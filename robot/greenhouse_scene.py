"""CoppeliaSim scene adapter. Kinematic differential navigation, simulated detector."""
import math
import struct
import zlib

import zmq
from PIL import Image
from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from robot.capture_plan import prepare_reference
from robot.capture_quality import assess_quality
from robot.field_layout import HOME, STOP, ROUTE, route_point
from robot.robot_body import CAMERA_LENS_X, CAMERA_PIVOT_Z, build_body


def png_rgb(data, width, height):
    def chunk(kind, payload):
        return struct.pack('!I', len(payload))+kind+payload+struct.pack('!I', zlib.crc32(kind+payload)&0xffffffff)
    # CoppeliaSim returns pixels from bottom to top.
    rows = b''.join(b'\0'+data[y*width*3:(y+1)*width*3] for y in range(height-1,-1,-1))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


class Scene:
    home = HOME
    def __init__(self, state, args):
        self.state = state
        self.client = RemoteAPIClient(host=args.coppelia_host, port=args.coppelia_port)
        self.client.socket.setsockopt(zmq.RCVTIMEO,10000)
        self.client.socket.setsockopt(zmq.SNDTIMEO,10000)
        self.sim = self.client.require('sim')
        sim = self.sim
        if sim.getSimulationState() != sim.simulation_stopped:
            raise RuntimeError('Pare a simulação atual antes de abrir a nova estufa.')
        for alias in ['/AgroBotPrototype','/AgroBotEstufa']:
            old = sim.getObject(alias, {'noError':True})
            if old != -1:
                sim.removeObjects(sim.getObjectsInTree(old))
        self.root = sim.createDummy(.01)
        sim.setObjectAlias(self.root, 'AgroBotEstufa')
        self.build()
        if not args.no_save_scene:
            sim.saveScene(str(args.scene_path))
        sim.startSimulation()

    def shape(self, size, pos, color, alias, parent=None, primitive=None, collidable=True):
        sim = self.sim
        h = sim.createPrimitiveShape(primitive if primitive is not None else sim.primitiveshape_cuboid, size, 0)
        sim.setObjectAlias(h,alias)
        sim.setObjectPosition(h,sim.handle_world,pos)
        sim.setShapeColor(h,None,sim.colorcomponent_ambient_diffuse,color)
        sim.setObjectInt32Param(h,sim.shapeintparam_static,1)
        properties = sim.objectspecialproperty_renderable | sim.objectspecialproperty_detectable_all
        if collidable:
            properties |= sim.objectspecialproperty_collidable
        sim.setObjectSpecialProperty(h, properties)
        sim.setObjectParent(h,self.root if parent is None else parent,True)
        return h

    def point_camera(self, camera, eye, target):
        sim = self.sim
        z = [target[i]-eye[i] for i in range(3)]
        length = math.sqrt(sum(v*v for v in z))
        z = [v/length for v in z]
        x = [-z[1],z[0],0]
        length = math.hypot(x[0],x[1])
        # A câmera apontada exatamente na vertical não tem projeção XY para
        # definir o eixo X. Escolha um eixo estável nesse caso degenerado.
        x = [1,0,0] if length < 1e-9 else [v/length for v in x]
        y = [z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]]
        sim.setObjectMatrix(camera,sim.handle_world,[x[0],y[0],z[0],eye[0],x[1],y[1],z[1],eye[1],x[2],y[2],z[2],eye[2]])

    def build(self):
        sim = self.sim
        self.floor = self.shape([12,16,.08],[0,.7,-.04],[.80,.78,.68],'Estufa_Piso')
        for x in [-1.9,1.9]:
            self.shape([1.6,10.5,.012],[x,-.4,.008],[.72,.70,.63],'Corredor')
        # Faixa de 8 cm que liga o docking aos quatro pontos de inspeção.
        # Ela fica alguns milímetros acima do corredor para evitar z-fighting,
        # mas não participa das colisões do robô.
        self.guide_line = []
        for a,b in zip(ROUTE,ROUTE[1:]):
            dx,dy = b[0]-a[0],b[1]-a[1]
            h = self.shape([math.hypot(dx,dy)+.008,.08,.004],
                           [(a[0]+b[0])/2,(a[1]+b[1])/2,.034],
                           [.005,.005,.005],'Linha_Guia_Preta',collidable=False)
            sim.setObjectOrientation(h,sim.handle_world,[0,0,math.atan2(dy,dx)])
            self.guide_line.append(h)
        for x in [-5.8,5.8]:
            self.shape([.12,15.6,.35],[x,.7,.175],[.60,.70,.66],'Limite_Lateral')
            for y in [-6.9,-3,0,3,8.3]:
                self.shape([.075,.075,2.7],[x,y,1.35],[.48,.61,.57],'Estufa_Coluna')
        for y in [-6.9,8.3]:
            self.shape([11.6,.10,.35],[0,y,.175],[.60,.70,.66],'Limite_Frontal')
            self.shape([11.6,.07,.07],[0,y,2.7],[.48,.61,.57],'Estufa_Travessa')
        self.indicators = {}
        self.leaves = {}
        self.photo_panels = {}
        for bed in self.state.beds:
            x,y = bed['x'], bed['y']
            self.shape([2.1,1.8,.18],[x,y,.09],[.31,.21,.13],f'Canteiro_{bed["id"]:02}_Solo')
            self.leaves[bed['id']] = []
            for dx in [-.65,0,.65]:
                for dy in [-.5,0,.5]:
                    self.shape([.04,.04,.36],[x+dx,y+dy,.34],[.22,.40,.18],'Planta_Caule',primitive=sim.primitiveshape_cylinder)
                    for lx,ly in [(-.11,0),(.1,.06),(0,-.1)]:
                        color = [.25,.55,.28]
                        if bed['scenario']=='yellowing' and dx==0:
                            color = [.64,.65,.22]
                        leaf = self.shape([.32,.23,.12],[x+dx+lx,y+dy+ly,.55],[*color],'Planta_Folha',primitive=sim.primitiveshape_spheroid)
                        self.leaves[bed['id']].append(leaf)
            self.indicators[bed['id']] = self.shape([.12,.12,.12],[x-1 if x>0 else x+1,y-.7,.38],[.5,.55,.55],f'Canteiro_{bed["id"]:02}_Status',primitive=sim.primitiveshape_spheroid)
            wp = sim.createDummy(.05)
            sim.setObjectAlias(wp,f'INSPECAO_CANTEIRO_{bed["id"]:02}')
            sim.setObjectPosition(wp,sim.handle_world,[*route_point(bed['route_distance']),.04])
            sim.setObjectParent(wp,self.root,True)
        self.dock = self.shape([1.2,.85,.025],[*HOME,.015],[.10,.50,.44],'START_DOCKING_STATION')
        self.shape([1.2,.85,.025],[*STOP,.015],[.72,.20,.13],'STOP',collidable=False)
        self.robot = sim.createDummy(.01)
        sim.setObjectAlias(self.robot,'AgroBot_Inspecao')
        sim.setObjectPosition(self.robot,sim.handle_world,[0,-5.1,0])
        sim.setObjectParent(self.robot,self.root,True)
        self.camera_pan, self.camera_tilt = build_body(self)
        self.camera_angles = (0., 0.)
        self.camera_target = (0., 0.)
        self.camera = sim.createVisionSensor(1|2|4,[640,400,0,0],[.02,8,math.radians(65),.025,0,0,.15,.2,.17,0,0])
        sim.setObjectAlias(self.camera,'Camera_Inspecao_RGB')
        self.point_camera(self.camera, [CAMERA_LENS_X,-5.1,CAMERA_PIVOT_Z], [1.,-5.1,CAMERA_PIVOT_Z])
        sim.setObjectParent(self.camera,self.camera_tilt,True)
        # Três sensores ortográficos de baixa resolução olham para o piso.
        # O robô avança no seu eixo local +X; por isso o conjunto fica 22 cm
        # à frente e é distribuído no eixo local Y (esquerda/centro/direita).
        self.line_sensors = []
        for name, lateral in [('Esquerdo',.10),('Central',0.),('Direito',-.10)]:
            sensor = sim.createVisionSensor(
                1|4,
                [16,16,0,0],
                [.01,.18,.055,.025,0,0,1,1,1,0,0],
            )
            sim.setObjectAlias(sensor,f'Sensor_Linha_{name}')
            sim.setObjectParent(sensor,self.robot,True)
            self.point_camera(sensor,[.22,-5.1+lateral,.075],[.22,-5.1+lateral,0])
            self.line_sensors.append(sensor)
        # Invisible conservative envelope probes the next footprint before moving.
        self.probe = self.shape([.86,.86,.85],[0,-5.1,.56],[1,0,0],'Envelope_Seguranca')
        sim.setObjectInt32Param(self.probe,sim.objintparam_visibility_layer,0)
        self.obstacles = sim.createCollection(0)
        sim.addItemToCollection(self.obstacles,sim.handle_all,-1,0)
        sim.addItemToCollection(self.obstacles,sim.handle_tree,self.robot,1)
        sim.addItemToCollection(self.obstacles,sim.handle_single,self.probe,1)
        self.demo_obstacle = self.shape([.65,.45,.7],[0,0,-3],[.78,.43,.16],'Caixa_Teste_Obstaculo')
        camera = sim.getObject('/DefaultCamera',{'noError':True})
        if camera != -1:
            self.point_camera(camera,[13,-17,18],[0,.7,0])
        self.move(*self.home,math.pi/2)
        self.update()

    def read_line_sensors(self):
        """Return normalized darkness (0=white, 1=black), left to right."""
        readings = []
        for sensor in self.line_sensors:
            self.sim.handleVisionSensor(sensor)
            image,resolution = self.sim.getVisionSensorImg(sensor,1)
            expected = resolution[0]*resolution[1]
            if len(image) != expected:
                raise RuntimeError('Imagem incompleta do sensor de linha')
            readings.append(1.0-sum(image)/(255.0*expected))
        return readings

    def move(self,x,y,heading):
        self.sim.setObjectPosition(self.robot,self.sim.handle_world,[x,y,0])
        self.sim.setObjectOrientation(self.robot,self.sim.handle_world,[0,0,heading])

    def blocked(self,x,y,heading):
        sim = self.sim
        sim.setObjectPosition(self.demo_obstacle,sim.handle_world,[x+.75*math.cos(heading),y+.75*math.sin(heading),.35] if self.state.obstacle else [0,0,-3])
        sim.setObjectPosition(self.probe,sim.handle_world,[x+.10*math.cos(heading),y+.10*math.sin(heading),.56])
        return sim.checkCollision(self.probe,self.obstacles)[0] > 0

    def aim(self,bed):
        sim = self.sim
        x, y, z = sim.getObjectPosition(self.camera_pan, sim.handle_world)
        heading = sim.getObjectOrientation(self.robot, sim.handle_world)[2]
        dx, dy = bed['x']-x, bed['y']-y
        yaw = (math.atan2(dy, dx)-heading+math.pi)%(2*math.pi)-math.pi
        self.camera_target = (yaw, math.atan2(z-.48, math.hypot(dx, dy)))

    def advance_camera(self, dt, tracking=True):
        """Move both visible pivots toward the target; report when aligned."""
        target = self.camera_target if tracking else (0., 0.)
        pan, tilt = self.camera_angles
        next_angles = []
        for current, goal, speed in zip((pan, tilt), target, (110, 75)):
            limit = math.radians(speed)*dt
            delta = goal-current
            next_angles.append(goal if abs(delta) <= limit else current+math.copysign(limit, delta))
        next_pan, next_tilt = next_angles
        if next_pan != pan:
            self.sim.setObjectOrientation(self.camera_pan, self.robot, [0,0,next_pan])
        if next_tilt != tilt:
            self.sim.setObjectOrientation(self.camera_tilt, self.camera_pan, [0,next_tilt,0])
        self.camera_angles = (next_pan, next_tilt)
        return self.camera_angles == target

    def capture(self,bed,key):
        self.sim.handleVisionSensor(self.camera)
        data,resolution = self.sim.getVisionSensorImg(self.camera)
        if len(data)!=resolution[0]*resolution[1]*3:
            raise RuntimeError('Imagem RGB incompleta')
        path = self.state.data_dir/'images'/f'{key}.png'
        path.write_bytes(png_rgb(data,*resolution))
        return path.name,'coppeliasim'

    def show_reference(self, bed, image_path, label):
        """Display the selected leaf photo in the actual inspection scene."""
        sim = self.sim
        previous = self.photo_panels.pop(bed['id'], None)
        if previous is not None:
            sim.removeObjects([previous])
        panel, _texture, _resolution = sim.createTexture(str(image_path), 2, [1.15, 1.15])
        sim.setObjectAlias(panel, f'Canteiro_{bed["id"]:02}_Folha_Referencia')
        sim.setObjectInt32Param(panel, sim.shapeintparam_static, 1)
        sim.setObjectSpecialProperty(panel, sim.objectspecialproperty_renderable | sim.objectspecialproperty_detectable_all)
        x, y = bed['x'], bed['y']
        waypoint = route_point(bed['route_distance'])
        dx, dy = waypoint[0]-x, waypoint[1]-y
        distance = math.hypot(dx, dy)
        front = .95 / distance if distance else 0
        self.point_camera(panel, [x+front*dx, y+front*dy, .65], [*waypoint, .85])
        sim.setObjectParent(panel, self.root, True)
        self.photo_panels[bed['id']] = panel
        color = ([.24, .55, .27] if 'healthy' in label.lower()
                 else [.63, .59, .23] if any(word in label.lower() for word in ('yellow', 'virus', 'curl'))
                 else [.45, .48, .24])
        for leaf in self.leaves[bed['id']]:
            sim.setShapeColor(leaf, None, sim.colorcomponent_ambient_diffuse, color)

    def capture_for_model(self, bed, key, bank):
        if not bank.by_crop.get(bed['crop']):
            filename, source = self.capture(bed, key)
            return dict(filename=filename, source=source, analysis_file=None,
                        analysis_state='unsupported_crop')
        filename = None
        source = 'coppeliasim'
        for attempt in range(1, 4):
            reference = prepare_reference(bank, bed['crop'], attempts=1)
            if reference['image'] is None:
                quality = reference['quality']
                continue
            staged = self.state.data_dir / 'images' / f'{key}-reference.jpg'
            reference['image'].save(staged, format='JPEG', quality=90)
            self.show_reference(bed, staged, reference['provenance']['dataset_label'])
            filename, source = self.capture(bed, key)
            camera = Image.open(self.state.data_dir / 'images' / filename).convert('RGB')
            width, height = camera.size
            side = int(min(width, height) * .6)
            left, top = (width-side)//2, (height-side)//2
            closeup = camera.crop((left, top, left+side, top+side)).resize((256, 256))
            quality = assess_quality(closeup)
            if quality['accepted']:
                analysis = self.state.data_dir / 'images' / f'{key}-modelo.jpg'
                closeup.save(analysis, format='JPEG', quality=90)
                return dict(filename=filename, source=source, analysis_file=analysis.name,
                            analysis_state='ready', capture_conditions=reference['conditions'],
                            capture_quality=quality, capture_attempts=attempt,
                            photo_provenance=reference['provenance'])
        if filename is None:
            filename, source = self.capture(bed, key)
        return dict(filename=filename, source=source, analysis_file=None,
                    analysis_state='poor_quality', capture_conditions=reference['conditions'],
                    capture_quality=quality, capture_attempts=3)

    def update(self):
        colors = {'NORMAL':[.18,.72,.42],'SUSPECT':[.95,.68,.13],'ALERT':[.88,.24,.18],'PENDING':[.5,.55,.55]}
        for b in self.state.beds:
            self.sim.setShapeColor(self.indicators[b['id']],None,self.sim.colorcomponent_ambient_diffuse,colors[(b['latest'] or {}).get('status','PENDING')])

    def close(self):
        try:
            self.sim.stopSimulation()
        except Exception:
            pass
