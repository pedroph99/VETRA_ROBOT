"""Baixa pequenas amostras PlantVillage rastreáveis para a simulação, não para avaliação."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a"
DEST = ROOT / "robot/simulation_photos"


def fetch(url):
    with urlopen(
        Request(url, headers={"User-Agent": "VETRA-photo-setup"}), timeout=60
    ) as response:
        return response.read()


def prepare(count=3):
    knowledge = json.loads(
        (ROOT / "server/knowledge/pragas_sintomas.json").read_text(encoding="utf-8")
    )
    rows = []
    for label in knowledge["classes"]:
        crop = next(
            c
            for c, prefix in knowledge["culturas"].items()
            if label.startswith(prefix + "___")
        )
        url = f"https://api.github.com/repos/spMohanty/PlantVillage-Dataset/contents/raw/color/{quote(label, safe='')}?ref={COMMIT}"
        listing = json.loads(fetch(url))
        candidates = sorted(
            (
                item
                for item in listing
                if item["name"].lower().endswith((".jpg", ".jpeg", ".png"))
            ),
            key=lambda item: item["name"],
        )[:count]
        for item in candidates:
            rows.append(
                dict(
                    crop=crop,
                    label=label,
                    file=f"{label}/{item['name']}",
                    url=item["download_url"],
                    git_blob=item["sha"],
                )
            )

    def download(row):
        target = DEST / row["file"]
        data = target.read_bytes() if target.exists() else fetch(row["url"])
        blob = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        if blob != row["git_blob"]:
            raise ValueError(f"Hash inválido: {row['file']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        row["sha256"] = hashlib.sha256(data).hexdigest()

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, rows))
    manifest = dict(
        dataset="spMohanty/PlantVillage-Dataset",
        commit=COMMIT,
        purpose="Simulação; não é teste independente do treinamento.",
        images=rows,
    )
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(rows)} fotos verificadas em {DEST}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.per_class <= 100:
        parser.error("--per-class deve estar entre 1 e 100")
    prepare(args.per_class)
