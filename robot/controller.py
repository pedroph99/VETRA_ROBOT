"""Navegação, bateria, agenda e execução da missão."""
import math
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from robot.field_layout import LENGTH, route_point
from robot.energy import (BASE_PER_SECOND, CAMERA_PER_SECOND, DRIVE_PER_METRE,
                          INFERENCE_PER_SECOND, TURN_PER_RADIAN, return_reserve)
from robot.state import stamp
from server.src.classification.service import SimulatedDetector

class Controller:
    def __init__(self, state, scene, detector=None):
        self.s, self.scene, self.detector = state, scene, detector or SimulatedDetector()
        self.index = 0
        self.elapsed = 0.
        self.blocked_time = 0.
        self.blocked_pose = None
        self.resume_state = None
        self.route_distance = 0.
        self.visit_order = sorted(state.beds, key=lambda b: b['route_distance'])
        self.executor = ThreadPoolExecutor(max_workers=1) if getattr(self.detector, 'background', False) else None
        self.pending = None
        state.controller = self

    def close(self):
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)

    def cancel_pending(self):
        if self.pending:
            self.pending[0].cancel()
            self.pending = None

    def command(self, command):
        s = self.s
        if command == 'START_MISSION':
            if not s.connected or s.status != 'DOCKED':
                raise ValueError('O robô precisa estar conectado e na estação para iniciar.')
            if s.battery <= 20:
                raise ValueError('Aguarde a recarga da bateria acima de 20%.')
            self.index, self.elapsed = 0, 0.
            self.route_distance = 0.
            s.mission = dict(id=uuid.uuid4().hex[:10], started_at=stamp(), finished_at=None, inspected=0, total=len(s.beds), progress=0, outcome='RUNNING')
            s.error = None
            s.status = 'STARTING_MISSION'
            s.log(f'Missão {s.mission["id"]} iniciada. Ronda de {len(s.beds)} canteiros até o STOP.')
        elif command == 'PAUSE_MISSION':
            if s.status not in ('STARTING_MISSION','NAVIGATING','INSPECTING','RETURNING_HOME'):
                raise ValueError('Não há deslocamento ou inspeção para pausar.')
            self.resume_state = s.status
            s.status = 'PAUSED'
            s.log('Missão pausada pelo operador.')
        elif command == 'RESUME_MISSION':
            if s.status != 'PAUSED':
                raise ValueError('A missão não está pausada.')
            s.status = self.resume_state
            s.log('Missão retomada.')
        elif command in ('RETURN_HOME', 'STOP_MISSION'):
            if s.status == 'DOCKED':
                raise ValueError('O robô já está na estação.')
            if not s.connected:
                raise ValueError('Comunicação indisponível; reinicie a conexão com o simulador.')
            if s.mission:
                s.mission['outcome'] = 'INTERRUPTED'
            self.cancel_pending()
            s.status = 'RETURNING_HOME'
            s.current_bed = None
            s.error = None
            self.blocked_time = 0
            s.log('Missão interrompida. Retorno à estação solicitado.', 'warning')

    def schedule(self, now=None):
        s = self.s
        now = now or datetime.now().astimezone()
        key = now.strftime('%Y-%m-%d %H:%M')
        if s.settings['enabled'] and now.weekday() in s.settings['days'] and now.strftime('%H:%M') in s.settings['times'] and key not in s.fired:
            s.fired = (s.fired + [key])[-100:]
            s.store.save('fired', s.fired)
            if s.status == 'DOCKED' and s.battery > 20 and s.connected:
                self.command('START_MISSION')
                s.log('Ronda iniciada pelo agendamento.')
            else:
                s.log('Horário programado não executado: robô ocupado ou indisponível.', 'warning')

    def line_guided_heading(self, waypoint_heading):
        """Correct the waypoint heading with the three downward line sensors."""
        reader = getattr(self.scene, 'read_line_sensors', None)
        if reader is None:
            return waypoint_heading
        left, center, right = reader()
        # On uniform surfaces (including the docking platform), keep the
        # waypoint heading. Once the black stripe is visible, a darker left
        # or right sensor gently steers the robot back toward the center.
        if max(left, center, right)-min(left, center, right) < .12:
            return waypoint_heading
        return waypoint_heading + .45*(left-right)

    def tick(self, dt):
        s = self.s
        self.schedule()
        if s.status == 'DOCKED':
            s.battery = min(100, s.battery + dt*.6)
            return
        if s.status in ('ERROR','FINISHED'):
            return
        s.battery = max(0, s.battery - dt*BASE_PER_SECOND)
        reserve = max(20., return_reserve(self.route_distance))
        if s.battery <= reserve and s.status != 'RETURNING_HOME' and not (s.status in ('OBSTACLE','BLOCKED') and self.resume_state == 'RETURNING_HOME'):
            if s.mission:
                s.mission['outcome'] = 'LOW_BATTERY'
            s.status, s.current_bed = 'RETURNING_HOME', None
            self.cancel_pending()
            s.log(f'Bateria na reserva de retorno ({reserve:.1f}%). Inspeção interrompida.', 'warning')
        if s.status == 'PAUSED':
            return
        advance_camera = getattr(self.scene, 'advance_camera', None)
        camera_ready = advance_camera(dt, tracking=s.status == 'INSPECTING') if advance_camera else True
        if s.status == 'INSPECTING':
            s.battery = max(0, s.battery - dt*CAMERA_PER_SECOND)
            if self.pending:
                s.battery = max(0, s.battery - dt*INFERENCE_PER_SECOND)
        if s.status == 'STARTING_MISSION':
            s.status = 'NAVIGATING'
        if s.status in ('OBSTACLE','BLOCKED'):
            if self.scene.blocked(*(self.blocked_pose or (*s.position, s.heading))):
                self.blocked_time += dt
                if self.blocked_time >= 10 and s.status != 'BLOCKED':
                    s.status, s.error = 'BLOCKED', 'PATH_BLOCKED'
                    s.log('Corredor bloqueado há 10 segundos. Aguardando liberação.', 'warning')
                return
            s.status, s.error = self.resume_state, None
            self.blocked_time = 0
            s.log('Corredor liberado. Rota retomada.')
        if s.status in ('NAVIGATING','RETURNING_HOME'):
            returning = s.status == 'RETURNING_HOME'
            bed = None if returning or self.index == len(self.visit_order) else self.visit_order[self.index]
            s.current_bed = bed['id'] if bed else None
            destination = 0. if returning else (bed['route_distance'] if bed else LENGTH)
            direction = -1 if returning else 1
            next_distance = self.route_distance + direction*min(.25,abs(destination-self.route_distance))
            target = route_point(next_distance)
            dx, dy = target[0]-s.position[0], target[1]-s.position[1]
            distance = math.hypot(dx,dy)
            if distance > .035:
                heading = self.line_guided_heading(math.atan2(dy,dx))
                angle = (heading-s.heading+math.pi) % (2*math.pi)-math.pi
                turn = max(-dt*1.8, min(dt*1.8, angle))
                s.heading += turn
                s.battery = max(0, s.battery - abs(turn)*TURN_PER_RADIAN)
                if abs(angle) > .04:
                    self.scene.move(*s.position, s.heading)
                    return
                step = min(.85*dt, distance)
                x,y = s.position[0]+math.cos(s.heading)*step, s.position[1]+math.sin(s.heading)*step
                if self.scene.blocked(x,y,s.heading):
                    self.blocked_pose = (x, y, s.heading)
                    self.resume_state = s.status
                    s.status = 'OBSTACLE'
                    self.blocked_time = 0
                    s.log('Obstáculo à frente. Motores parados; aguardando passagem segura.', 'warning')
                    return
                self.scene.move(x,y,s.heading)
                s.position = [x,y]
                s.battery = max(0, s.battery - step*DRIVE_PER_METRE)
            elif abs(next_distance-destination) > .001:
                self.route_distance = next_distance
            elif returning or bed is None:
                self.route_distance = destination
                s.position = list(route_point(destination))
                self.scene.move(*s.position,s.heading)
                s.status, s.current_bed = ('DOCKED' if returning else 'FINISHED'), None
                if s.mission:
                    s.mission['finished_at'] = stamp()
                    if s.mission['outcome'] == 'RUNNING':
                        s.mission['outcome'] = 'COMPLETED'
                    s.store.append('mission', s.mission)
                    s.last_mission = dict(s.mission)
                    s.log(f'Missão {s.mission["id"]} encerrada: {s.mission["inspected"]}/{len(s.beds)} canteiros. Robô em {"START" if returning else "STOP"}.')
                    s.mission = None
            else:
                self.route_distance = destination
                self.scene.aim(bed)
                s.status = 'INSPECTING'
                self.elapsed = 0
                s.log(f'{bed["name"]}: robô parado, ajustando a câmera para as plantas.')
        elif s.status == 'INSPECTING':
            self.elapsed += dt
            if self.elapsed < 2 or not camera_ready:
                return
            bed = self.visit_order[self.index]
            failure_code = 'CAMERA_UNAVAILABLE'
            try:
                if self.pending:
                    failure_code = 'INFERENCE_UNAVAILABLE'
                    future, key, filename, source, capture = self.pending
                    if not future.done():
                        return
                    self.pending = None
                    result = future.result()
                else:
                    key = uuid.uuid4().hex
                    if getattr(self.detector, 'bank', None) is not None:
                        capture = self.scene.capture_for_model(bed, key, self.detector.bank)
                        filename, source = capture['filename'], capture['source']
                    else:
                        filename, source = self.scene.capture(bed, key)
                        capture = None
                    failure_code = 'INFERENCE_UNAVAILABLE'
                    image_path = s.data_dir / 'images' / filename
                    if self.executor:
                        future = self.executor.submit(self.detector.analyze, image_path, dict(bed, capture=capture))
                        self.pending = (future, key, filename, source, capture)
                        s.log(f'{bed["name"]}: captura concluída; enviando a imagem observada ao servidor.')
                        return
                    result = self.detector.analyze(image_path, dict(bed, capture=capture))
            except Exception as exc:
                s.status, s.error = 'ERROR', failure_code
                s.log(f'Falha na captura/análise do {bed["name"]}: {exc}', 'error')
                return
            analysis_image = result.pop('analysis_image', None)
            record = dict(id=key, mission_id=s.mission['id'], bed_id=bed['id'], greenhouse='Estufa 01', time=stamp(),
                          position=list(s.position), image=analysis_image or f'/images/{filename}',
                          image_source=source, **result)
            s.store.append('inspection', record)
            bed['latest'] = record
            mode = 'simulado' if result.get('simulated') else 'do servidor'
            s.log(f'{bed["name"]}: {result["problem"]}. Resultado {mode}: {result["status"]}.', 'warning' if result['status']!='NORMAL' else 'info')
            self.index += 1
            s.mission['inspected'] = self.index
            s.mission['progress'] = round(100*self.index/len(s.beds))
            s.status = 'NAVIGATING'
            self.scene.update()
