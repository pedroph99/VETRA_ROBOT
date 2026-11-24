"""Classificação simulada; ponto de substituição pelo serviço do modelo."""
PROBLEMS = {
    'normal': ('NORMAL', 'Nenhuma alteração aparente', None, 'Nenhuma'),
    'aphids': ('ALERT', 'Possível presença de pulgões', .93, 'Direta'),
    'whitefly': ('ALERT', 'Possível presença de mosca-branca', .89, 'Direta'),
    'yellowing': ('SUSPECT', 'Amarelecimento foliar; possível sintoma associado a pragas', .67, 'Indireta'),
    'curling': ('SUSPECT', 'Enrolamento foliar; possível sintoma associado a pragas', .72, 'Indireta'),
}

class SimulatedDetector:
    """Replace this adapter with an image model without changing the mission controller."""
    def analyze(self, image_path, bed):
        status, problem, confidence, detection = PROBLEMS[bed['scenario']]
        return dict(status=status, problem=problem, confidence=confidence, detection=detection, simulated=True)
