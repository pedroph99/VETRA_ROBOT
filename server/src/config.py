"""Caminhos absolutos, independentes da pasta de onde o comando é chamado."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = PROJECT_ROOT / "server"
SCENES_DIR = PROJECT_ROOT / "robot" / "scenes"
TEMPLATES_DIR = SERVER_DIR / "templates"
DATA_DIR = Path(os.environ.get("VETRA_DATA_DIR", SERVER_DIR / "data")).resolve()
