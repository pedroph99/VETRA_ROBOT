from __future__ import annotations

import argparse
import math
import os
import signal
import socket
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import uvicorn
import zmq
from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


@dataclass
class Zone:
    id: int
    name: str
    crop: str
    x: float
    y: float
    moisture: float
    threshold: float
    watering_seconds: float
    enabled: bool = True
    dryness_per_minute: float = 4.0


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.zones = [
            Zone(1, "Area 1", "Alface", -1.25, -0.9, 62, 42, 5),
            Zone(2, "Area 2", "Tomate", 0.10, -0.9, 53, 48, 6),
            Zone(3, "Area 3", "Pimentao", -1.25, 0.9, 68, 40, 5),
            Zone(4, "Area 4", "Morango", 0.10, 0.9, 58, 50, 4),
        ]
        self.automatic = True
        self.operating_start = "00:00"
        self.operating_end = "23:59"
        self.robot_status = "Inicializando"
        self.current_zone: int | None = None
        self.manual_queue: list[int] = []
        self.events: list[dict[str, str]] = []
        self.running = True

    def log(self, message: str) -> None:
        with self.lock:
            self.events.insert(0, {"time": datetime.now().strftime("%H:%M:%S"), "message": message})
            del self.events[30:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "zones": [asdict(z) for z in self.zones],
                "automatic": self.automatic,
                "operating_start": self.operating_start,
                "operating_end": self.operating_end,
                "robot_status": self.robot_status,
                "current_zone": self.current_zone,
                "events": list(self.events),
                "server_time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            }


class ZoneUpdate(BaseModel):
    crop: str = Field(min_length=1, max_length=40)
    threshold: float = Field(ge=0, le=100)
    watering_seconds: float = Field(ge=1, le=60)
    enabled: bool = True


class MoistureUpdate(BaseModel):
    moisture: float = Field(ge=0, le=100)


class GlobalUpdate(BaseModel):
    automatic: bool
    operating_start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    operating_end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AgroBot | Central de Irrigacao</title>
  <style>
    :root{--green:#1f6f43;--lime:#7fbf4d;--ink:#173126;--cream:#f5f3e8;--card:#fff;--danger:#b84336}
    *{box-sizing:border-box} body{margin:0;background:var(--cream);color:var(--ink);font:15px system-ui,Segoe UI,sans-serif}
    header{background:linear-gradient(120deg,#174f34,#2f8556);color:white;padding:22px max(20px,calc((100% - 1120px)/2))}
    h1{margin:0;font-size:28px} header p{margin:5px 0 0;opacity:.85}.wrap{max-width:1120px;margin:auto;padding:22px}
    .top,.zones{display:grid;gap:16px}.top{grid-template-columns:2fr 1fr;margin-bottom:18px}.zones{grid-template-columns:repeat(2,1fr)}
    .card{background:var(--card);border:1px solid #dce4dc;border-radius:14px;padding:18px;box-shadow:0 5px 20px #21402b10}
    .status{font-size:20px;font-weight:700;color:var(--green)}.muted{color:#617267}.row{display:flex;gap:10px;align-items:end;flex-wrap:wrap}
    label{display:grid;gap:5px;font-size:13px;font-weight:650;flex:1;min-width:110px}input{width:100%;padding:9px;border:1px solid #bdcbbf;border-radius:8px}
    button{border:0;border-radius:8px;padding:10px 13px;background:var(--green);color:white;font-weight:700;cursor:pointer}button.alt{background:#52685b}button.warn{background:var(--danger)}
    .meter{height:12px;background:#e6e9df;border-radius:8px;overflow:hidden;margin:9px 0}.meter span{display:block;height:100%;background:var(--lime);transition:width .3s}
    .zone-head{display:flex;justify-content:space-between;gap:10px}.badge{background:#e7f2e8;padding:5px 8px;border-radius:20px;font-weight:700}
    #events{max-height:220px;overflow:auto;margin:0;padding-left:20px}#events li{margin:7px 0}.error{color:var(--danger);font-weight:700}
    @media(max-width:760px){.top,.zones{grid-template-columns:1fr}}
  </style>
</head>
<body>
<header><h1>AgroBot</h1><p>Irrigacao inteligente por areas de cultivo</p></header>
<main class="wrap">
  <section class="top">
    <div class="card"><div class="muted">Estado do robo</div><div id="robotStatus" class="status">Conectando...</div><div id="serverTime" class="muted"></div></div>
    <div class="card"><div class="row"><label>Inicio<input id="start" type="time"></label><label>Fim<input id="end" type="time"></label></div><p><label style="display:flex"><input id="automatic" type="checkbox" style="width:auto"> Modo automatico</label></p><button onclick="saveGlobal()">Salvar programacao</button></div>
  </section>
  <section id="zones" class="zones"></section>
  <section class="card" style="margin-top:18px"><h2>Historico recente</h2><ol id="events"></ol></section>
</main>
<script>
let last={zones:[]};
async function api(url, options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});if(!r.ok)throw new Error(await r.text());return r.json()}
function zoneCard(z){return `<article class="card"><div class="zone-head"><div><b>${z.name}</b><div class="muted">Sensor ${z.id}</div></div><span class="badge">${Math.round(z.moisture)}%</span></div><div class="meter"><span style="width:${z.moisture}%"></span></div><div class="row"><label>Cultura<input id="crop-${z.id}" value="${z.crop}"></label><label>Limite (%)<input id="threshold-${z.id}" type="number" min="0" max="100" value="${z.threshold}"></label><label>Rega (s)<input id="seconds-${z.id}" type="number" min="1" max="60" value="${z.watering_seconds}"></label></div><p><label style="display:flex"><input id="enabled-${z.id}" type="checkbox" style="width:auto" ${z.enabled?'checked':''}> Setor habilitado</label></p><div class="row"><button onclick="saveZone(${z.id})">Salvar setor</button><button class="alt" onclick="water(${z.id})">Irrigar agora</button><button class="warn" onclick="dry(${z.id})">Simular solo seco</button></div></article>`}
async function refresh(){try{last=await api('/api/status');document.getElementById('robotStatus').textContent=last.robot_status;document.getElementById('serverTime').textContent=last.server_time;let active=document.activeElement?.tagName==='INPUT';if(!active){document.getElementById('start').value=last.operating_start;document.getElementById('end').value=last.operating_end;document.getElementById('automatic').checked=last.automatic;document.getElementById('zones').innerHTML=last.zones.map(zoneCard).join('')}document.getElementById('events').innerHTML=last.events.map(e=>`<li><b>${e.time}</b> — ${e.message}</li>`).join('')}catch(e){document.getElementById('robotStatus').innerHTML='<span class="error">Sem comunicacao</span>'}}
async function saveGlobal(){await api('/api/settings',{method:'PUT',body:JSON.stringify({automatic:document.getElementById('automatic').checked,operating_start:document.getElementById('start').value,operating_end:document.getElementById('end').value})});refresh()}
async function saveZone(id){await api('/api/zones/'+id,{method:'PUT',body:JSON.stringify({crop:document.getElementById('crop-'+id).value,threshold:+document.getElementById('threshold-'+id).value,watering_seconds:+document.getElementById('seconds-'+id).value,enabled:document.getElementById('enabled-'+id).checked})});refresh()}
async function water(id){await api('/api/control/water/'+id,{method:'POST'});refresh()}
async function dry(id){await api('/api/zones/'+id+'/moisture',{method:'PUT',body:JSON.stringify({moisture:15})});refresh()}
refresh();setInterval(refresh,1000);
</script></body></html>"""


def make_app(state: SharedState) -> FastAPI:
    app = FastAPI(title="AgroBot Prototype")

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return HTML

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return state.snapshot()

    @app.put("/api/settings")
    def update_settings(data: GlobalUpdate) -> dict[str, bool]:
        with state.lock:
            state.automatic = data.automatic
            state.operating_start = data.operating_start
            state.operating_end = data.operating_end
        state.log("Programacao geral atualizada pela plataforma")
        return {"ok": True}

    @app.put("/api/zones/{zone_id}")
    def update_zone(zone_id: int, data: ZoneUpdate) -> dict[str, bool]:
        zone = next((z for z in state.zones if z.id == zone_id), None)
        if not zone:
            raise HTTPException(404, "Area inexistente")
        with state.lock:
            zone.crop = data.crop
            zone.threshold = data.threshold
            zone.watering_seconds = data.watering_seconds
            zone.enabled = data.enabled
        state.log(f"Parametros da {zone.name} ({zone.crop}) atualizados")
        return {"ok": True}

    @app.put("/api/zones/{zone_id}/moisture")
    def update_moisture(zone_id: int, data: MoistureUpdate) -> dict[str, bool]:
        zone = next((z for z in state.zones if z.id == zone_id), None)
        if not zone:
            raise HTTPException(404, "Area inexistente")
        with state.lock:
            zone.moisture = data.moisture
        state.log(f"Leitura simulada do sensor {zone.id}: {data.moisture:.0f}%")
        return {"ok": True}

    @app.post("/api/control/water/{zone_id}")
    def manual_water(zone_id: int) -> dict[str, bool]:
        if not any(z.id == zone_id for z in state.zones):
            raise HTTPException(404, "Area inexistente")
        with state.lock:
            state.manual_queue.append(zone_id)
        state.log(f"Irrigacao manual solicitada para a Area {zone_id}")
        return {"ok": True}

    return app


class Scene:
    def __init__(self, sim: Any, state: SharedState) -> None:
        self.sim = sim
        self.state = state
        self.root = -1
        self.robot = -1
        self.nozzle = -1
        self.sensor_lights: dict[int, int] = {}
        self.water_drawing = -1
        self.home = (1.55, 0.0)

    def _shape(self, primitive: int, size: list[float], position: list[float], color: list[float], alias: str, parent: int = -1) -> int:
        h = self.sim.createPrimitiveShape(primitive, size, 0)
        self.sim.setObjectAlias(h, alias)
        self.sim.setObjectPosition(h, self.sim.handle_world, position)
        self.sim.setShapeColor(h, None, self.sim.colorcomponent_ambient_diffuse, color)
        try:
            self.sim.setObjectInt32Param(h, self.sim.shapeintparam_static, 1)
        except Exception:
            pass
        if parent != -1:
            self.sim.setObjectParent(h, parent, True)
        return h

    def build(self) -> None:
        sim = self.sim
        previous = sim.getObject('/AgroBotPrototype', {'noError': True})
        while previous != -1:
            sim.removeObjects(sim.getObjectsInTree(previous))
            previous = sim.getObject('/AgroBotPrototype', {'noError': True})
        self.root = sim.createDummy(0.015)
        sim.setObjectAlias(self.root, "AgroBotPrototype")

        self._shape(sim.primitiveshape_cuboid, [4.2, 3.2, 0.08], [0.0, 0.0, -0.04], [0.80, 0.78, 0.64], "AgroBot_Floor", self.root)
        self._shape(sim.primitiveshape_cuboid, [0.65, 3.0, 0.015], [1.35, 0.0, 0.012], [0.63, 0.56, 0.43], "AgroBot_Lane", self.root)

        crop_colors = ([0.20, 0.68, 0.25], [0.12, 0.55, 0.18], [0.40, 0.72, 0.17], [0.70, 0.18, 0.18])
        for zone, crop_color in zip(self.state.zones, crop_colors):
            self._shape(sim.primitiveshape_cuboid, [1.05, 1.18, 0.14], [zone.x, zone.y, 0.07], [0.27, 0.15, 0.07], f"{zone.name}_{zone.crop}_Solo", self.root)
            for dx in (-0.28, 0.0, 0.28):
                for dy in (-0.30, 0.30):
                    self._shape(sim.primitiveshape_cylinder, [0.025, 0.025, 0.22], [zone.x + dx, zone.y + dy, 0.23], [0.16, 0.42, 0.12], f"Planta_{zone.id}_Caule", self.root)
                    self._shape(sim.primitiveshape_spheroid, [0.15, 0.15, 0.15], [zone.x + dx, zone.y + dy, 0.38], list(crop_color), f"Planta_{zone.id}_Folha", self.root)
            self._shape(sim.primitiveshape_cylinder, [0.045, 0.045, 0.43], [zone.x + 0.43, zone.y - 0.45, 0.25], [0.20, 0.22, 0.20], f"Sensor_{zone.id}_Haste", self.root)
            self.sensor_lights[zone.id] = self._shape(sim.primitiveshape_spheroid, [0.13, 0.13, 0.13], [zone.x + 0.43, zone.y - 0.45, 0.50], [0.3, 0.9, 0.3], f"Sensor_{zone.id}_Indicador", self.root)

        self.robot = sim.createDummy(0.02)
        sim.setObjectAlias(self.robot, "AgroBot_Robo")
        sim.setObjectPosition(self.robot, sim.handle_world, [self.home[0], self.home[1], 0.0])
        sim.setObjectParent(self.robot, self.root, True)
        self._shape(sim.primitiveshape_cuboid, [0.62, 0.48, 0.16], [self.home[0], self.home[1], 0.18], [0.12, 0.43, 0.24], "AgroBot_Base", self.robot)
        self._shape(sim.primitiveshape_cylinder, [0.34, 0.34, 0.42], [self.home[0], self.home[1], 0.47], [0.18, 0.55, 0.78], "AgroBot_Reservatorio", self.robot)
        for dy in (-0.27, 0.27):
            for dx in (-0.20, 0.20):
                wheel = self._shape(sim.primitiveshape_cylinder, [0.14, 0.14, 0.08], [self.home[0] + dx, self.home[1] + dy, 0.13], [0.08, 0.08, 0.08], "AgroBot_Roda", self.robot)
                sim.setObjectOrientation(wheel, self.robot, [math.pi / 2, 0, 0])
        self.nozzle = self._shape(sim.primitiveshape_cylinder, [0.07, 0.07, 0.50], [self.home[0] - 0.25, self.home[1], 0.60], [0.75, 0.78, 0.80], "AgroBot_Bico", self.robot)
        sim.setObjectOrientation(self.nozzle, self.robot, [0, math.pi / 2, 0])
        self.water_drawing = sim.addDrawingObject(sim.drawing_lines, 5, 0, sim.handle_world, 1, [0.1, 0.55, 1.0])
        self.state.log("Cena criada com quatro areas de cultivo")

    def robot_position(self) -> tuple[float, float]:
        p = self.sim.getObjectPosition(self.robot, self.sim.handle_world)
        return float(p[0]), float(p[1])

    def move_robot(self, x: float, y: float) -> None:
        self.sim.setObjectPosition(self.robot, self.sim.handle_world, [x, y, 0.0])

    def water_line(self, zone: Zone | None) -> None:
        self.sim.addDrawingObjectItem(self.water_drawing, None)
        if zone is None:
            return
        x, y = self.robot_position()
        self.sim.addDrawingObjectItem(self.water_drawing, [x - 0.48, y, 0.60, zone.x + 0.35, zone.y, 0.18])

    def update_sensor_colors(self) -> None:
        for zone in self.state.zones:
            if zone.moisture < zone.threshold:
                color = [0.95, 0.18, 0.08]
            elif zone.moisture < zone.threshold + 10:
                color = [1.0, 0.65, 0.08]
            else:
                color = [0.20, 0.85, 0.25]
            self.sim.setShapeColor(self.sensor_lights[zone.id], None, self.sim.colorcomponent_ambient_diffuse, color)


def time_allowed(start: str, end: str) -> bool:
    now = datetime.now().strftime("%H:%M")
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def run_controller(scene: Scene, state: SharedState) -> None:
    mode = "idle"
    active: Zone | None = None
    watering_started = 0.0
    last = time.monotonic()
    speed = 0.65

    while state.running:
        now = time.monotonic()
        dt = min(now - last, 0.15)
        last = now
        with state.lock:
            for zone in state.zones:
                zone.moisture = max(0.0, zone.moisture - zone.dryness_per_minute * dt / 60.0)

            if mode == "idle":
                requested = state.manual_queue.pop(0) if state.manual_queue else None
                if requested is not None:
                    active = next(z for z in state.zones if z.id == requested)
                elif state.automatic and time_allowed(state.operating_start, state.operating_end):
                    candidates = [z for z in state.zones if z.enabled and z.moisture < z.threshold]
                    active = min(candidates, key=lambda z: z.moisture - z.threshold) if candidates else None
                else:
                    active = None
                if active:
                    mode = "moving_to_zone"
                    state.current_zone = active.id
                    state.robot_status = f"Indo para {active.name} - {active.crop}"
                    state.log(f"Sensor {active.id} solicitou irrigacao da cultura {active.crop}")
                else:
                    state.robot_status = "Monitorando os sensores" if state.automatic else "Modo automatico pausado"

            target = None
            if mode == "moving_to_zone" and active:
                target = (0.80, active.y)
            elif mode == "returning":
                target = scene.home

            if target:
                x, y = scene.robot_position()
                dx, dy = target[0] - x, target[1] - y
                distance = math.hypot(dx, dy)
                if distance <= 0.025:
                    scene.move_robot(*target)
                    if mode == "moving_to_zone" and active:
                        mode = "watering"
                        watering_started = now
                        state.robot_status = f"Irrigando {active.name} - {active.crop}"
                        state.log(f"Bomba acionada na {active.name}")
                    else:
                        mode = "idle"
                        active = None
                        state.current_zone = None
                        state.robot_status = "Monitorando os sensores"
                else:
                    step = min(speed * dt, distance)
                    scene.move_robot(x + dx / distance * step, y + dy / distance * step)

            if mode == "watering" and active:
                active.moisture = min(100.0, active.moisture + 7.0 * dt)
                scene.water_line(active)
                if now - watering_started >= active.watering_seconds or active.moisture >= active.threshold + 12:
                    state.log(f"Irrigacao concluida na {active.name}; umidade em {active.moisture:.0f}%")
                    scene.water_line(None)
                    mode = "returning"
                    state.robot_status = "Retornando a base"
            else:
                scene.water_line(None)

            scene.update_sensor_colors()
        time.sleep(0.04)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgroBot: irrigacao por setores no CoppeliaSim")
    parser.add_argument("--coppelia-host", default="127.0.0.1")
    parser.add_argument("--coppelia-port", type=int, default=23000)
    parser.add_argument("--web-host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-save-scene", action="store_true")
    parser.add_argument("--scene-path", default="AgroBotPrototype.ttt")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = SharedState()
    try:
        with socket.create_connection((args.coppelia_host, args.coppelia_port), timeout=3):
            pass
    except OSError as exc:
        raise SystemExit('CoppeliaSim indisponivel. Abra o simulador antes de iniciar o AgroBot.') from exc
    client = RemoteAPIClient(host=args.coppelia_host, port=args.coppelia_port)
    client.socket.setsockopt(zmq.RCVTIMEO, 10000)
    client.socket.setsockopt(zmq.SNDTIMEO, 10000)
    client.socket.setsockopt(zmq.LINGER, 0)
    sim = client.require("sim")

    if sim.getSimulationState() != sim.simulation_stopped:
        raise RuntimeError("Pare a simulacao atual e execute novamente em uma cena vazia.")

    scene = Scene(sim, state)
    scene.build()
    if not args.no_save_scene:
        path = os.path.abspath(args.scene_path)
        sim.saveScene(path)
        state.log(f"Cena salva como {os.path.basename(path)}")

    app = make_app(state)
    server = uvicorn.Server(uvicorn.Config(app, host=args.web_host, port=args.web_port, log_level="warning"))
    web_thread = threading.Thread(target=server.run, name="agrobot-web", daemon=True)
    web_thread.start()

    def stop(*_: Any) -> None:
        state.running = False
        server.should_exit = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    sim.startSimulation()
    state.log("Simulacao iniciada")
    url = f"http://{args.web_host}:{args.web_port}"
    print(f"AgroBot em execucao. Painel: {url}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        run_controller(scene, state)
    finally:
        state.running = False
        server.should_exit = True
        if sim.getSimulationState() != sim.simulation_stopped:
            sim.stopSimulation()
        print("AgroBot finalizado.")


if __name__ == "__main__":
    main()
