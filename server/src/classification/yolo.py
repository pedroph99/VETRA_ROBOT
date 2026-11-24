"""Inferência PlantVillage com o pré-processamento do checkpoint YOLOv5s-cls."""
import argparse
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import pathlib
import subprocess
import sys

COMMIT = "402e17ddf820996f51a191cbb798376e1144f069"


@contextmanager
def linux_checkpoint_paths():
    """Compatibilidade temporária para caminhos Linux gravados no checkpoint."""
    old = pathlib.PosixPath
    try:
        local = importlib.import_module("pathlib._local")
    except ModuleNotFoundError:
        local = None
    alias = local is None
    old_local = local.PosixPath if local is not None else None
    if alias:
        sys.modules["pathlib._local"] = pathlib
    if os.name == "nt":
        pathlib.PosixPath = pathlib.WindowsPath
        if local is not None:
            local.PosixPath = pathlib.WindowsPath
    try:
        yield
    finally:
        pathlib.PosixPath = old
        if local is not None:
            local.PosixPath = old_local
        if alias:
            sys.modules.pop("pathlib._local", None)


def load_model(repo, weights, device="cpu"):
    repo, weights = Path(repo).resolve(), Path(weights).resolve()
    if not weights.is_file():
        raise FileNotFoundError(f"Pesos não encontrados: {weights}")
    marker = repo / 'VETRA_REVISION.txt'
    actual = marker.read_text().strip() if marker.exists() else subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise ValueError(f"Use o commit {COMMIT} do YOLOv5; encontrado: {actual}")
    sys.path.insert(0, str(repo))
    import torch
    from models.yolo import ClassificationModel
    from utils.augmentations import classify_transforms

    # O checkpoint contém objetos Python completos. Carregar apenas pesos de origem conhecida.
    with linux_checkpoint_paths():
        checkpoint = torch.load(str(weights), map_location="cpu", weights_only=False)
    model = checkpoint["model"]
    if not isinstance(model, ClassificationModel):
        raise TypeError("Este programa espera um YOLOv5 ClassificationModel.")
    if len(model.names) != 38 or model.model[-1].linear.out_features != 38:
        raise ValueError("O checkpoint deve ter 38 classes e 38 saídas.")
    model = model.float().to(device).eval()
    # Corrige metadado herdado do pré-treino; não modifica os pesos.
    model.nc = len(model.names)
    return model, classify_transforms(224)


def predict(model, transform, bgr_image):
    import torch
    parameter = next(model.parameters())
    # A transformação oficial recebe BGR, recorta/redimensiona, converte RGB
    # e aplica (pixel/255 - mean)/std com as estatísticas ImageNet.
    tensor = transform(bgr_image).unsqueeze(0).to(device=parameter.device, dtype=parameter.dtype)
    with torch.inference_mode():
        logits = model(tensor)
        if logits.shape != (1, len(model.names)) or not torch.isfinite(logits).all():
            raise ValueError("Saída do modelo inválida.")
        probabilities = logits.softmax(dim=1)[0]
    values, indices = probabilities.topk(5)
    return [{"classe": model.names[int(i)], "probabilidade_softmax": float(v)}
            for v, i in zip(values.cpu(), indices.cpu())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("imagem", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).parent / "yolov5")
    parser.add_argument("--weights", type=Path, default=Path(__file__).parent / "best.pt")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--mostrar", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    import cv2
    import numpy as np
    image = cv2.imdecode(np.fromfile(args.imagem, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Não foi possível ler a imagem: {args.imagem}")
    model, transform = load_model(args.repo, args.weights, args.device)
    result = predict(model, transform, image)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload + "\n", encoding="utf-8")
    if args.mostrar:
        top = result[0]
        cv2.putText(image, f"{top['classe']}: {top['probabilidade_softmax']:.1%}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.imshow("PlantVillage - classificacao", image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
