"""Tracked VETRA bodywork, in the robot's local +X forward frame.

The reference is scaled to the greenhouse robot; dimensions are simulation
metres, not a manufacturing drawing. Decorative parts are non-collidable.
"""
import math
from pathlib import Path


WHITE = [.91, .93, .94]
BLACK = [.045, .055, .065]
RUBBER = [.025, .029, .034]
GOLD = [.78, .58, .15]
GREEN = [.10, .28, .22]
BLUE = [.07, .25, .65]
TRACK_HALF = .272
TRACK_RADIUS = .129
TRACK_Z = .156
TRACK_Y = .316
TRACK_WIDTH = .124
TRACK_PADS = 42
CAMERA_PIVOT_Z = .925
CAMERA_LENS_X = .035
BODY_SECTIONS = [
    (-.43, .15, .205, .385), (-.40, .205, .195, .435),
    (-.30, .245, .195, .515), (-.12, .25, .195, .565),
    (.06, .245, .195, .55), (.23, .225, .195, .485),
    (.36, .19, .205, .40), (.425, .145, .225, .355),
]


def loft(rings):
    """Join equal-size perimeter rings and close both ends."""
    count = len(rings[0])
    vertices = [value for ring in rings for point in ring for value in point]
    indices = []
    for row in range(len(rings)-1):
        for col in range(count):
            a, b = row*count+col, row*count+(col+1)%count
            c, d = b+count, a+count
            indices.extend([a, b, c, a, c, d])
    for row, reverse in [(0, True), (len(rings)-1, False)]:
        center = len(vertices)//3
        vertices.extend(sum(point[axis] for point in rings[row])/count for axis in range(3))
        for col in range(count):
            a, b = row*count+col, row*count+(col+1)%count
            indices.extend([center, b, a] if reverse else [center, a, b])
    return vertices, indices


def shell_mesh():
    # Rounded cross-sections: narrow nose, broad shoulders, low rear deck.
    rings = []
    for x, width, bottom, top in BODY_SECTIONS:
        center, radius = (top+bottom)/2, (top-bottom)/2
        ring = []
        for i in range(48):
            angle = 2*math.pi*i/48
            # Superellipse gives gently flattened panels and rounded corners.
            c, s = math.cos(angle), math.sin(angle)
            ring.append((x, width*math.copysign(abs(c)**.65, c),
                         center+radius*math.copysign(abs(s)**.75, s)))
        rings.append(ring)
    return loft(rings)


def top_panel_mesh(start, end, half_width):
    """Thin closed trim panel fitted to the curved shell rather than floating."""
    rings = []
    # Include the shell's section breaks to follow changes of slope exactly.
    samples = sorted({start, end, *(p[0] for p in BODY_SECTIONS if start < p[0] < end)})
    for x in samples:
        for left, right in zip(BODY_SECTIONS, BODY_SECTIONS[1:]):
            if left[0] <= x <= right[0]:
                t = (x-left[0])/(right[0]-left[0])
                width, bottom, top = [left[i]*(1-t)+right[i]*t for i in range(1, 4)]
                break
        upper = []
        for i in range(17):
            y = half_width*(1-2*i/16)
            cosine = (abs(y)/width)**(1/.65)
            z = (top+bottom)/2+(top-bottom)/2*(1-cosine*cosine)**(.75/2)
            upper.append((x, y, z+.005))
        rings.append(upper+[(px, py, pz-.004) for px, py, pz in reversed(upper)])
    return loft(rings)


def track_point(distance, radius=TRACK_RADIUS):
    """Position and pitch on the closed track loop, starting above the rear axle."""
    straight = 2*TRACK_HALF
    arc = math.pi*radius
    d = distance % (2*(straight+arc))
    if d < straight:
        return d-TRACK_HALF, TRACK_Z+radius, 0
    if d < straight+arc:
        a = (d-straight)/radius
        return TRACK_HALF+radius*math.sin(a), TRACK_Z+radius*math.cos(a), a
    if d < 2*straight+arc:
        return TRACK_HALF-(d-straight-arc), TRACK_Z-radius, math.pi
    a = math.pi+(d-2*straight-arc)/radius
    return -TRACK_HALF+radius*math.sin(a), TRACK_Z+radius*math.cos(a), a


def belt_mesh(y):
    """Closed rubber belt surface underneath the animated individual treads."""
    vertices, indices = [], []
    count = 64
    for i in range(count):
        x, z, a = track_point(i*2*(2*TRACK_HALF+math.pi*TRACK_RADIUS)/count)
        for dy, offset in [(-1, -.005), (1, -.005), (1, -.018), (-1, -.018)]:
            vertices.extend((x+offset*math.sin(a), y+dy*(TRACK_WIDTH/2-.006), z+offset*math.cos(a)))
        for j in range(4):
            k = (j+1)%4
            a0, b = i*4+j, i*4+k
            c, d = ((i+1)%count)*4+k, ((i+1)%count)*4+j
            indices.extend((a0, b, c, a0, c, d))
    return vertices, indices


def build_body(scene):
    sim = scene.sim
    origin = [0, -5.1, 0]

    def part(size, pos, color, alias, primitive=None, parent=None):
        return scene.shape(size, [pos[i]+origin[i] for i in range(3)],
                           color, alias, scene.robot if parent is None else parent,
                           primitive, collidable=False)

    def mesh(data, color, alias):
        vertices, indices = data
        handle = sim.createShape(0, math.radians(35), vertices, indices)
        sim.setObjectAlias(handle, alias)
        position = sim.getObjectPosition(handle, sim.handle_world)
        sim.setObjectPosition(handle, sim.handle_world,
                              [position[i]+origin[i] for i in range(3)])
        sim.setShapeColor(handle, None, sim.colorcomponent_ambient_diffuse, color)
        sim.setObjectInt32Param(handle, sim.shapeintparam_static, 1)
        sim.setObjectSpecialProperty(handle, sim.objectspecialproperty_renderable)
        sim.setObjectParent(handle, scene.robot, True)
        return handle

    part([.86, .49, .032], [0, 0, .195], GOLD, 'Chassi_Esteiras')
    mesh(shell_mesh(), WHITE, 'Carcaca_Branca')
    part([.76, .46, .025], [0, 0, .22], BLACK, 'Saia_Inferior_Preta')
    # New tracked prototype: blue battery and driver on the lower deck,
    # breadboard/control electronics on a raised rear platform (design 08).
    part([.27, .20, .076], [-.17, 0, .255], BLUE, 'Interior_Bateria_Azul')
    for x in [-.235, -.10]:
        part([.012, .205, .079], [x, 0, .255], BLACK, 'Interior_Cinta_Bateria')
    for x in [-.30, -.015]:
        for y in [-.13, .13]:
            part([.014, .014, .145], [x, y, .287], GOLD, 'Interior_Coluna')
    part([.31, .29, .014], [-.16, 0, .365], BLACK, 'Interior_Plataforma_Controle')
    part([.26, .235, .025], [-.16, 0, .385], WHITE, 'Interior_Protoboard')
    part([.20, .06, .012], [-.16, .035, .407], BLUE, 'Interior_Placa_Controle')
    part([.055, .04, .012], [-.15, .035, .420], BLACK, 'Interior_Chip_Controle')
    for x in [-.24, -.21, -.18, -.15, -.12, -.09]:
        for y in [-.065, .089]:
            part([.009, .012, .003], [x, y, .400], BLACK, 'Interior_Contatos_Protoboard')
    part([.17, .20, .012], [.22, -.025, .228], [.60, .045, .035], 'Interior_Driver_Motores')
    for y in [-.09, .045]:
        part([.045, .038, .031], [.275, y, .250], BLUE, 'Interior_Borne_Driver')
    for x in [.175, .189, .203, .217, .231]:
        part([.006, .075, .065], [x, -.02, .266], BLACK, 'Interior_Dissipador_Driver')
    part([.10, .075, .012], [.05, .13, .230], BLUE, 'Interior_Conversor_DC_DC')
    part([.04, .035, .025], [.05, .13, .250], GOLD, 'Interior_Indutor')
    for x in [.015, .085]:
        part([.016, .016, .026], [x, .13, .251], BLACK, 'Interior_Capacitor', sim.primitiveshape_cylinder)
    for side in [-1, 1]:
        motor = part([.046, .046, .12], [.20, side*.17, .155], [.45, .47, .48],
                     'Interior_Motor', sim.primitiveshape_cylinder)
        sim.setObjectOrientation(motor, sim.handle_world, [math.pi/2, 0, 0])
    part([.035, .035, .16], [-.06, 0, .49], BLACK, 'Interior_Suporte_Camera')

    def wire(points, color):
        for a, b in zip(points, points[1:]):
            vector = [b[i]-a[i] for i in range(3)]
            length = math.sqrt(sum(v*v for v in vector))
            handle = part([.005, .005, length], [(a[i]+b[i])/2 for i in range(3)],
                          color, 'Interior_Fio', sim.primitiveshape_cylinder)
            dx, dy, dz = [v/length for v in vector]
            quaternion = [-dy, dx, 0, 1+dz] if dz > -.99999 else [1, 0, 0, 0]
            norm = math.sqrt(sum(v*v for v in quaternion))
            sim.setObjectQuaternion(handle, [v/norm for v in quaternion], sim.handle_world)

    for i, color in enumerate([[.8,.025,.02], [.025,.025,.025], [.85,.65,.02], [.05,.45,.21]]):
        dy = i*.011
        wire([[-.25,-.08+dy,.405],[-.25,-.15+dy,.48],[.11,-.15+dy,.47],
              [.24,-.13+dy,.26]], color)
    wire([[-.04,.08,.27],[.02,.08,.31],[.05,.13,.27]], [.8,.025,.02])
    wire([[-.04,.065,.27],[.035,.065,.31],[.07,.13,.27]], BLACK)
    wire([[-.16,.13,.54],[-.16,.17,.50],[-.25,.17,.43],[-.25,.05,.41]], [.8,.025,.02])
    # Mounting holes along the exposed yellow deck, represented as dark insets.
    for x in [-.37, -.28, -.19, -.10, 0, .10, .19, .28, .37]:
        for y in [-.218, .218]:
            part([.009, .009, .002], [x, y, .212], BLACK, 'Chassi_Furo', sim.primitiveshape_cylinder)
    pitch = 2*(2*TRACK_HALF+math.pi*TRACK_RADIUS)/TRACK_PADS
    for side, name in [(1, 'Esquerda'), (-1, 'Direita')]:
        y = side*TRACK_Y
        mesh(belt_mesh(y), RUBBER, f'Esteira_{name}')
        for x in [-TRACK_HALF, TRACK_HALF]:
            sprocket = part([.228, .228, .089], [x, y, TRACK_Z], GOLD,
                            f'Roda_{name}_{"Traseira" if x < 0 else "Frontal"}', sim.primitiveshape_cylinder)
            sim.setObjectOrientation(sprocket, sim.handle_world, [math.pi/2, 0, 0])
            for angle in [0, 2*math.pi/3, 4*math.pi/3]:
                part([.025, .012, .025], [x+.067*math.cos(angle), y+side*.05,
                     TRACK_Z+.067*math.sin(angle)], BLACK, 'Marca_Roda', parent=sprocket)
        part([.58, .017, .105], [0, side*.374, TRACK_Z], GREEN, 'Longarina_Esteira')
        for x in [-.235, 0, .235]:
            axle = part([.026, .026, .009], [x, side*.386, TRACK_Z], BLACK,
                        'Fixacao_Longarina', sim.primitiveshape_cylinder)
            sim.setObjectOrientation(axle, sim.handle_world, [math.pi/2, 0, 0])
        for i in range(TRACK_PADS):
            x, z, a = track_point(i*pitch)
            pad = part([pitch*.76, TRACK_WIDTH, .016], [x, y, z], [.07, .078, .082],
                       f'Patim_{name}_{i:02d}')
            sim.setObjectOrientation(pad, sim.handle_world, [0, a, 0])

    # The scene script keeps the tracks animated after the scene is reopened.
    lua = Path(__file__).with_name('track_animation.lua').read_text(encoding='utf-8')
    params = f'local half, radius, z, gauge, count, wheelRadius = {TRACK_HALF}, {TRACK_RADIUS}, {TRACK_Z}, {TRACK_Y}, {TRACK_PADS}, 0.114\n'
    animator = sim.createScript(sim.scripttype_simulation, params+lua, 0, 'lua')
    sim.setObjectAlias(animator, 'Animacao_Esteiras')
    sim.setObjectParent(animator, scene.robot, True)

    # Black inset following the hood slope, with a level service cover aft.
    mesh(top_panel_mesh(.015, .26, .102), BLACK, 'Capo_Preto')
    mesh(top_panel_mesh(-.31, -.17, .10), BLACK, 'Tampa_Traseira')
    for side in [-1, 1]:
        for x in [-.244, -.199, -.154]:
            part([.027, .012, .044], [x, side*.243, .368], BLACK, 'Ventilacao_Lateral')
    part([.045, .036, .016], [-.16, .13, .552], [.60, .035, .025], 'Chave_Gangorra')
    part([.024, .28, .115], [.415, 0, .29], BLACK, 'Painel_Sensores_Frontal')
    part([.012, .26, .095], [.396, 0, .29], BLUE, 'Interior_Placa_HC_SR04')
    for y in [-.078, .078]:
        sensor = part([.083, .083, .025], [.437, y, .29], [.67, .70, .73],
                      'Sensor_Ultrassonico_Aro', sim.primitiveshape_cylinder)
        sim.setObjectOrientation(sensor, sim.handle_world, [0, math.pi/2, 0])
        center = part([.062, .062, .028], [.442, y, .29], BLACK,
                      'Sensor_Ultrassonico_Centro', sim.primitiveshape_cylinder)
        sim.setObjectOrientation(center, sim.handle_world, [0, math.pi/2, 0])
    part([.035, .34, .028], [.445, 0, .215], BLACK, 'Para_Choque_Frontal')
    part([.018, .31, .047], [.432, 0, .154], BLACK, 'Barra_QTR8A_Representacao')
    for i in range(8):
        part([.011, .016, .017], [.446, (i-3.5)*.036, .15], BLUE, 'Canal_QTR8A')

    part([.13, .14, .035], [-.06, 0, .57], BLACK, 'Base_Camera')
    part([.045, .045, .28], [-.06, 0, .725], BLACK, 'Mastro_Camera')
    def pivot(alias, parent):
        handle = sim.createDummy(.005)
        sim.setObjectAlias(handle, alias)
        sim.setObjectPosition(handle, sim.handle_world, [0, origin[1], CAMERA_PIVOT_Z])
        sim.setObjectParent(handle, parent, True)
        return handle

    pan = pivot('Camera_Eixo_Pan', scene.robot)
    tilt = pivot('Camera_Eixo_Tilt', pan)
    part([.082, .08, .049], [-.035, 0, .878], BLUE, 'Servo_Pan')
    part([.075, .022, .077], [-.035, -.082, .897], BLACK, 'Suporte_Pan_Tilt', parent=pan)
    part([.062, .04, .055], [-.04, -.093, CAMERA_PIVOT_Z], BLUE, 'Servo_Tilt', parent=pan)
    part([.09, .15, .12], [-.035, 0, CAMERA_PIVOT_Z], BLACK, 'Camera_ESP32_Representacao', parent=tilt)
    lens = part([.060, .060, .025], [.02, 0, .925], [.12, .15, .18],
                'Camera_Lente', sim.primitiveshape_cylinder, tilt)
    sim.setObjectOrientation(lens, sim.handle_world, [0, math.pi/2, 0])
    for y in [-.054, .054]:
        part([.012, .023, .025], [.016, y, .944], [.87, .93, 1.0], 'Camera_LED', parent=tilt)
    ui_lua = Path(__file__).with_name('shell_control.lua').read_text(encoding='utf-8')
    shell_ui = sim.createScript(sim.scripttype_simulation, ui_lua, 0, 'lua')
    sim.setObjectAlias(shell_ui, 'Controle_Carcaca')
    sim.setObjectParent(shell_ui, scene.robot, True)
    return pan, tilt
