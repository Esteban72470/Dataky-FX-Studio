"""Fresh, bounded catalogue snapshots and text retrieval for local VFX generation.

Read-only access to the three user catalogues; local OBJ registrations live in a
separate atomic index. Names/tags are search hints, never visual observations.
No permanent cache, network request, downloaded script or asset code is used.
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
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"textures": "textures.json", "beams": "beams/assets.json", "meshes": "meshes/assets.json"}
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100_000
MAX_LOCAL_ASSETS = 256
REGISTRY = "editor/local_ai/catalog.json"
GEOMETRY = "editor/local_ai/meshes"
LAYOUTS = {2: "Grid2x2", 4: "Grid4x4", 8: "Grid8x8"}


class CatalogError(ValueError):
    pass


def _root(root):
    return Path(root if root is not None else ROOT).resolve()


def _path(root, relative):
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise CatalogError("Chemin de catalogue hors de l'application")
    return candidate


def _clean(value, maximum=160):
    return " ".join(value.split())[:maximum] if isinstance(value, str) else ""


def _labels(value, limit=32):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for v in value[:limit] if (item := _clean(v, 120))))


def _id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    match = re.fullmatch(r"(?:rbxassetid://|https?://(?:www\.)?roblox\.com/asset/?\?id=)?([0-9]{1,30})", str(value).strip())
    return str(int(match[1])) if match and int(match[1]) > 0 else None


def _stat(path):
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CatalogError(f"Catalogue inaccessible : {path.name} : {exc}") from None
    return value.st_size, value.st_mtime_ns, value.st_ino


def _read(path):
    try:
        if not path.exists():
            return None
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise CatalogError(f"Catalogue trop volumineux : {path.name} (64 Mio maximum)")
        with path.open("rb") as handle:
            body = handle.read(MAX_SOURCE_BYTES + 1)
        if len(body) > MAX_SOURCE_BYTES:
            raise CatalogError(f"Catalogue trop volumineux : {path.name}")
        return body
    except OSError as exc:
        raise CatalogError(f"Catalogue illisible : {path.name} : {exc}") from None


def _json(body, label):
    try:
        return json.loads(body.decode("utf-8-sig"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CatalogError(f"Catalogue JSON invalide : {label}. Corriger le fichier ; aucune ancienne version n'est utilisée.") from None


def _files(root):
    names = [*SOURCES.values(), "tool/grid_overrides.json", "editor/artistry/assets.json", REGISTRY]
    paths = {name: _path(root, name) for name in names}
    # A snapshot never mixes entries from a file changed while it was read.
    for _ in range(3):
        before = {name: _stat(path) for name, path in paths.items()}
        bodies = {name: _read(path) for name, path in paths.items()}
        after = {name: _stat(path) for name, path in paths.items()}
        if before == after:
            digest = hashlib.sha256()
            for name, body in bodies.items():
                digest.update(name.encode()); digest.update(b"\0")
                digest.update(body if body is not None else b"<missing>"); digest.update(b"\0")
            return bodies, digest.hexdigest()
    raise CatalogError("Le catalogue est en cours de modification ; réessayer la demande.")


def _image(row, collection):
    relative = row.get("image_path") or row.get("preview_path")
    if not isinstance(relative, str):
        return None
    prefix = "" if collection == "textures" else collection + "/"
    relative = relative.replace("\\", "/")
    if prefix and relative.startswith(prefix):
        relative = relative[len(prefix):]
    if not re.fullmatch(r"(?:images|previews)/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp|gif)", relative, re.I):
        return None
    return prefix + relative


def _reference(row, label):
    for ref in row.get("references", []) if isinstance(row.get("references"), list) else []:
        if isinstance(ref, dict) and str(ref.get("label", "")).casefold() == label.casefold():
            ident = _id(ref.get("uri") or ref.get("asset_id"))
            if ident:
                return "rbxassetid://" + ident
    ident = _id(row.get(label))
    return "rbxassetid://" + ident if ident else None


def _annotation(record, annotations):
    entry = annotations.get(record["key"])
    if not isinstance(entry, dict):
        return
    metadata, evidence = entry.get("metadata"), entry.get("provenance")
    if not isinstance(metadata, dict) or not isinstance(evidence, dict):
        return
    observed = {}
    provenance = {}
    for field in ("shape", "style", "color", "usage", "category", "notes"):
        proof = evidence.get(field)
        if field not in metadata or not isinstance(proof, dict) or proof.get("observer") not in {"human", "vision"}:
            continue
        value = _clean(metadata[field], 2000) if field == "notes" else _labels(metadata[field], 16)
        if value:
            observed[field] = value
            provenance[field] = deepcopy(proof)
    if observed:
        record["metadata"] = observed
        record["provenance"]["observations"] = provenance
        record["visual_status"] = "observed"


def _asset(row, collection, overrides, annotations):
    if not isinstance(row, dict) or row.get("id_status", "valid") != "valid":
        return None
    ident = _id(row.get("asset_id")) or _id(row.get("uri"))
    if collection == "meshes":
        ident = _id(_reference(row, "MeshId")) or ident
    if not ident:
        return None
    record = {"key": collection + ":" + ident, "collection": collection, "id": ident,
              "uri": "rbxassetid://" + ident, "name": _clean(row.get("name")),
              "tags": _labels(row.get("tags")), "aliases": _labels(row.get("aliases")),
              "key_aliases": list(dict.fromkeys(_clean(value, 100) for value in [row.get("key"), *row.get("key_aliases", [])] if isinstance(value, str) and value)),
              "kind": _clean(row.get("kind"), 30) or {"textures": "static", "beams": "beam", "meshes": "mesh"}[collection],
              "image": _image(row, collection), "visual_status": "unknown",
              "provenance": {"source": SOURCES[collection], "license": deepcopy(row.get("license")),
                             "creator": deepcopy(row.get("creator") or row.get("author")),
                             "source_url": row.get("source_url") if isinstance(row.get("source_url"), str) else None}}
    if collection == "textures" and record["kind"] == "flipbook":
        grid = overrides.get(ident, row.get("grid", 0))
        grid = grid if type(grid) is int and 0 <= grid <= 64 else 0
        record["flipbook"] = {"grid": grid, "FlipbookLayout": LAYOUTS.get(grid),
                              "estimated": ident not in overrides and str(row.get("grid_source", "")).startswith("inferred")}
    if collection == "meshes":
        record["mesh_id"] = record["uri"]
        record["mesh_texture_id"] = _reference(row, "TextureId") or _reference(row, "TextureID") or ""
    if annotations is not None:
        _annotation(record, annotations)
    return record


def _mesh_variant_rows(row):
    """Expose saved texture choices while the editor stores one mesh row per ID."""
    if not isinstance(row, dict) or not isinstance(row.get("variants"), list) or not row["variants"]:
        return [row]
    result = []
    for variant in row["variants"]:
        if not isinstance(variant, dict):
            continue
        texture = variant.get("texture_uri") or ""
        if texture and not _id(texture):
            continue
        item = deepcopy(row)
        item["references"] = [ref for ref in row.get("references", []) if isinstance(ref, dict) and str(ref.get("label", "")).casefold() not in {"textureid"}]
        if texture:
            item["references"].append({"label": "TextureId", "uri": texture})
        item["key_aliases"] = list(variant.get("key_aliases", []))
        # The row's stable key resolves its original texture choice when known.
        if row.get("key") not in item["key_aliases"]:
            item.pop("key", None)
        names = variant.get("names", [])
        if isinstance(names, list) and names:
            item["aliases"] = list(dict.fromkeys(item.get("aliases", []) + names))
        result.append(item)
    return result or [row]


def _registry(body):
    if body is None:
        return {"version": 1, "assets": []}
    value = _json(body, REGISTRY)
    if not isinstance(value, dict) or value.get("version") != 1 or type(value.get("version")) is not int or not isinstance(value.get("assets"), list) or len(value["assets"]) > MAX_LOCAL_ASSETS:
        raise CatalogError("Registre des meshes locaux invalide")
    for record in value["assets"]:
        if (not isinstance(record, dict) or record.get("collection") != "meshes"
                or not re.fullmatch(r"local-[a-f0-9]{24}", str(record.get("id", "")))
                or record.get("key") != "meshes:" + record["id"]
                or not re.fullmatch(r"editor/local_ai/meshes/[a-f0-9]{64}\.json", str(record.get("geometry_path", "")))
                or not isinstance(record.get("name"), str) or not isinstance(record.get("tags"), list)
                or (record.get("mesh_id") and not _id(record["mesh_id"]))):
            raise CatalogError("Entrée du registre de meshes locaux invalide")
    return value


def snapshot(root=None):
    """Read all sources afresh. Invalid JSON fails visibly; no stale snapshot fallback."""
    root = _root(root)
    bodies, revision = _files(root)
    warnings = []
    overrides, annotations = {}, {}
    for name, target, key in (("tool/grid_overrides.json", overrides, None), ("editor/artistry/assets.json", annotations, "assets")):
        if bodies[name] is None:
            continue
        value = _json(bodies[name], name)
        if key:
            if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get(key), dict):
                raise CatalogError("Index d'observations d'assets invalide")
            target.update(value[key])
        elif isinstance(value, dict):
            # Existing override format is versioned; old direct maps remain readable.
            values = value.get("overrides", value.get("grids", value))
            if isinstance(values, dict):
                for ident, entry in values.items():
                    grid = entry.get("grid") if isinstance(entry, dict) else entry
                    if _id(ident) and type(grid) is int and grid in LAYOUTS:
                        target[str(int(ident))] = grid
        else:
            raise CatalogError("Index de grilles de flipbooks invalide")
    assets = {}
    raw_counts = {}
    skipped = duplicates = 0
    for collection, name in SOURCES.items():
        if bodies[name] is None:
            raw_counts[collection] = 0
            warnings.append(f"Catalogue absent : {name}")
            continue
        rows = _json(bodies[name], name)
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise CatalogError(f"{name} : liste de {MAX_ROWS} assets maximum requise")
        raw_counts[collection] = len(rows)
        expanded = [item for row in rows for item in _mesh_variant_rows(row)] if collection == "meshes" else rows
        prepared = [_asset(row, collection, overrides, None) for row in expanded]
        mesh_bases = {}
        if collection == "meshes":
            variants = {}
            for record in prepared:
                if record is not None:
                    variants.setdefault(record["id"], set()).add(_id(record.get("mesh_texture_id")) or "")
            # Choose the canonical base before walking rows. Reordering a
            # catalogue must never change which texture its base key selects.
            mesh_bases = {ident: "" if "" in textures else min(textures, key=int) for ident, textures in variants.items()}
        for record in prepared:
            if record is None:
                skipped += 1
                continue
            if collection == "meshes":
                texture_id = _id(record.get("mesh_texture_id")) or ""
                if texture_id != mesh_bases[record["id"]]:
                    record["key"] += "@" + texture_id
            _annotation(record, annotations)
            key = record["key"]
            if key in assets:
                duplicates += 1
                assets[key]["tags"] = list(dict.fromkeys(assets[key]["tags"] + record["tags"]))
                assets[key]["aliases"] = list(dict.fromkeys(assets[key]["aliases"] + record["aliases"] + ([record["name"]] if record["name"] else [])))
                assets[key]["key_aliases"] = list(dict.fromkeys(assets[key].get("key_aliases", []) + record.get("key_aliases", [])))
            else:
                assets[key] = record
    for record in _registry(bodies[REGISTRY])["assets"]:
        record = deepcopy(record)
        path = _path(root, record["geometry_path"])
        record["geometry_available"] = path.is_file()
        if not record["geometry_available"]:
            warnings.append(f"Géométrie locale manquante : {record['name']}")
        assets[record["key"]] = record
    if skipped:
        warnings.append(f"{skipped} entrées avec identifiant invalide exclues")
    if duplicates:
        warnings.append(f"{duplicates} doublons fusionnés par collection et identifiant")
    values = list(assets.values())
    counts = {collection: sum(a["collection"] == collection for a in values) for collection in SOURCES}
    counts.update(total=len(values), skipped=skipped, local_meshes=sum(a.get("local", False) for a in values))
    return {"revision": revision, "counts": counts, "raw_counts": raw_counts,
            "assets": values, "warnings": warnings, "source": str(root)}


def fold(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in value if not unicodedata.combining(c))))


_SYNONYM_GROUPS = (
    "anneau ring shockwave onde choc cercle circle ground sol",
    "entaille lame slash crescent croissant sword epee swipe blade",
    "fumee smoke poussiere dust brouillard fog",
    "etincelle etincelles spark sparks spec sparkle glowing",
    "feu fire flamme flammes flame flames burn brulure",
    "eclair eclairs lightning thunder electric electrique",
    "eau water vague wave splash tsunami",
    "glace ice frost frozen cristal crystal",
    "energie energy laser beam faisceau rayon arc",
    "flash glare flare glow lumiere light lumineux lueur",
    "charge charging aspiration convergence accumulation",
    "orbe orb sphere boule ball bubble bulle",
    "vent wind swirl tourbillon tornado tornade spiral spirale",
    "impact explosion burst explosive blast",
    "mesh meshes maillage maillages geometrie geometry",
    "chaine chain chains chaines",
    "portail portal magic magique magie sigil invocation summoning",
)
_SYNONYMS = {word: set(group.split()) for group in _SYNONYM_GROUPS for word in group.split()}
_STOP = set("a an and are at avec ce ces cette create creer creerun dans de des do du effect effet en et for from il la le les make me my of on or ou par pour qui the to un une use uses using veuillez avec without sans tres more plus extremely puissantofthe s d l".split())


def _groups(query):
    return [_SYNONYMS.get(word, {word}) for word in dict.fromkeys(fold(query).split()) if word not in _STOP and len(word) > 1]


def search(query="", collection=None, limit=12, offset=0, *, snapshot=None, root=None, role=None):
    """Rank textual metadata over the entire live catalogue; paginate all matches.

    Synonyms translate common FR/EN VFX words, without declaring observed visuals.
    A caller may reuse one snapshot for a coherent bounded generation request.
    """
    if collection not in (None, *SOURCES):
        raise CatalogError("collection : textures, beams ou meshes requis")
    if not isinstance(query, str) or len(query) > 12000:
        raise CatalogError("query : texte de 12000 caractères maximum requis")
    if role is not None and (not isinstance(role, str) or len(role) > 160):
        raise CatalogError("role : texte court requis")
    if type(limit) is not int or not 1 <= limit <= 120 or type(offset) is not int or offset < 0:
        raise CatalogError("limit : entier 1–120 ; offset : entier positif ou nul requis")
    snap = snapshot if snapshot is not None else globals()["snapshot"](root)
    if not isinstance(snap, dict) or not isinstance(snap.get("assets"), list):
        raise CatalogError("Snapshot de catalogue invalide")
    groups, role_groups = _groups(query), _groups(role or "")
    explicit_ids = set(re.findall(r"(?<![0-9])[1-9][0-9]{2,29}(?![0-9])", query))
    explicit_keys = set(re.findall(r"(?:textures|beams|meshes):(?:local-[a-f0-9]{24}|[1-9][0-9]{0,29}(?:@[1-9][0-9]{0,29})?)", query))
    folded_query = fold(query)
    ranked = []
    for position, asset in enumerate(snap["assets"]):
        if collection is not None and asset["collection"] != collection:
            continue
        metadata = asset.get("metadata") or {}
        observed = " ".join(v if isinstance(v, str) else " ".join(v) for v in metadata.values() if isinstance(v, (str, list)))
        name = fold(asset["name"])
        tags = fold(" ".join(asset.get("tags", [])))
        alias = fold(" ".join(asset.get("aliases", [])))
        haystack = set((name + " " + tags + " " + alias + " " + fold(observed)).split())
        hits = sum(bool(group & haystack) for group in groups)
        role_hits = sum(bool(group & haystack) for group in role_groups)
        exact_key = asset["key"] in explicit_keys or query.strip() == asset["key"] or query.strip() in asset.get("key_aliases", [])
        exact = asset["id"] in explicit_ids or exact_key or query.strip() == asset["id"]
        if (groups or role_groups) and not (hits or role_hits or exact):
            continue
        # New exact query metadata must beat an old generic layer-role match.
        score = hits * 100 + role_hits * 10
        if folded_query and folded_query == name:
            score += 600
        if exact_key:
            score += 20000
        elif exact:
            score += 10000
        ranked.append((score, position, asset))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return {"items": [deepcopy(asset) for _, _, asset in ranked[offset:offset+limit]], "total": len(ranked),
            "offset": offset, "limit": limit, "revision": snap["revision"], "counts": deepcopy(snap["counts"]),
            "warnings": list(snap.get("warnings", [])), "query": query, "collection": collection}


def get_asset(key, *, snapshot=None, root=None):
    """Resolve a canonical collection:key or an unambiguous local/numeric ID."""
    if not isinstance(key, str) or len(key) > 100:
        raise CatalogError("Clé d'asset invalide")
    snap = snapshot if snapshot is not None else globals()["snapshot"](root)
    found = [asset for asset in snap["assets"] if asset["key"] == key or asset["id"] == key]
    if not found:
        found = [asset for asset in snap["assets"] if key in asset.get("key_aliases", [])]
    if len(found) != 1:
        raise CatalogError("Asset absent ou identifiant ambigu dans le catalogue actuel : " + key)
    return deepcopy(found[0])


@contextmanager
def _locked(root):
    folder = _path(root, "editor/local_ai")
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".catalog.lock"
    for attempt in range(100):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if attempt == 99:
                raise CatalogError("Registre de meshes locaux occupé ; réessayer après l'import en cours")
            time.sleep(.02)
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _atomic(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".catalog-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(body); file.flush(); os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def register_mesh(imported, *, root=None, tags=None):
    """Add/update a validated OBJ in the separate reusable local catalogue.

    The source hash is its stable identity. Geometry files are content-addressed
    and the metadata index is replaced atomically under a cross-process lock.
    """
    if __package__:
        from .fx_mesh import validate_mesh
    else:
        from fx_mesh import validate_mesh
    if not isinstance(imported, dict) or not isinstance(imported.get("node"), dict):
        raise CatalogError("Résultat d'import OBJ requis")
    if imported["node"].get("class") != "MeshPart" or not isinstance(imported["node"].get("properties"), dict):
        raise CatalogError("MeshPart issu d'un import OBJ requis")
    geometry = imported.get("mesh")
    validate_mesh(geometry)
    properties = imported["node"].get("properties", {})
    if properties.get("MeshId") and not _id(properties["MeshId"]):
        raise CatalogError("MeshId Roblox explicite invalide")
    if properties.get("TextureID") and not _id(properties["TextureID"]):
        raise CatalogError("TextureID Roblox explicite invalide")
    ident = "local-" + geometry["source"]["sha256"][:24]
    body = json.dumps(geometry, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    root = _root(root)
    relative = GEOMETRY + "/" + digest + ".json"
    with _locked(root):
        registry_path = _path(root, REGISTRY)
        registry = _registry(_read(registry_path))
        prior = next((asset for asset in registry["assets"] if asset["id"] == ident), None)
        if prior is None and len(registry["assets"]) >= MAX_LOCAL_ASSETS:
            raise CatalogError("Catalogue local limité à 256 meshes")
        mesh_id = _id(properties.get("MeshId")) or (_id(prior.get("mesh_id")) if prior else None)
        uri = "rbxassetid://" + mesh_id if mesh_id else ""
        texture = _id(properties.get("TextureID")) or (_id(prior.get("mesh_texture_id")) if prior else None)
        incoming_name = _clean(imported["node"].get("name") or geometry["source"]["name"])
        if prior:
            # Saving an effect is not an instruction to rename a library asset
            # or replace its source/license/observation provenance.
            record = deepcopy(prior)
            record["aliases"] = list(dict.fromkeys(prior.get("aliases", []) + ([incoming_name] if incoming_name != prior["name"] else [])))
            if tags is not None:
                record["tags"] = list(dict.fromkeys(prior.get("tags", []) + _labels(tags)))
            record.update(uri=uri, mesh_id=uri, mesh_texture_id="rbxassetid://" + texture if texture else "",
                          geometry_path=relative, dimensions=deepcopy(geometry["source"]["dimensions"]))
        else:
            record = {"key": "meshes:" + ident, "collection": "meshes", "id": ident, "uri": uri,
                  "mesh_id": uri, "mesh_texture_id": "rbxassetid://" + texture if texture else "",
                  "name": incoming_name,
                  "tags": _labels(tags or ["Imported", "OBJ"]), "aliases": [], "kind": "mesh", "image": None,
                  "local": True, "geometry_path": relative, "visual_status": "unknown",
                  "provenance": {"source": "local-import", "source_sha256": geometry["source"]["sha256"],
                                 "registered_at": datetime.now(timezone.utc).isoformat(), "license": None, "creator": None},
                  "dimensions": deepcopy(geometry["source"]["dimensions"])}
        path = _path(root, relative)
        if not path.is_file():
            _atomic(path, body)
        if record != prior:
            if prior:
                registry["assets"][registry["assets"].index(prior)] = record
            else:
                registry["assets"].append(record)
            _atomic(registry_path, (json.dumps(registry, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8"))
    return deepcopy(record)


def load_geometry(asset, *, root=None):
    """Return only explicitly registered local geometry; external meshes yield None."""
    if not isinstance(asset, dict) or not asset.get("geometry_path"):
        return None
    relative = asset["geometry_path"]
    if not isinstance(relative, str) or not re.fullmatch(r"editor/local_ai/meshes/[a-f0-9]{64}\.json", relative):
        raise CatalogError("Référence de géométrie locale invalide")
    body = _read(_path(_root(root), relative))
    if body is None:
        raise CatalogError("La géométrie du mesh local a été supprimée ; réimporter son OBJ")
    if hashlib.sha256(body).hexdigest() != Path(relative).stem:
        raise CatalogError("L'empreinte de la géométrie locale ne correspond plus à son registre")
    geometry = _json(body, relative)
    if __package__:
        from .fx_mesh import validate_mesh
    else:
        from fx_mesh import validate_mesh
    validate_mesh(geometry)
    return geometry


def _editor_local_entries(rows):
    result = []
    for asset in rows:
        references = []
        for label, key in (("MeshId", "mesh_id"), ("TextureId", "mesh_texture_id")):
            if ident := _id(asset.get(key)):
                references.append({"label": label, "asset_id": ident, "uri": "rbxassetid://" + ident, "id_status": "valid"})
        result.append({"asset_id": asset["id"], "uri": asset.get("mesh_id", ""), "name": asset["name"],
                       "kind": "mesh", "collection": "meshes", "tags": list(asset["tags"]), "aliases": list(asset.get("aliases", [])),
                       "image_path": None, "image_status": "local-geometry", "local_key": asset["id"],
                       "references": references, "id_status": "local"})
    return result


def local_entries(root=None):
    """Raw records compatible with the editor's existing /api/catalog format."""
    rows = _registry(_read(_path(_root(root), REGISTRY)))["assets"]
    return _editor_local_entries(rows)


def editor_catalog(root=None):
    """Return raw editor rows and their revision from one coherent byte snapshot.

    Never compute the revision using a later independent read: that could mark
    old rows as current and hide an addition until the following modification.
    """
    bodies, revision = _files(_root(root))
    result = {"revision": revision}
    for collection, name in SOURCES.items():
        rows = [] if bodies[name] is None else _json(bodies[name], name)
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise CatalogError(f"{name} : liste de {MAX_ROWS} assets maximum requise")
        result[collection] = rows
    result["meshes"].extend(_editor_local_entries(_registry(bodies[REGISTRY])["assets"]))
    return result
