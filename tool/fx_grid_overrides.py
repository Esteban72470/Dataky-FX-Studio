"""Manual flipbook-grid confirmations, kept outside the immutable catalogue."""
from __future__ import annotations

import json
from pathlib import Path
import re

DEFAULT_PATH = Path(__file__).with_name("grid_overrides.json")
SUPPORTED_GRIDS = (2, 4, 8)


def _asset_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)) or int(value) <= 0:
        raise ValueError("ID de texture numérique strictement positif requis")
    return str(value)


def _grid(value):
    if isinstance(value, bool) or not isinstance(value, int) or value not in SUPPORTED_GRIDS:
        raise ValueError("grille carrée 2, 4 ou 8 requise")
    return value


def read_grid_overrides(path=None):
    path = Path(path) if path is not None else DEFAULT_PATH
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1 or not isinstance(data.get("grids"), dict):
        raise ValueError("fichier de surcharges de grille invalide (version 1 et objet grids requis)")
    return {_asset_id(asset_id): _grid(grid) for asset_id, grid in data["grids"].items()}


def confirm_grid(asset_id, grid, *, path=None):
    asset_id, grid = _asset_id(asset_id), _grid(grid)
    path = Path(path) if path is not None else DEFAULT_PATH
    grids = read_grid_overrides(path)
    grids[asset_id] = grid
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "grids": grids}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"texture": asset_id, "grid": grid, "confirmed": True, "path": str(path)}
