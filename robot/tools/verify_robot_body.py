"""Rebuild, validate and preview the tracked robot in CoppeliaSim."""
import math
import shutil
import tempfile
import time
from argparse import ArgumentParser, Namespace
from pathlib import Path

import zmq
from coppeliasim_zmqremoteapi_client import RemoteAPIClient

from robot.field_layout import HOME, ROUTE
from robot.greenhouse_scene import Scene, png_rgb
from robot.state import State
from server.src.config import PROJECT_ROOT, SCENES_DIR


def check_animation(scene):
    sim = scene.sim
    handles = [sim.getObject(f'/AgroBotEstufa/AgroBot_Inspecao/Patim_{side}_03')
               for side in ('Esquerda', 'Direita')]

    def positions():
        return [sim.getObjectPosition(h, scene.robot)[0] for h in handles]

    def step_animation():
        # step() may return when the clock advances, before sensing callbacks.
        # A second stationary step gives the pose-following script its barrier.
        sim.step()
        sim.step()

    wheels = [sim.getObject(f'/AgroBotEstufa/AgroBot_Inspecao/Roda_{side}_{end}')
              for side in ('Esquerda', 'Direita') for end in ('Frontal', 'Traseira')]

    def angles():
        values = []
        for wheel in wheels:
            matrix = sim.getObjectMatrix(wheel, scene.robot)
            assert all(abs(a-b)<1e-6 for a,b in zip((matrix[2], matrix[6], matrix[10]), (0,-1,0))), 'Eixo da roda inclinou.'
            q = sim.getObjectQuaternion(wheel, scene.robot)
            values.append(2*math.atan2(q[1], q[3]))
        return values

    def check_rotation(before, after, travel):
        for i, (a,b) in enumerate(zip(before, after)):
            delta = (b-a+math.pi)%(2*math.pi)-math.pi
            assert abs(delta-travel[i//2]/.114) < 1e-5, (delta, travel, before, after)

    sim.setStepping(True)
    try:
        step_animation()
        start = positions()
        initial_angles = angles()
        scene.move(HOME[0], HOME[1]+.10, math.pi/2)
        step_animation()
        forward = positions()
        forward_angles = angles()
        check_rotation(initial_angles, forward_angles, [.10, .10])
        assert all(abs((b-a)-.10) < .001 for a,b in zip(start, forward)), (start, forward)
        scene.move(HOME[0], HOME[1]+.10, math.pi/2+.20)
        step_animation()
        turned = positions()
        turn_angles = angles()
        check_rotation(forward_angles, turn_angles, [-.316*.20, .316*.20])
        assert turned[0] < forward[0] and turned[1] > forward[1], (forward, turned)
        step_animation()
        assert positions() == turned, 'Esteiras se moveram com o robô parado.'
        assert angles() == turn_angles, 'Rodas se moveram com o robô parado.'
        heading = math.pi/2+.20
        scene.move(HOME[0]-.05*math.cos(heading), HOME[1]+.10-.05*math.sin(heading), heading)
        step_animation()
        check_rotation(turn_angles, angles(), [-.05, -.05])
        print('Rodas e esteiras: avanço, ré, curva, eixo e parada verificados.', flush=True)
    finally:
        sim.setStepping(False)


def check_shell_toggle(scene, previews):
    sim = scene.sim
    controller = sim.getObject('/AgroBotEstufa/AgroBot_Inspecao/Controle_Carcaca')
    visible, count, ui_created = sim.callScriptFunction('getShellState', controller)
    assert visible and count >= 7 and ui_created
    names = {'Carcaca_Branca', 'Capo_Preto', 'Tampa_Traseira', 'Ventilacao_Lateral',
             'Painel_Sensores_Frontal', 'Saia_Inferior_Preta', 'Para_Choque_Frontal'}
    objects = sim.getObjectsInTree(scene.robot, sim.sceneobject_shape, 1)
    original = {h:sim.getObjectInt32Param(h, sim.objintparam_visibility_layer)
                for h in objects if sim.getObjectAlias(h) in names}
    interior = [h for h in objects if sim.getObjectAlias(h).startswith('Interior_')]
    assert len(interior) > 40
    pose = sim.getObjectPose(scene.robot, sim.handle_world)
    for _ in range(2):
        assert sim.callScriptFunction('toggleShell', controller) is False
        assert all(sim.getObjectInt32Param(h, sim.objintparam_visibility_layer) == 0 for h in original)
        assert all(sim.getObjectInt32Param(h, sim.objintparam_visibility_layer) != 0 for h in interior)
        assert sim.callScriptFunction('toggleShell', controller) is True
        assert all(sim.getObjectInt32Param(h, sim.objintparam_visibility_layer) == layer for h,layer in original.items())
    assert sim.getObjectPose(scene.robot, sim.handle_world) == pose
    assert sim.getObjectsInTree(scene.robot, sim.sceneobject_shape, 1) == objects
    sim.callScriptFunction('toggleShell', controller)
    scene.move(*HOME, math.pi/2)
    view = sim.createVisionSensor(1|2|4|128, [1000,900,0,0],
        [.02,40,math.radians(42),.01,0,0,.94,.94,.94,0,0])
    try:
        scene.point_camera(view, [HOME[0]+1.4,HOME[1]+1.6,1.20], [*HOME,.47])
        sim.handleVisionSensor(view)
        data,res = sim.getVisionSensorImg(view)
        (previews/'robo-esteiras-interior.png').write_bytes(png_rgb(data,*res))
    finally:
        sim.removeObjects([view])
    print('Botão nativo: abrir/recolocar duas vezes e interior visível verificados.', flush=True)
    return original


def check_camera_aim(scene, bed):
    sim = scene.sim
    scene.aim(bed)
    assert not scene.advance_camera(.05), 'O suporte saltou direto para o alvo.'
    for _ in range(40):
        if scene.advance_camera(.05):
            break
    else:
        raise AssertionError('O suporte da câmera não chegou ao alvo.')
    matrix = sim.getObjectMatrix(scene.camera, sim.handle_world)
    vector = [bed['x']-matrix[3], bed['y']-matrix[7], .48-matrix[11]]
    direction = [matrix[2], matrix[6], matrix[10]]
    cosine = sum(a*b for a,b in zip(direction, vector))/math.sqrt(sum(v*v for v in vector))
    assert cosine > .9999, f'Câmera desalinhada: {cosine}'
    assert sim.getObjectParent(scene.camera) == scene.camera_tilt


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=23000)
    args = parser.parse_args()
    client = RemoteAPIClient(port=args.port)
    client.socket.setsockopt(zmq.RCVTIMEO, 10000)
    sim = client.require('sim')
    if sim.getSimulationState() != sim.simulation_stopped:
        raise RuntimeError('Pare a simulação antes de atualizar a carcaça.')
    target = SCENES_DIR/'AgroBotEstufa.ttt'
    backup = SCENES_DIR/'AgroBotEstufa.antes-interior-robo.ttt'
    if target.exists() and not backup.exists():
        shutil.copy2(target, backup)
    previews = PROJECT_ROOT/'robot'/'previews'
    previews.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        state = State(Path(folder))
        try:
            scene = Scene(state, Namespace(
                coppelia_host='127.0.0.1', coppelia_port=args.port,
                no_save_scene=True, scene_path=target))
            try:
                check_animation(scene)
                shell_layers = check_shell_toggle(scene, previews)
            finally:
                scene.close()
            deadline = time.monotonic()+10
            while sim.getSimulationState() != sim.simulation_stopped:
                if time.monotonic() > deadline:
                    raise RuntimeError('O simulador não parou para salvar a cena.')
                time.sleep(.1)
            assert all(sim.getObjectInt32Param(h,sim.objintparam_visibility_layer) == layer
                       for h,layer in shell_layers.items()), 'Carcaça não foi restaurada ao parar.'
            for point, nxt in zip(ROUTE, ROUTE[1:]):
                heading = math.atan2(nxt[1]-point[1], nxt[0]-point[0])
                assert not scene.blocked(*point, heading), f'Colisão em {point}'
            print('Rota: 240 posições livres.', flush=True)
            for i in [25, 105, 120, 135, 210]:
                point, nxt = ROUTE[i], ROUTE[i+1]
                scene.move(*point, math.atan2(nxt[1]-point[1], nxt[0]-point[0]))
                readings = scene.read_line_sensors()
                assert readings[1] > max(readings[0], readings[2])+.15, readings
            print('Sensores de linha: cinco trechos verificados.', flush=True)
            bed = state.beds[0]
            index = min(range(len(ROUTE)-1), key=lambda i: abs(ROUTE[i][1]-bed['y']))
            point, nxt = ROUTE[index], ROUTE[index+1]
            scene.move(*point, math.atan2(nxt[1]-point[1], nxt[0]-point[0]))
            state.position = list(point)
            check_camera_aim(scene, bed)
            check_camera_aim(scene, {'x': 0., 'y': point[1]})
            check_camera_aim(scene, bed)
            name, source = scene.capture(bed, 'validacao-camera-esteiras')
            assert source == 'coppeliasim' and (state.data_dir/'images'/name).stat().st_size > 5000
            print('Câmera RGB: giro gradual para os dois lados, inclinação e captura verificados.', flush=True)
            scene.move(*HOME, math.pi/2)
            assert scene.advance_camera(2., tracking=False)
            sim.setObjectPosition(scene.probe, sim.handle_world, [0, 0, -3])
            for name, eye, aim in [
                ('robo-esteiras-perspectiva.png', [HOME[0]+1.4, HOME[1]+1.6, 1.20],
                 [*HOME, .47]),
                ('robo-esteiras-frente.png', [HOME[0], HOME[1]+2.0, .90],
                 [*HOME, .47]),
            ]:
                view = sim.createVisionSensor(1|2|4|128, [1000, 900, 0, 0],
                    [.02, 40, math.radians(42), .01, 0, 0, .94, .94, .94, 0, 0])
                try:
                    scene.point_camera(view, eye, aim)
                    sim.handleVisionSensor(view)
                    data, resolution = sim.getVisionSensorImg(view)
                    (previews/name).write_bytes(png_rgb(data, *resolution))
                finally:
                    sim.removeObjects([view])
            default = sim.getObject('/DefaultCamera', {'noError': True})
            if default != -1:
                scene.point_camera(default, [HOME[0]+1.4, HOME[1]+1.6, 1.2], [*HOME, .47])
            sim.saveScene(str(target))
            print(f'Cena salva: {target}', flush=True)
        finally:
            state.store.close()


if __name__ == '__main__':
    main()
