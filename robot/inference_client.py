"""Send the image captured by the scene; labels remain audit-only metadata."""

import hashlib
import json
import random
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PHOTO_BANK = Path(__file__).resolve().parent / 'simulation_photos'


class PhotoBank:
    def __init__(self, root=PHOTO_BANK, rng=None):
        self.root = Path(root).resolve()
        self.rng = rng or random.SystemRandom()
        self.manifest = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        self.by_crop = {}
        for row in self.manifest['images']:
            path = (self.root / row['file']).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError('Foto ausente ou caminho inválido no banco de simulação.')
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError(f"Foto alterada: {row['file']}")
            self.by_crop.setdefault(row['crop'], []).append(row)

    def choose(self, crop):
        candidates = self.by_crop.get(crop)
        return self.rng.choice(candidates) if candidates else None


class HttpDetector:
    background = True

    def __init__(self, url, bank=None):
        self.url = url.rstrip('/')
        self.bank = bank or PhotoBank()

    def analyze(self, image_path, bed):
        capture = bed.get('capture')
        if capture is None:
            raise ValueError('Captura vinculada ao canteiro ausente')
        state = capture['analysis_state']
        if state != 'ready':
            reason = ('Cultura sem fotos compatíveis ou não suportada; sem diagnóstico'
                      if state == 'unsupported_crop' else
                      'Imagem sem qualidade suficiente; nova inspeção necessária')
            return dict(status='SUSPECT', problem=reason, confidence=None,
                        detection='Não analisada', simulated=False, inconclusive=True,
                        crop=bed['crop'], analysis_state=state,
                        **{key: capture[key] for key in
                           ('capture_conditions', 'capture_quality', 'capture_attempts')
                           if key in capture})
        analysis_path = Path(image_path).with_name(capture['analysis_file'])
        if not analysis_path.is_file():
            raise FileNotFoundError('Imagem capturada para análise ausente')
        content_type = 'image/png' if analysis_path.suffix.lower() == '.png' else 'image/jpeg'
        request = Request(
            self.url + '/api/classification/predict?' + urlencode({'crop': bed['crop']}),
            data=analysis_path.read_bytes(),
            headers={'Content-Type': content_type}, method='POST')
        # The filename, scenario and dataset label are not sent to the API.
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
        if result.get('status') not in ('NORMAL', 'SUSPECT', 'ALERT') or 'top5' not in result:
            raise ValueError('Resposta de inferência inválida')
        result.update(
            analysis_state='completed', analysis_image=f'/images/{analysis_path.name}',
            camera_image=f'/images/{Path(image_path).name}',
            photo_simulated=True, capture_conditions=capture['capture_conditions'],
            capture_quality=capture['capture_quality'],
            capture_attempts=capture['capture_attempts'],
            photo_provenance=capture['photo_provenance'],
        )
        return result
