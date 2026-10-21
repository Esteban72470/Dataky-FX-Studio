"""Dataky FX Studio · boîte à outils pour créer des effets avec une IA.

Recherche d’assets, validation, rendu sans fenêtre, comparaison de variantes,
briques réutilisables, sauvegarde et export (Luau, .rbxmx). Utilisée par la ligne
de commande tool/fx.py et par le serveur MCP tool/fx_mcp.py. Bibliothèque standard
seulement ; le rendu appelle Node.js et Playwright (tool/fx_render.cjs).
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

if __package__:
    from .fx_schema import ValidationError, validate_project
else:
    from fx_schema import ValidationError, validate_project

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "editor" / "projects"
EXPORTS = ROOT / "exports"
RENDERS = ROOT / "rendus"
RENDERER = Path(__file__).with_name("fx_render.cjs")
COLLECTIONS = {"textures": ("textures.json", ""), "beams": ("beams/assets.json", "beams/"), "meshes": ("meshes/assets.json", "meshes/")}
LAYOUTS = {2: "Grid2x2", 4: "Grid4x4", 8: "Grid8x8"}
_catalogs: dict[str, list[dict[str, Any]]] = {}


class ToolError(RuntimeError):
    pass


# ---- Bibliothèque d’assets ----

def catalog(collection: str) -> list[dict[str, Any]]:
    if collection not in COLLECTIONS:
        raise ToolError("collection inconnue : textures, beams ou meshes")
    if collection not in _catalogs:
        path = ROOT / COLLECTIONS[collection][0]
        _catalogs[collection] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    return _catalogs[collection]


def describe_asset(item: dict[str, Any], collection: str) -> dict[str, Any]:
    prefix = COLLECTIONS[collection][1]
    image = prefix + item["image_path"] if item.get("image_path") and (ROOT / prefix / item["image_path"]).is_file() else None
    out = {"id": str(item.get("asset_id")), "uri": item.get("uri"), "name": item.get("name") or "", "tags": item.get("tags", []),
           "collection": collection, "kind": item.get("kind"), "image": image}
    grid = item.get("grid") or 0
    if collection == "textures" and item.get("kind") == "flipbook":
        out["flipbook"] = {"grid": grid, "FlipbookLayout": LAYOUTS.get(grid, "Custom" if grid else None),
                           "estimated": str(item.get("grid_source", "")).startswith("inferred")}
    if collection == "meshes":
        for reference in item.get("references", []):
            out[reference.get("label", "MeshId")] = reference.get("uri")
    return out


def search_assets(collection: str = "textures", tag: str | None = None, kind: str | None = None, query: str | None = None,
                  limit: int = 24, offset: int = 0) -> dict[str, Any]:
    """Filtre par tag (Impact, Slash, Smoke…), type (static / flipbook) et texte du nom ou ID."""
    items = catalog(collection)
    if tag:
        wanted = tag.lower()
        items = [item for item in items if any(t.lower() == wanted for t in item.get("tags", []))]
    if kind:
        items = [item for item in items if item.get("kind") == kind]
    if query:
        words = query.lower().split()
        items = [item for item in items if str(item.get("asset_id")) == query.strip()
                 or all(word in (item.get("name") or "").lower() for word in words)]
    limit = max(1, min(int(limit), 120))
    page = items[max(0, int(offset)):max(0, int(offset)) + limit]
    return {"collection": collection, "total": len(items), "offset": offset, "items": [describe_asset(item, collection) for item in page]}


def tags(collection: str = "textures") -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in catalog(collection):
        for tag in item.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))


# ---- Rendu par l’émulateur (Node + Playwright) ----

def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise ToolError("Node.js est introuvable : installez Node.js, puis `npm install -g playwright` et `npx playwright install chromium`.")
    return node


def _run_renderer(args: list[str], timeout: int = 240) -> dict[str, Any]:
    result = subprocess.run([_node(), str(RENDERER), *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if result.returncode != 0:
        raise ToolError((result.stderr or result.stdout).strip() or "rendu impossible")
    return json.loads(result.stdout)


def _out(out: str | Path | None, default: str) -> Path:
    path = Path(out) if out else RENDERS / default
    path = path if path.is_absolute() else ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text.strip()).strip("-.").lower()
    return slug[:60] or "effet"


def texture_sheet(items: list[dict[str, Any]], out: str | Path | None = None, columns: int = 6) -> Path:
    path = _out(out, "textures.png")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump([{"id": item["id"], "label": item.get("name") or ", ".join(item.get("tags", [])),
                    "path": item.get("image"), "grid": (item.get("flipbook") or {}).get("grid", 0)} for item in items], handle)
    try:
        _run_renderer(["--textures", handle.name, "--out", str(path), "--columns", str(columns)])
    finally:
        os.unlink(handle.name)
    return path


def render(projects: dict[str, Any] | list[dict[str, Any]], out: str | Path | None = None, times: list[float] | None = None,
           frames: int = 8, size: str = "480x270", auto_camera: bool = True, dummy: bool = True, background: str | None = None,
           ground: bool = True, seed: int = 1, camera: list[float] | None = None, columns: int = 4) -> dict[str, Any]:
    """Planche PNG d’un projet, ou d’une ligne par projet pour comparer des variantes."""
    projects = projects if isinstance(projects, list) else [projects]
    if not projects or len(projects) > 8:
        raise ToolError("1 à 8 projets par planche")
    validated = [validate_project(project) for project in projects]
    name = "comparaison" if len(validated) > 1 else _slug(validated[0].get("id") or validated[0]["name"])
    path = _out(out, f"{name}.png")
    files = []
    try:
        for project in validated:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
                json.dump(project, handle, ensure_ascii=False)
                files.append(handle.name)
        args = [*files, "--out", str(path), "--size", size, "--seed", str(seed), "--frames", str(frames), "--columns", str(columns)]
        if times:
            args += ["--times", ",".join(str(float(t)) for t in times)]
        if camera:
            args += ["--camera", ",".join(str(float(v)) for v in camera)]
        elif auto_camera:
            args.append("--auto-camera")
        if dummy:
            args.append("--dummy")
        if background:
            args += ["--background", background]
        if not ground:
            args.append("--no-ground")
        result = _run_renderer(args)
    finally:
        for file in files:
            os.unlink(file)
    result["image"] = str(path)
    return result


# ---- Projets ----

def _sibling(name: str):
    import importlib
    return importlib.import_module("." + name, __package__) if __package__ else importlib.import_module(name)


def validate(project: dict[str, Any]) -> dict[str, Any]:
    return validate_project(project)


def project_path(ident: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", ident or "") or ident in {".", ".."}:
        raise ToolError("identifiant de projet invalide")
    return PROJECTS / f"{ident}.json"


def load(ident: str) -> dict[str, Any]:
    path = project_path(ident)
    if not path.is_file():
        raise ToolError(f"projet introuvable : {ident}")
    return validate_project(json.loads(path.read_text(encoding="utf-8")))


def list_projects() -> list[dict[str, Any]]:
    out = []
    for path in sorted(PROJECTS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({"id": path.stem, "name": data.get("name"), "duration": data.get("duration"), "nodes": len(data.get("nodes", []))})
        except (OSError, ValueError):
            continue
    return out


def save(project: dict[str, Any]) -> dict[str, Any]:
    project = deepcopy(project)
    project.setdefault("id", _slug(project.get("name", "effet")))
    project = validate_project(project)
    path = project_path(project["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": project["id"], "path": str(path), "studio": f"http://127.0.0.1:48754/ (Projets → {project['name']})"}


def export(project: dict[str, Any], fmt: str = "rbxmx", out: str | Path | None = None) -> Path:
    project = validate_project(project)
    name = _slug(project.get("id") or project["name"])
    if fmt == "lua":
        data = _sibling("fx_export").export_project(project)
    elif fmt == "rbxmx":
        data = _sibling("fx_rbxmx").export_rbxmx(project)
    elif fmt == "json":
        data = json.dumps(project, ensure_ascii=False, indent=2) + "\n"
    else:
        raise ToolError("format : rbxmx, lua ou json")
    path = Path(out) if out else EXPORTS / f"{name}.{fmt}"
    path = path if path.is_absolute() else ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return path


__all__ = ["ToolError", "ValidationError", "search_assets", "tags", "texture_sheet", "render", "validate", "load", "save",
           "list_projects", "export", "describe_asset"]
