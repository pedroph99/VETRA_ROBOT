"""Operações de inspeção, agenda, histórico e exportação."""
import csv
import io

def command(state, value):
    with state.lock:
        if state.controller is None:
            raise ValueError("Controlador indisponível.")
        state.controller.command(value)

def update_schedule(state, data):
    with state.lock:
        state.settings = dict(enabled=data.enabled, times=sorted(set(data.times)), days=sorted(set(data.days)))
        state.store.save("schedule", state.settings)
        state.log("Programação de rondas atualizada.")

def update_scenario(state, bed_id, scenario):
    with state.lock:
        if not 1 <= bed_id <= len(state.beds):
            raise LookupError("Canteiro inexistente.")
        if state.classification_mode == 'model':
            raise ValueError('Condição manual não controla a inferência real. A foto é sorteada pela cultura.')
        state.beds[bed_id - 1]["scenario"] = scenario
        state.store.save("scenarios", {str(b["id"]): b["scenario"] for b in state.beds})
        state.log(f"Cenário de teste do canteiro {bed_id:02} alterado. Resultado será registrado na próxima inspeção.")

def update_obstacle(state, enabled):
    with state.lock:
        state.obstacle = enabled
        state.log("Obstáculo de demonstração " + ("ativado." if enabled else "removido."))

def list_inspections(state, bed_id, status, limit, offset):
    with state.lock:
        rows = state.store.read("inspection", 1000000)
        rows = [r for r in rows if (bed_id is None or r["bed_id"] == bed_id) and (not status or r["status"] == status)]
        return dict(items=rows[offset:offset + limit], total=len(rows))

def export_csv(state):
    with state.lock:
        records = state.store.read("inspection", 1000000)
    out = io.StringIO()
    fields = ["id", "mission_id", "time", "greenhouse", "bed_id", "status", "problem",
              "confidence", "detection", "simulated", "crop", "predicted_class", "analysis_state",
              "photo_simulated", "image", "camera_image", "image_source", "position", "interpretation", "photo_provenance"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return "\ufeff" + out.getvalue()
