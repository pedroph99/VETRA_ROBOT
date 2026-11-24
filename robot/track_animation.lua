-- Visual locomotion follows the pose supplied by the inspection controller.
-- Track dimensions are prepended by robot_body.py, shared with the meshes.
local sim = require('sim')
local robot, previous, tracks
local straight = 2 * half
local arc = math.pi * radius
local perimeter = 2 * (straight + arc)

local function point(distance)
    local d = distance % perimeter
    if d < straight then return d-half, z+radius, 0 end
    if d < straight+arc then
        local a = (d-straight)/radius
        return half+radius*math.sin(a), z+radius*math.cos(a), a
    end
    if d < 2*straight+arc then return half-(d-straight-arc), z-radius, math.pi end
    local a = math.pi+(d-2*straight-arc)/radius
    return -half+radius*math.sin(a), z+radius*math.cos(a), a
end

function sysCall_init()
    robot = sim.getObjectParent(sim.getObject('.'))
    previous = sim.getObjectPosition(robot, sim.handle_world)
    previous[4] = sim.getObjectOrientation(robot, sim.handle_world)[3]
    tracks = {Esquerda={side=1, phase=0, wheelAngle=0, pads={}, wheels={}}, Direita={side=-1, phase=0, wheelAngle=0, pads={}, wheels={}}}
    for _, h in ipairs(sim.getObjectsInTree(robot, sim.sceneobject_shape, 1)) do
        local side, index = sim.getObjectAlias(h):match('^Patim_(%a+)_(%d+)$')
        if side then tracks[side].pads[tonumber(index)] = h end
        local wheelSide = sim.getObjectAlias(h):match('^Roda_(%a+)_%a+$')
        if wheelSide and tracks[wheelSide] then table.insert(tracks[wheelSide].wheels, h) end
    end
end

function sysCall_sensing()
    local pose = sim.getObjectPosition(robot, sim.handle_world)
    local yaw = sim.getObjectOrientation(robot, sim.handle_world)[3]
    local deltaYaw = (yaw-previous[4]+math.pi)%(2*math.pi)-math.pi
    local midYaw = previous[4]+deltaYaw/2
    local dx, dy = pose[1]-previous[1], pose[2]-previous[2]
    local distance = dx*math.cos(midYaw)+dy*math.sin(midYaw)
    previous = {pose[1], pose[2], pose[3], yaw}
    -- Repositioning between scenes or test checkpoints isn't travel.
    if dx*dx+dy*dy > 0.25 or math.abs(deltaYaw) > math.pi/2 then return end
    if math.abs(distance)+math.abs(deltaYaw) < 1e-8 then return end
    for _, track in pairs(tracks) do
        local travel = distance - track.side*gauge*deltaYaw
        track.phase = (track.phase + travel) % perimeter
        track.wheelAngle = (track.wheelAngle + travel/wheelRadius) % (2*math.pi)
        for _, h in ipairs(track.wheels) do
            -- R_y(angle) * R_x(pi/2): spin around the fixed lateral axle,
            -- never yaw the axle with respect to the chassis.
            local s, c = math.sin(track.wheelAngle/2), math.cos(track.wheelAngle/2)
            local root = math.sqrt(0.5)
            sim.setObjectQuaternion(h, {root*c, root*s, -root*s, root*c}, robot)
        end
        for i, h in pairs(track.pads) do
            local x, height, a = point(i*perimeter/count+track.phase)
            sim.setObjectPose(h, {x, track.side*gauge, height, 0, math.sin(a/2), 0, math.cos(a/2)}, robot)
        end
    end
end
