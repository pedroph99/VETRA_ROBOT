-- The button exists while simulation is running and restores the original layers.
local sim = require('sim')
local simUI = require('simUI')
local ui, parts, visible

function setShellVisible(show)
    visible = show
    for _, part in ipairs(parts) do
        sim.setObjectInt32Param(part.handle, sim.objintparam_visibility_layer, visible and part.layer or 0)
    end
    simUI.setButtonText(ui, 1, visible and 'Mostrar interior' or 'Recolocar carcaça')
    return visible
end

function toggleShell()
    return setShellVisible(not visible)
end

function getShellState()
    return visible, #parts, ui ~= nil
end

function sysCall_init()
    local robot = sim.getObjectParent(sim.getObject('.'))
    local names = {Carcaca_Branca=true, Capo_Preto=true, Tampa_Traseira=true,
                   Ventilacao_Lateral=true, Painel_Sensores_Frontal=true,
                   Saia_Inferior_Preta=true, Para_Choque_Frontal=true}
    parts = {}
    for _, h in ipairs(sim.getObjectsInTree(robot, sim.sceneobject_shape, 1)) do
        if names[sim.getObjectAlias(h)] then
            table.insert(parts, {handle=h, layer=sim.getObjectInt32Param(h, sim.objintparam_visibility_layer)})
        end
    end
    visible = true
    ui = simUI.create('<ui title="Interior do VETRA" closeable="false" resizable="false" placement="relative" position="20,20"><button text="Mostrar interior" on-click="toggleShell" id="1"/></ui>')
end

function sysCall_cleanup()
    if ui then simUI.destroy(ui) end
    if visible == false then
        for _, part in ipairs(parts) do
            sim.setObjectInt32Param(part.handle, sim.objintparam_visibility_layer, part.layer)
        end
    end
end
