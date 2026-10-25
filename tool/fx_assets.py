"""Observed asset metadata and local artistic references; never infer visuals from names.

search() combines the existing catalogue with an optional sidecar. annotate_asset()
records the caller's human/vision observations with evidence, not an automated claim
that this module has seen the image. References are inspiration for original effects.
All authored data stays outside the immutable catalogue and portable VFX recipes.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

if __package__:
    from . import fx_tools
else:
    import fx_tools

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("shape", "style", "color", "usage", "category")
OBSERVATIONS = {"shape", "forms", "color", "colors", "rhythm", "transitions", "depth", "motion", "composition", "notes"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MAX_IMAGE = 16 * 1024 * 1024
MAX_VIDEO = 128 * 1024 * 1024
ToolError = fx_tools.ToolError


def _text(value, label, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ToolError(f"{label} : texte non vide de {limit} caractères maximum requis")
    return value.strip()


def _labels(value, label):
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or len(values) > 16:
        raise ToolError(label + " : texte ou liste de 16 textes maximum requis")
    return list(dict.fromkeys(_text(v, label, 120).casefold() for v in values))


def _observer(value):
    if not isinstance(value, str) or value not in {"human", "vision"}:
        raise ToolError("observer : human ou vision requis ; aucune analyse visuelle automatique n’est simulée")
    return value


def _directory(relative=""):
    base = ROOT.resolve() / "editor" / "artistry"
    target = (base / relative).resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ToolError("Répertoire artistique situé hors du projet")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read(path, key):
    if not path.is_file():
        return {"version": 1, key: {}}
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ToolError(f"Index trop volumineux : {path}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"Index illisible, conservé sans modification : {path}") from exc
    if not isinstance(result, dict) or result.get("version") != 1 or not isinstance(result.get(key), dict):
        raise ToolError(f"Format d’index invalide, conservé sans modification : {path}")
    for ident, entry in result[key].items():
        if not isinstance(entry, dict):
            raise ToolError(f"Entrée d’index invalide : {path} / {ident}")
        if key == "assets" and (not isinstance(entry.get("metadata"), dict) or not isinstance(entry.get("provenance"), dict)):
            raise ToolError(f"Métadonnées d’index invalides : {ident}")
        if key == "assets":
            for field, value in entry["metadata"].items():
                if field not in (*FIELDS, "notes"):
                    raise ToolError(f"Champ d’index inconnu : {ident} / {field}")
                if field == "notes":
                    _text(value, "notes", 2000)
                elif not isinstance(value, list) or _labels(value, field) != value:
                    raise ToolError(f"Liste de métadonnées invalide : {ident} / {field}")
        if key == "references" and (not re.fullmatch(r"[a-f0-9]{32}", ident) or entry.get("id") != ident
                                    or not isinstance(entry.get("path"), str)
                                    or Path(entry["path"]).suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
                                    or not isinstance(entry.get("created_at"), str)):
            raise ToolError(f"Référence d’index invalide : {ident}")
    return result


def _atomic(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".dataky-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _locked(path):
    # Exclusive creation also serializes independent HTTP and MCP processes.
    lock = path.with_suffix(".lock")
    for attempt in range(100):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if attempt == 99:
                raise ToolError(f"Index occupé : {lock}. Si le serveur a planté, supprimer ce verrou après son arrêt.")
            time.sleep(.02)
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _write(path, value):
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(data) > 16 * 1024 * 1024:
        raise ToolError("Index artistique limité à 16 Mo")
    _atomic(path, data)


def _media(path, kind=None):
    if not isinstance(path, (str, Path)) or not str(path):
        raise ToolError("Chemin local de preuve visuelle requis")
    source = Path(path).expanduser()
    source = (source if source.is_absolute() else ROOT / source).resolve()
    if not source.is_file():
        raise ToolError(f"Fichier visuel introuvable : {source}")
    extension = source.suffix.lower()
    is_video = extension in VIDEO_EXTENSIONS
    if extension not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        raise ToolError("Format visuel accepté : PNG, JPEG, WebP, GIF, BMP, MP4, MOV ou WebM")
    if kind is not None and (not isinstance(kind, str) or kind not in {"image", "spritesheet", "video"}
                             or (kind == "video") != is_video):
        raise ToolError("kind doit correspondre au fichier : image, spritesheet ou video")
    limit = MAX_VIDEO if is_video else MAX_IMAGE
    if not 0 < source.stat().st_size <= limit:
        raise ToolError(f"Fichier vide ou trop volumineux (maximum {limit // (1024 * 1024)} Mo)")
    with source.open("rb") as handle:
        data = handle.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise ToolError("Fichier visuel modifié ou trop volumineux")
    valid_header = {".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
                    ".jpg": data.startswith(b"\xff\xd8\xff"), ".jpeg": data.startswith(b"\xff\xd8\xff"),
                    ".gif": data.startswith((b"GIF87a", b"GIF89a")), ".bmp": data.startswith(b"BM"),
                    ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
                    ".webm": data.startswith(b"\x1aE\xdf\xa3"),
                    ".mp4": data[4:8] == b"ftyp", ".mov": data[4:8] in {b"ftyp", b"moov", b"mdat"}}[extension]
    if not valid_header:
        raise ToolError("Le contenu du fichier ne correspond pas à son extension visuelle")
    return source, data, {"path": str(source), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _asset_id(value, collection):
    if not isinstance(collection, str) or collection not in fx_tools.COLLECTIONS:
        raise ToolError("collection inconnue : textures, beams ou meshes")
    match = re.fullmatch(r"(?:rbxassetid://)?([0-9]{1,30})", str(value))
    ident = match.group(1) if match else None
    if not ident or not any(str(item.get("asset_id")) == ident and item.get("id_status", "valid") == "valid"
                            for item in fx_tools.catalog(collection)):
        raise ToolError(f"Asset valide introuvable dans {collection} : {value}")
    return ident


def annotate_asset(asset_id, collection, metadata, *, observer, evidence):
    """Merge explicitly supplied fields; provenance is retained separately per field.

    Fields: shape/style/color/usage/category (text or up to 16 labels), notes (text).
    Empty label lists clear a field. Evidence must be an existing local visual file.
    The observer declaration is supplied by the caller, never verified by this tool.
    """
    ident = _asset_id(asset_id, collection)
    _observer(observer)
    if not isinstance(metadata, dict) or not metadata or set(metadata) - set(FIELDS) - {"notes"}:
        raise ToolError("metadata : shape, style, color, usage, category ou notes requis")
    cleaned = {key: _text(value, "notes", 2000) if key == "notes" else _labels(value, key) for key, value in metadata.items()}
    _, _, proof = _media(evidence)
    provenance = {"observer": observer, "evidence": proof, "observed_at": datetime.now(timezone.utc).isoformat()}
    path = _directory() / "assets.json"
    key = collection + ":" + ident
    with _locked(path):
        store = _read(path, "assets")
        entry = store["assets"].setdefault(key, {"id": ident, "collection": collection, "metadata": {}, "provenance": {}})
        entry["metadata"].update(cleaned)
        entry["provenance"].update({field: deepcopy(provenance) for field in cleaned})
        _write(path, store)
    return deepcopy(entry)


def search(collection="textures", *, shape=None, style=None, color=None, usage=None, category=None,
           query=None, kind=None, limit=24, offset=0):
    """AND across filters, OR among labels of one filter; unknown visuals never match.

    category may match captured catalogue tags (explicitly labelled catalogue).
    Text query matches names, IDs, catalogue tags and observed metadata; it never
    converts a descriptive name into a visually verified shape, style or colour.
    """
    if not isinstance(collection, str) or collection not in fx_tools.COLLECTIONS:
        raise ToolError("collection inconnue : textures, beams ou meshes")
    rows = fx_tools.catalog(collection)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 120:
        raise ToolError("limit : entier entre 1 et 120 requis")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ToolError("offset : entier positif ou nul requis")
    if kind is not None and (not isinstance(kind, str) or kind not in {"static", "flipbook", "mesh", "beam"}):
        raise ToolError("kind : static, flipbook, mesh ou beam requis")
    filters = {key: set(_labels(value, key)) for key, value in zip(FIELDS, (shape, style, color, usage, category)) if value is not None}
    words = _text(query, "query", 500).casefold().split() if query is not None else []
    annotations = _read(ROOT / "editor" / "artistry" / "assets.json", "assets")["assets"]
    results = []
    for row in rows:
        if row.get("id_status", "valid") != "valid" or kind and row.get("kind") != kind:
            continue
        annotation = annotations.get(collection + ":" + str(row.get("asset_id")), {})
        metadata = {key: list(annotation.get("metadata", {}).get(key, [])) for key in FIELDS}
        if annotation.get("metadata", {}).get("notes"):
            metadata["notes"] = annotation["metadata"]["notes"]
        categories = {str(tag).casefold() for tag in row.get("tags", [])}
        if any(not wanted.intersection(set(metadata[key]) | (categories if key == "category" else set())) for key, wanted in filters.items()):
            continue
        haystack = " ".join([str(row.get("asset_id", "")), row.get("name") or "", *row.get("aliases", []), *row.get("tags", []),
                             *(label for key in FIELDS for label in metadata[key]), metadata.get("notes", "")]).casefold()
        if not all(word in haystack for word in words):
            continue
        results.append((row, metadata, annotation))
    items = []
    for row, metadata, annotation in results[offset:offset + limit]:
        item = fx_tools.describe_asset(row, collection)
        item.update({"metadata": metadata, "provenance": deepcopy(annotation.get("provenance", {})),
                     "visual_status": "observed" if annotation else "unknown", "category_source": "catalogue tags and explicit observations"})
        items.append(item)
    return {"collection": collection, "total": len(results), "offset": offset, "items": items,
            "visual_policy": "Visual attributes are unknown until a human or vision observer supplies evidence."}


def add_reference(path, kind, observations, *, observer, name=None, source=None):
    """Copy a local visual reference and record caller-supplied observations.

    No image/video analysis or video frame extraction occurs here. Observations
    describe inspiration; references must inform an original effect, not a copy.
    """
    _observer(observer)
    if not isinstance(kind, str) or kind not in {"image", "spritesheet", "video"}:
        raise ToolError("kind : image, spritesheet ou video requis")
    original, data, proof = _media(path, kind)
    if not isinstance(observations, dict) or not observations or set(observations) - OBSERVATIONS:
        raise ToolError("observations : shape/forms, color/colors, rhythm, transitions, depth, motion, composition ou notes requis")
    cleaned = {key: _labels(value, key) if isinstance(value, list) else _text(value, key, 2000) for key, value in observations.items()}
    if not any(cleaned.values()):
        raise ToolError("Au moins une observation visuelle explicite est requise")
    ident = uuid.uuid4().hex
    item = {"id": ident, "kind": kind, "name": _text(name or original.stem, "name", 160),
            "observer": observer, "observations": cleaned, "evidence": proof,
            "created_at": datetime.now(timezone.utc).isoformat(), "purpose": "inspiration for an original effect"}
    if source is not None:
        item["source"] = _text(source, "source", 2000)
    directory = _directory("references")
    target = directory / (ident + original.suffix.lower())
    item.update({"path": str(target), "relative_path": target.relative_to(ROOT.resolve()).as_posix()})
    index = directory / "index.json"
    with _locked(index):
        store = _read(index, "references")
        _atomic(target, data)
        try:
            store["references"][ident] = item
            _write(index, store)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return deepcopy(item)


def list_references():
    """Return registered references; missing files are explicitly marked unavailable."""
    store = _read(ROOT / "editor" / "artistry" / "references" / "index.json", "references")
    items = []
    for item in store["references"].values():
        value = deepcopy(item)
        expected = ROOT.resolve() / "editor" / "artistry" / "references" / (item["id"] + Path(item["path"]).suffix)
        value["path"] = str(expected)
        value["available"] = expected.is_file()
        items.append(value)
    return sorted(items, key=lambda item: item["created_at"], reverse=True)


def get_reference(reference_id):
    if not isinstance(reference_id, str) or not re.fullmatch(r"[a-f0-9]{32}", reference_id):
        raise ToolError("reference_id : identifiant local invalide")
    for item in list_references():
        if item["id"] == reference_id:
            return item
    raise ToolError("Référence introuvable : " + reference_id)


__all__ = ["search", "annotate_asset", "add_reference", "list_references", "get_reference"]
