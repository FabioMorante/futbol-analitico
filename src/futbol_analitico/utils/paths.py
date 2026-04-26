from __future__ import annotations

from pathlib import Path
from futbol_analitico.config import ROOT_DIR, load_settings


def get_data_paths() -> dict[str, Path]:
    settings = load_settings()
    base_paths = settings["paths"]

    paths = {
        "raw": ROOT_DIR / base_paths["raw"],
        "interim": ROOT_DIR / base_paths["interim"],
        "audit": ROOT_DIR / base_paths["audit"],
        "curated": ROOT_DIR / base_paths["curated"],
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths