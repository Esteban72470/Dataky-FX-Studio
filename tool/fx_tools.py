"""Dataky FX Studio · boîte à outils pour créer des effets avec une IA.

Recherche d’assets, validation, rendu sans fenêtre, comparaison de variantes,
briques réutilisables, sauvegarde et export (Luau, .rbxmx). Utilisée par la ligne
de commande tool/fx.py et par le serveur MCP tool/fx_mcp.py. Bibliothèque standard
seulement ; le rendu appelle Node.js et Playwright (tool/fx_render.cjs).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
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
_catalog_fingerprints: dict[str, tuple[str, str]] = {}
_catalog_lock = threading.RLock()
MAX_CATALOG_BYTES = 64 * 1024 * 1024


class ToolError(RuntimeError):
    pass


# ---- Bibliothèque d’assets ----

def catalog(collection: str) -> list[dict[str, Any]]:
    """Read the current catalogue, reusing parsing only for identical file bytes.

    Size/mtime alone miss edits made by an external catalogue writer. Hashing the
    current bounded bytes also detects same-size replacements and root changes.
    Missing or malformed files never silently return a prior catalogue snapshot.
    """
    if collection not in COLLECTIONS:
        raise ToolError("collection inconnue : textures, beams ou meshes")
    path = (ROOT / COLLECTIONS[collection][0]).resolve()
    with _catalog_lock:
        try:
            with path.open("rb") as source:
                content = source.read(MAX_CATALOG_BYTES + 1)
        except FileNotFoundError:
            _catalogs.pop(collection, None)
            _catalog_fingerprints.pop(collection, None)
            return []
        except OSError as exc:
            raise ToolError(f"Catalogue {collection} illisible : {exc}") from exc
        if len(content) > MAX_CATALOG_BYTES:
            raise ToolError(f"Catalogue {collection} limité à 64 Mio")
        fingerprint = (str(path), hashlib.sha256(content).hexdigest())
        if collection in _catalogs and _catalog_fingerprints.get(collection) == fingerprint:
            return _catalogs[collection]
        try:
            rows = json.loads(content.decode("utf-8-sig"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ToolError(f"Catalogue {collection} JSON invalide : {exc}") from exc
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ToolError(f"Catalogue {collection} : liste d'assets JSON requise")
        _catalogs[collection] = rows
        _catalog_fingerprints[collection] = fingerprint
        return rows


def describe_asset(item: dict[str, Any], collection: str) -> dict[str, Any]:
    prefix = COLLECTIONS[collection][1]
    image = prefix + item["image_path"] if item.get("image_path") and (ROOT / prefix / item["image_path"]).is_file() else None
    out = {"id": str(item.get("asset_id")), "uri": item.get("uri"), "name": item.get("name") or "", "tags": item.get("tags", []),
           "collection": collection, "kind": item.get("kind"), "image": image,
           "size": [item.get("width"), item.get("height")]}
    grid = item.get("grid") or 0
    if collection == "textures" and item.get("kind") == "flipbook":
        try:
            confirmed = _sibling("fx_grid_overrides").read_grid_overrides().get(str(item.get("asset_id")))
        except (OSError, ValueError):
            # Validation reports malformed overrides as an info; asset search
            # can still show the original catalogue grid in the meantime.
            confirmed = None
        if confirmed is not None:
            grid = confirmed
        out["flipbook"] = {"grid": grid, "FlipbookLayout": LAYOUTS.get(grid, "Custom" if grid else None),
                           "estimated": confirmed is None and str(item.get("grid_source", "")).startswith("inferred")}
    if collection == "meshes":
        for reference in item.get("references", []):
            out[reference.get("label", "MeshId")] = reference.get("uri")
    return out


def _asset_ids(values: str | list[str] | None) -> list[str]:
    """Accept decimal IDs or asset URIs separated by whitespace, commas or semicolons."""
    if values is None:
        return []
    values = [values] if isinstance(values, str) else values
    if not isinstance(values, (list, tuple, set)):
        raise ToolError("IDs attendus : liste ou texte séparé par des virgules")
    result = []
    for value in values:
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ToolError("ID d’asset invalide : " + str(value))
        for token in re.split(r"[\s,;]+", str(value).strip()):
            if not token:
                continue
            match = re.fullmatch(r"(?:rbxassetid://)?([0-9]+)", token)
            if not match:
                raise ToolError("ID d’asset invalide : " + token)
            result.append(match.group(1))
    return list(dict.fromkeys(result))


def excluded_ids(exclude_ids: str | list[str] | None = None, exclude_file: str | Path | None = None) -> set[str]:
    result = set(_asset_ids(exclude_ids))
    if exclude_file:
        content = Path(exclude_file).read_text(encoding="utf-8-sig")
        result.update(_asset_ids("\n".join(line.partition("#")[0] for line in content.splitlines())))
    return result


def compact_assets(result: dict[str, Any]) -> str:
    """Readable search table shared by the CLI and MCP, without losing image data internally."""
    def clean(value):
        return " ".join(str(value or "").replace("|", "/").split())

    lines = ["id | nom | kind/grille | taille"]
    for item in result["items"]:
        flipbook = item.get("flipbook") or {}
        grid = flipbook.get("grid")
        kind = item.get("kind") or "?"
        if grid:
            kind += f"/{grid}x{grid}" + (" estimated" if flipbook.get("estimated") else "")
        width, height = item.get("size") or [None, None]
        size = f"{width}x{height}" if width and height else "?"
        lines.append(" | ".join([("USED " if item.get("used") else "") + item["id"], clean(item.get("name")) or "—", kind, size]))
    lines.append(f"{len(result['items'])} affichés / {result['total']} résultats · offset {result.get('offset', 0)}")
    if result.get("sheet"):
        lines.append("Planche : " + str(result["sheet"]))
    return "\n".join(lines)


def search_assets(collection: str = "textures", tag: str | None = None, kind: str | None = None, query: str | None = None,
                  limit: int = 24, offset: int = 0, *, exclude_ids: str | list[str] | None = None,
                  exclude_file: str | Path | None = None, compact: bool = False) -> dict[str, Any]:
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
    excluded = excluded_ids(exclude_ids, exclude_file)
    if excluded:
        items = [item for item in items if str(item.get("asset_id")) not in excluded]
    limit = max(1, min(int(limit), 120))
    offset = max(0, int(offset))
    page = items[offset:offset + limit]
    result = {"collection": collection, "total": len(items), "offset": offset, "items": [describe_asset(item, collection) for item in page]}
    if compact:
        result["table"] = compact_assets(result)
    return result


def assets_by_ids(ids: str | list[str], collection: str | None = None, *, exclude_ids: str | list[str] | None = None,
                  exclude_file: str | Path | None = None) -> list[dict[str, Any]]:
    """Explicit sheet selection retains excluded assets and marks them USED instead of dropping them."""
    requested = _asset_ids(ids)
    if not requested:
        raise ToolError("la planche exige au moins un ID")
    collections = [collection] if collection else list(COLLECTIONS)
    found = {}
    for name in collections:
        for item in catalog(name):
            ident = str(item.get("asset_id"))
            if ident in requested and ident not in found:
                found[ident] = describe_asset(item, name)
    unknown = [ident for ident in requested if ident not in found]
    if unknown:
        raise ToolError("IDs inconnus dans le catalogue : " + ", ".join(unknown))
    excluded = excluded_ids(exclude_ids, exclude_file)
    return [{**found[ident], "used": ident in excluded} for ident in requested]


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
                    "path": item.get("image"), "grid": (item.get("flipbook") or {}).get("grid", 0),
                    "used": bool(item.get("used"))} for item in items], handle)
    try:
        _run_renderer(["--textures", handle.name, "--out", str(path), "--columns", str(columns)])
    finally:
        os.unlink(handle.name)
    return path


def render(projects: dict[str, Any] | list[dict[str, Any]], out: str | Path | None = None, times: list[float] | None = None,
           frames: int = 8, size: str = "480x270", auto_camera: bool = False, dummy: bool = True, background: str | None = None,
           ground: bool = True, seed: int = 1, camera: list[float] | None = None, columns: int = 4,
           fit: str | None = None, focus: list[float] | None = None, radius: float | None = None,
           fit_percentile: float = 90, fit_all: bool = False, backgrounds: str | list[str] | None = None) -> dict[str, Any]:
    """Planche PNG d’un projet, ou d’une ligne par projet pour comparer des variantes."""
    projects = projects if isinstance(projects, list) else [projects]
    if not projects or len(projects) > 8:
        raise ToolError("1 à 8 projets par planche")
    if isinstance(fit_percentile, bool) or not isinstance(fit_percentile, (int, float)) or not 0 < fit_percentile <= 100 or not math.isfinite(fit_percentile):
        raise ToolError("fit_percentile doit être un nombre > 0 et <= 100")
    if not isinstance(fit_all, bool):
        raise ToolError("fit_all doit être un booléen")
    if backgrounds is not None:
        if background is not None:
            raise ToolError("background et backgrounds sont exclusifs")
        values = backgrounds.split(",") if isinstance(backgrounds, str) else backgrounds
        if not isinstance(values, list) or not 1 <= len(values) <= 8 or any(not isinstance(value, str) or not re.fullmatch(r"(?:sombre|gris|ciel|noir|roblox|dark|#[\da-fA-F]{6})", value.strip()) for value in values):
            raise ToolError("backgrounds : 1 à 8 presets ou couleurs #RRGGBB requis")
        backgrounds = [value.strip() for value in values]
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
        if backgrounds is not None:
            args += ["--backgrounds", ",".join(backgrounds)]
        if not ground:
            args.append("--no-ground")
        if fit is not None:
            args += ["--fit", fit]
        args += ["--fit-percentile", str(float(fit_percentile))]
        if fit_all:
            args.append("--fit-all")
        if focus is not None:
            args += ["--focus", ",".join(str(float(v)) for v in focus)]
        if radius is not None:
            args += ["--radius", str(float(radius))]
        result = _run_renderer(args)
    finally:
        for file in files:
            os.unlink(file)
    result["image"] = str(path)
    return result


def render_batch(jobs: list[dict[str, Any]], *, base_dir: str | Path | None = None) -> dict[str, Any]:
    """One Chromium launch for jobs with projects/out/times/camera/fit/focus.

    Renderer options use camelCase (including fitPercentile=90 and fitAll=false).
    Project files resolve relative to base_dir;
    relative output paths keep the usual repository-root convention.
    """
    if not isinstance(jobs, list) or not jobs or len(jobs) > 128:
        raise ToolError("render-batch : liste de 1 à 128 jobs requise")
    manifest = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or not isinstance(job.get("projects"), list) or not 1 <= len(job["projects"]) <= 8:
            raise ToolError(f"jobs[{index}].projects : 1 à 8 recettes requises")
        recipes = []
        for source in job["projects"]:
            if isinstance(source, dict):
                recipe = source
            elif isinstance(source, str):
                candidate = Path(base_dir or ROOT) / source
                recipe = json.loads(candidate.read_text(encoding="utf-8-sig")) if candidate.is_file() else load(source)
            else:
                raise ToolError(f"jobs[{index}] : recette ou fichier/ID requis")
            recipes.append(validate_project(recipe))
        config = {"autoCamera": False, "dummy": True, **deepcopy(job), "projects": recipes}
        if "out" not in config:
            config["out"] = str(RENDERS / f"batch-{index + 1}.png")
        manifest.append(config)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump({"jobs": manifest}, handle, ensure_ascii=False, allow_nan=False)
    try:
        return _run_renderer(["--batch", handle.name], timeout=max(240, len(jobs) * 120))
    finally:
        os.unlink(handle.name)


# ---- Projets ----

def _sibling(name: str):
    import importlib
    return importlib.import_module("." + name, __package__) if __package__ else importlib.import_module(name)


def validate(project: dict[str, Any]) -> dict[str, Any]:
    return validate_project(project)


def warnings(project: dict[str, Any], include_infos: bool = False) -> list[dict[str, Any]]:
    return _sibling("fx_warnings").validation_warnings(validate_project(project), include_infos=include_infos)


def diagnostic_counts(diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    """Stable, one-entry-per-code summary shared by the CLI and MCP."""
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        counts[diagnostic["code"]] = counts.get(diagnostic["code"], 0) + 1
    return dict(sorted(counts.items()))


def grid_confirm(asset_id: str, grid: int) -> dict[str, Any]:
    """Confirm a visually checked grid in the local overrides, outside the catalogue."""
    ids = _asset_ids(asset_id)
    if len(ids) != 1:
        raise ToolError("grid-confirm exige un seul ID de texture")
    return _sibling("fx_grid_overrides").confirm_grid(ids[0], grid)


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
    elif fmt == "manifest":
        data = json.dumps(export_manifest(project), ensure_ascii=False, indent=2) + "\n"
    else:
        raise ToolError("format : rbxmx, lua, json ou manifest")
    path = Path(out) if out else EXPORTS / (f"{name}.assets.json" if fmt == "manifest" else f"{name}.{fmt}")
    path = path if path.is_absolute() else ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return path


def export_manifest(project: dict[str, Any]) -> dict[str, Any]:
    """Return manual Roblox upload requirements; no files or assets are uploaded."""
    return _sibling("fx_export").mesh_export_manifest(project)


def export_library(recipes: dict[str, dict[str, Any]], out: str | Path | None = None) -> tuple[Path, Path]:
    """One data-only ModuleScript plus the independent gameplay kit."""
    path = Path(out) if out else EXPORTS / "MesEffets.lua"
    path = path if path.is_absolute() else ROOT / path
    return _sibling("fx_export").write_library(recipes, path)


__all__ = ["ToolError", "ValidationError", "search_assets", "compact_assets", "excluded_ids", "assets_by_ids", "tags", "texture_sheet", "render", "validate", "load", "save",
           "list_projects", "export", "export_library", "export_manifest", "describe_asset", "warnings", "diagnostic_counts", "grid_confirm", "render_batch"]
