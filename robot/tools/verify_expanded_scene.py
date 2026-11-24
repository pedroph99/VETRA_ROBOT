"""Build and verify the expanded scene on an already stopped simulator."""
import math
import tempfile
from argparse import Namespace
from pathlib import Path
from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from robot.state import State
from robot.greenhouse_scene import Scene, png_rgb
from robot.field_layout import ROUTE, HOME
from server.src.config import SCENES_DIR

root = SCENES_DIR
sim = RemoteAPIClient().require('sim')
assert sim.getSimulationState() == sim.simulation_stopped, 'Pare a simulação primeiro.'
backup = root/'AgroBotEstufa.antes-ampliacao.ttt'
if not backup.exists():
    sim.saveScene(str(backup))
with tempfile.TemporaryDirectory() as folder:
    state = State(folder)
    args = Namespace(coppelia_host='127.0.0.1', coppelia_port=23000,
                     no_save_scene=True, scene_path=root/'AgroBotEstufa.ttt')
    scene = Scene(state,args)
    scene.close()
    import time
    while sim.getSimulationState() != sim.simulation_stopped:
        time.sleep(.1)
    for i,p in enumerate(ROUTE[:-1]):
        nxt = ROUTE[i+1]
        heading = math.atan2(nxt[1]-p[1],nxt[0]-p[0])
        assert not scene.blocked(*p,heading), f'Colisão na rota: {i}, {p}'
    print('240 posições verificadas sem colisão.',flush=True)
    for i in [25,105,120,135,210]:
        p,nxt = ROUTE[i],ROUTE[i+1]
        scene.move(*p,math.atan2(nxt[1]-p[1],nxt[0]-p[0]))
        values = scene.read_line_sensors()
        print('Sensores',i,[round(v,3) for v in values],flush=True)
        assert values[1] > max(values[0],values[2])+.15, 'Faixa não detectada no centro'
    scene.move(*HOME,math.pi/2)
    sim.setObjectPosition(scene.probe,sim.handle_world,[0,0,-3])
    sim.saveScene(str(root/'AgroBotEstufa.ttt'))
    for name,eye,target,size in [
        ('estufa-ampliada-aerea.png',[0,.7,21],[0,.7,0],18.),
        ('estufa-ampliada-perspectiva.png',[13,-17,19],[0,.7,0],21.)]:
        view=sim.createVisionSensor(1|4|128,[1100,1100,0,0],[.01,70,size,.01,0,0,.94,.94,.91,0,0])
        try:
            scene.point_camera(view,eye,target)
            if 'aerea' in name:
                sim.setObjectMatrix(view,sim.handle_world,[-1,0,0,0,0,1,0,.7,0,0,-1,21])
            sim.handleVisionSensor(view)
            data,res=sim.getVisionSensorImg(view)
            (root/name).write_bytes(png_rgb(data,*res))
        finally:
            sim.removeObjects([view])
    state.store.db.close()
print('Cena salva e imagens geradas.',flush=True)
