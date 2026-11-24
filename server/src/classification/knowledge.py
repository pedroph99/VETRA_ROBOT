"""Regras transparentes de triagem, separadas dos escores do classificador."""

import json
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).resolve().parents[2] / "knowledge/pragas_sintomas.json"


class KnowledgeBase:
    def __init__(self, path=KNOWLEDGE_PATH, threshold=0.70):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.threshold = (
            threshold  # Heurística de triagem, não limiar clínico validado.
        )

    def interpret(self, top5, crop):
        top = top5[0]
        label, score = top["classe"], top["probabilidade_softmax"]
        prefix = self.data["culturas"].get(crop)
        warnings = list(self.data["limites"])
        reason = None
        if prefix is None:
            reason = "Cultura não suportada nesta integração"
        elif not label.startswith(prefix + "___"):
            reason = "Cultura prevista diverge da cultura do canteiro"
        elif score < self.threshold:
            reason = "Escore abaixo do limiar de triagem (70%)"
        entry = self.data["classes"].get(
            label, {"nome": label, "categoria": "nao_mapeada"}
        )
        healthy = entry["categoria"] == "saudavel"
        associations = (
            []
            if reason or healthy
            else [
                {**p, "fontes": [self.data["fontes"][f] for f in p["fontes"]]}
                for p in self.data["pragas"]
                if crop in p["culturas"] and label in p["classes_relacionadas"]
            ]
        )
        if reason:
            warnings.insert(
                0,
                reason
                + "; resultado inconclusivo, sem associação automática a pragas.",
            )
        return dict(
            status="SUSPECT" if reason else ("NORMAL" if healthy else "ALERT"),
            problem=reason or ("Compatível com: " + entry["nome"]),
            confidence=score,
            detection="Classificação de imagem",
            simulated=False,
            crop=crop,
            predicted_class=label,
            top5=top5,
            inconclusive=bool(reason),
            interpretation=dict(
                knowledge_version=self.data["revisao"],
                symptoms=[] if reason else entry.get("sintomas_tipicos", []),
                possible_causes=associations,
                warnings=warnings,
                disease_hypothesis=None if reason or healthy else entry["nome"],
                sources=[
                    self.data["fontes"][f]
                    for f in entry.get("fontes", ["plantvillage"])
                ],
                next_step="Inspecionar a planta e confirmar a hipótese com profissional habilitado; não aplicar tratamento automaticamente.",
            ),
        )
