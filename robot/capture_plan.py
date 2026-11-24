"""Select a crop-matched reference and preserve its provenance outside inference."""

from robot.capture_quality import assess_quality, vary_capture


def prepare_reference(bank, crop, attempts=3):
    row = bank.choose(crop)
    if row is None:
        return None
    for number in range(1, attempts + 1):
        source = bank.root / row['file']
        image, conditions = vary_capture(source, bank.rng)
        quality = assess_quality(image)
        if quality['accepted']:
            return dict(image=image, conditions=conditions, quality=quality,
                        attempts=number, provenance=dict(
                            dataset=bank.manifest['dataset'],
                            commit=bank.manifest['commit'], file=row['file'],
                            dataset_label=row['label'], sha256=row['sha256'],
                            note='Rótulo de auditoria, não enviado à inferência; amostra não independente.'))
        row = bank.choose(crop)
    return dict(image=None, conditions=conditions, quality=quality,
                attempts=attempts, provenance=None)
