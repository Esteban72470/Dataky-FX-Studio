"""Merge a second captured plugin catalogue by canonical Roblox asset ID.

The input captures remain immutable. Existing rows, aliases, category membership,
mesh texture variants and source observations are retained. Run without --apply
to inspect a merge report before changing the application catalogue.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from copy import deepcopy
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import zipfile


PLUGIN = "VFX Studio"
SPECIAL = {"all", "user", "personal", "recentlyused", "favorites", "new", "newfilter", "static", "statics", "flipbook", "flipbooks"}
LIST_FIELDS = ("tags", "collections", "source_labels", "raw_uris", "normalization_warnings", "classification_conflicts", "observed_rect_kinds", "kind_source_labels")
IMAGE_FIELDS = ("image_path", "preview_path", "image_status", "image_error", "image_source", "width", "height", "preview_error")


def token(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def plain(value):
    return " ".join(re.sub(r"<[^>]*>", "", str(value or "")).split())


def canonical_id(value):
    """Parse known asset forms; never mistake thumbnail dimensions for IDs."""
    value = str(value or "").strip()
    match = re.search(r"(?:[?&])(?:id|assetid)=([0-9]+)(?:[&#]|$)", value, re.I)
    if not match:
        match = re.fullmatch(r"(?:rbxassetid://)+([0-9]+)", value, re.I)
    if not match:
        match = re.fullmatch(r"([0-9]+)", value)
    return str(int(match[1])) if match and int(match[1]) > 0 and not match[1].startswith("0") else None


def quality(name):
    name = plain(name)
    core = re.sub(r"\.(?:png|jpe?g|tga|webp)$", "", name.replace("\\", "/").rsplit("/", 1)[-1], flags=re.I)
    if not name or re.fullmatch(r"[\d\s_().-]+", core) or re.fullmatch(r"(?:VFXItem|Item|Texture|Mesh|MeshPart|SpecialMesh|Part|Handle|Asset|Template|Untitled|Unnamed)[_ #:-]*\d*", core, re.I):
        return 0
    if re.fullmatch(r"(?:(?:Circle|Crescent|Effect|Fire|Flare|Grid|Ground|Impact|Lightning|Other|Slash|Smoke|Spec|Star|Swirl|Text|Water|Wind)\s*\d+|\d+(?:Circle|Other|Mesh|Texture))", name, re.I):
        return 1
    return 2


def unique(values):
    result, seen = [], set()
    for value in values:
        signature = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if signature not in seen:
            result.append(deepcopy(value))
            seen.add(signature)
    return result


def unique_references(values):
    result, seen = [], set()
    for value in values:
        key = (str(value.get("label", "")), str(value.get("uri", "")))
        if key not in seen:
            result.append(deepcopy(value))
            seen.add(key)
    return result


def _raw_reference(raw, collection):
    if collection == "meshes":
        names = ("mesh_uri", "mesh_id", "MeshId", "MeshID", "raw_uri", "uri", "asset_id")
    else:
        names = ("raw_uri", "uri", "asset_id", "texture_uri", "texture_id", "TextureId", "image")
    return next((str(raw[name]) for name in names if raw.get(name)), "")


def _references(raw, collection):
    refs = [deepcopy(ref) for ref in raw.get("references", []) if isinstance(ref, dict)]
    if collection == "meshes":
        refs.insert(0, {"label": "MeshId", "raw_uri": _raw_reference(raw, collection)})
        texture = next((raw.get(field) for field in ("texture_uri", "texture_id", "TextureId", "TextureID") if raw.get(field)), "")
        if texture:
            refs.append({"label": "TextureId", "raw_uri": texture})
    normalized = []
    for ref in refs:
        uri = str(ref.get("raw_uri") or ref.get("uri") or ref.get("asset_id") or "")
        ident = canonical_id(uri)
        if ident:
            normalized.append({"label": str(ref.get("label") or "AssetId"), "asset_id": ident,
                "uri": "rbxassetid://" + ident, "raw_uri": uri, "id_status": "valid", "normalization_warnings": []})
    return unique_references(normalized)


def classify_texture(name, observations, collections, catalog):
    rectangles = [o for o in observations if isinstance(o.get("rect_size"), (list, tuple)) and len(o["rect_size"]) == 2]
    classification = catalog._classification(name, rectangles, collections)
    if not rectangles:
        classification["observed_rect_kinds"] = []
        classification["classification_conflicts"] = [value for value in classification["classification_conflicts"] if value != "rect_kind_differs_from_type_collection"]
        if classification["kind_source"] == "type_collection":
            classification["kind_source"] = "plugin_metadata"
    return classification


def prepare_record(raw, capture, source_file, collection, catalog):
    raw_uri = _raw_reference(raw, collection)
    ident = canonical_id(raw_uri)
    name = plain(raw.get("display_name") or raw.get("name"))
    if collection == "meshes" and quality(name) < quality(raw.get("item_name")):
        name = plain(raw["item_name"])
    label = plain(capture.get("label") or ("All" if isinstance(capture.get("source"), dict) else source_file.stem))
    kind_label = plain(capture.get("active_type") or raw.get("kind") or "")
    collections = ["Flipbooks"] if token(kind_label) in {"flipbook", "flipbooks"} else ["Statics"] if token(kind_label) in {"static", "statics"} else []
    if token(label) in {"static", "statics"}:
        collections = ["Statics"]
    elif token(label) in {"flipbook", "flipbooks"}:
        collections = ["Flipbooks"]
    tags = [label] if token(label) not in SPECIAL else []
    tags.extend(str(tag) for tag in raw.get("tags", []) if isinstance(tag, str))
    normalized = catalog.normalize_uri("rbxassetid://" + ident if ident else raw_uri)
    stable = json.dumps([collection, ident or raw_uri, name], ensure_ascii=False, separators=(",", ":"))
    source_info = capture.get("source", {})
    observation = {"plugin": PLUGIN, "source": label, "file": source_file.name,
        "index": raw.get("index"), "name": name, "raw_uri": raw_uri,
        "image": raw.get("image"), "rect_size": raw.get("rect_size"),
        "rect_offset": raw.get("rect_offset"), "captured_at": capture.get("captured_at") or source_info.get("captured_at")}
    for field in ("source_path", "item_name", "item_path", "class", "resolution", "source_metadata"):
        if field in raw:
            observation[field] = deepcopy(raw[field])
    row = {"key": hashlib.sha256(stable.encode()).hexdigest()[:24],
        "name": name, **normalized, "raw_uri": raw_uri, "raw_uris": [raw_uri],
        "aliases": unique([plain(raw["item_name"])]) if raw.get("item_name") and raw["item_name"] != name else [], "key_aliases": [], "tags": unique(tags), "collections": collections,
        "source_labels": [PLUGIN + "/" + label], "observations": [observation],
        "in_all_inventory": token(label) == "all", "observation_count": 1,
        "image_path": None, "preview_path": None, "image_status": "not_requested", "image_error": None,
        "plugins": [PLUGIN], "name_provenance": [{"name": name, "plugin": PLUGIN, "file": source_file.name}]}
    if not ident:
        row["id_status"] = normalized.get("id_status") if normalized.get("id_status") != "valid" else "invalid_unrecognized_uri"
    if collection == "textures":
        row.update(classify_texture(name, [observation], collections, catalog))
        explicit_grid = raw.get("grid")
        if type(explicit_grid) is int and explicit_grid in {2, 4, 8} and row["kind"] == "flipbook":
            row.update(grid=explicit_grid, grid_source="plugin_metadata")
    else:
        refs = _references(raw, collection)
        observation.update(mesh_uri=raw_uri, texture_uri=raw.get("texture_uri", ""), references=refs)
        row.update(collection=collection, kind="mesh", grid=0, references=refs)
    return row


def validate_capture(data, path):
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError(f"{path.name}: records list required")
    if data.get("status") in {"error", "running"} or data.get("missing_indexes"):
        raise ValueError(f"{path.name}: capture has errors or missing items")
    if plain(data.get("search")):
        raise ValueError(f"{path.name}: active search filter")
    if data.get("complete") is False:
        raise ValueError(f"{path.name}: incomplete capture")
    if data.get("reported_total") is not None and int(data["reported_total"]) != len(data["records"]):
        raise ValueError(f"{path.name}: reported item count does not match capture")
    return True


def mesh_variants(row):
    variants = [deepcopy(v) for v in row.get("variants", []) if isinstance(v, dict)]
    refs = row.get("references", [])
    textures = [r["uri"] for r in refs if isinstance(r, dict) and token(r.get("label")) == "textureid" and canonical_id(r.get("uri"))]
    if not variants:
        for texture in textures or [""]:
            variants.append({"mesh_uri": row.get("uri", ""), "texture_uri": texture, "names": [row.get("name", "")], "plugins": row.get("plugins", ["ZonitoVisuals"]), "key_aliases": unique([row.get("key")] + row.get("key_aliases", []))})
    return variants


def merge_rows(existing, incoming, collection):
    """One row per valid ID; invalid placeholders stay separate by source identity."""
    groups = defaultdict(list)
    for is_new, rows in ((False, existing), (True, incoming)):
        for raw in rows:
            row = deepcopy(raw)
            ident = canonical_id(row.get("asset_id") or row.get("uri")) if row.get("id_status", "valid") == "valid" else None
            identity = ident if ident else "invalid:" + str(row.get("key") or hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest())
            groups[identity].append((is_new, row))
    result, renamed, absorbed = [], [], 0
    for identity, members in groups.items():
        old = [r for new, r in members if not new]
        # Prefer the existing key with the best name; order breaks equal ties.
        base = deepcopy(max(old or [r for _, r in members], key=lambda r: quality(r.get("name"))))
        old_name = base.get("name", "")
        best_name = max((r.get("name", "") for _, r in members), key=quality)
        if quality(best_name) > quality(old_name):
            base["name"] = best_name
            renamed.append({"asset_id": base.get("asset_id"), "before": old_name, "after": best_name})
        all_names = unique([r.get("name", "") for _, r in members] + [v for _, r in members for v in r.get("aliases", [])])
        base["aliases"] = sorted((n for n in all_names if n and n != base.get("name")), key=str.casefold)
        base["key_aliases"] = unique([r.get("key") for _, r in members if r.get("key") != base.get("key")] + [v for _, r in members for v in r.get("key_aliases", [])])
        for field in LIST_FIELDS:
            if field in base or any(field in r for _, r in members):
                base[field] = unique([v for _, r in members for v in r.get(field, [])])
        observations = []
        for is_new, row in members:
            for observation in row.get("observations", []):
                observation = deepcopy(observation)
                observation.setdefault("plugin", PLUGIN if is_new else "ZonitoVisuals")
                observations.append(observation)
        base["observations"] = unique(observations)
        base["observation_count"] = len(base["observations"])
        base["in_all_inventory"] = any(r.get("in_all_inventory") for _, r in members)
        base["plugins"] = unique([p for is_new, r in members for p in r.get("plugins", [PLUGIN if is_new else "ZonitoVisuals"])])
        base["name_provenance"] = unique([p for is_new, r in members for p in r.get("name_provenance", [{"name": r.get("name", ""), "plugin": PLUGIN if is_new else "ZonitoVisuals"}])])
        # Preserve actual cache state rather than overwriting it with a new observation.
        image_row = next((r for _, r in members if r.get("image_path") and r.get("image_status") in {"cached", "downloaded"}), None)
        if image_row:
            for field in IMAGE_FIELDS:
                if field in image_row:
                    base[field] = deepcopy(image_row[field])
        if collection == "meshes":
            base["references"] = unique_references([ref for _, r in members for ref in r.get("references", [])])
            variants = {}
            for _, row in members:
                for variant in mesh_variants(row):
                    texture_id = canonical_id(variant.get("texture_uri")) or ""
                    if texture_id not in variants:
                        variants[texture_id] = deepcopy(variant)
                    else:
                        for field in ("names", "plugins", "key_aliases"):
                            variants[texture_id][field] = unique(variants[texture_id].get(field, []) + variant.get(field, []))
            base["variants"] = [variants[k] for k in sorted(variants, key=lambda v: int(v) if v else 0)]
            # First TextureId remains the primary variant for legacy callers.
            primary_texture = base["variants"][0].get("texture_uri", "")
            base["primary_texture_uri"] = primary_texture
            base["references"].sort(key=lambda r: (0 if token(r.get("label")) == "meshid" else 1 if r.get("uri") == primary_texture else 2, r.get("uri", "")))
        else:
            # Combine type evidence across captures without inventing grids.
            classification = classify_texture(base.get("name", ""), base["observations"], base.get("collections", []), _catalog)
            proven_grid = next((r for _, r in members if r.get("grid") in {2, 4, 8} and r.get("grid_source") in {"plugin_metadata", "name"}), None)
            base.update(classification)
            if proven_grid and base["kind"] == "flipbook":
                base.update(grid=proven_grid["grid"], grid_source=proven_grid["grid_source"])
        absorbed += len(members) - 1
        result.append(base)
    result.sort(key=lambda r: (str(r.get("name", "")).casefold(), str(r.get("asset_id", "")), r["key"]))
    old_ids = {canonical_id(r.get("asset_id") or r.get("uri")) for r in existing}
    new_ids = {canonical_id(r.get("asset_id") or r.get("uri")) for r in incoming} - {None}
    report = {"collection": collection, "before_rows": len(existing), "incoming_observations": sum(len(r.get("observations", [])) for r in incoming), "incoming_asset_rows": len(incoming), "after_rows": len(result),
        "unique_valid_ids": len({canonical_id(r.get("asset_id")) for r in result if r.get("id_status") == "valid"} - {None}),
        "new_ids": len(new_ids - old_ids), "existing_ids_seen": len(new_ids & old_ids), "collapsed_rows": absorbed,
        "renamed": renamed, "mesh_texture_variants": sum(len(r.get("variants", [])) for r in result) if collection == "meshes" else None}
    assert len({r["key"] for r in result}) == len(result), "Duplicate stable key after merge"
    return result, report


def apply_ui_memberships(rows, directory):
    """Add actual filter membership; plugin filters can also match item names."""
    by_id = {canonical_id(row.get("asset_id")): row for row in rows if canonical_id(row.get("asset_id"))}
    found = []
    for path in sorted(Path(directory).glob("Textures_*.json")):
        capture = json.loads(path.read_text(encoding="utf-8-sig"))
        ids = capture.get("ids")
        if not isinstance(ids, list) or capture.get("missing") or capture.get("missing_indexes") or capture.get("count") != len(ids):
            raise ValueError(f"{path.name}: incomplete UI category inventory")
        label = str(capture.get("label") or path.stem).removeprefix("Textures ")
        for uri in ids:
            ident = canonical_id(uri)
            if ident not in by_id:
                raise ValueError(f"{path.name}: UI ID absent from complete metadata: {uri}")
            row = by_id[ident]
            label_token = token(label)
            if label_token in {"static", "statics", "flipbook", "flipbooks", "user", "favorites"}:
                bucket = "collections"
                membership = "Statics" if label_token in {"static", "statics"} else "Flipbooks" if label_token in {"flipbook", "flipbooks"} else label
            else:
                bucket, membership = "tags", label
            if label_token != "all" and membership not in row[bucket]:
                row[bucket].append(membership)
            observation = {"plugin": PLUGIN, "source": label, "file": path.name, "raw_uri": uri, "evidence": "live_ui_filter_membership"}
            row["observations"] = unique(row.get("observations", []) + [observation])
            row["observation_count"] = len(row["observations"])
        found.append({"label": label, "count": len(ids), "file": path.name})
    return found


def merge_saved_plugin(root, rows, collection, catalog):
    global _catalog
    _catalog = catalog
    directory = Path(root) / "source" / "vfx-studio" / collection
    path = directory / (collection + "-metadata.json")
    if not path.exists():
        return rows, None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_capture(data, path)
    incoming = [prepare_record(raw, data, path, collection, catalog) for raw in data["records"]]
    # Coalesce the immutable metadata before adding UI category observations.
    incoming, _ = merge_rows([], incoming, collection)
    categories = apply_ui_memberships(incoming, Path(root) / "source/vfx-studio/verified") if collection == "textures" else []
    merged, report = merge_rows(rows, incoming, collection)
    report["metadata_rows"] = len(data["records"])
    report["collapsed_rows"] += len(data["records"]) - len(incoming)
    report["verified_ui_categories"] = categories
    return merged, report


def _enriched_csv(path, rows, fields, catalog):
    fields = tuple(fields) + ("aliases", "plugins", "key_aliases", "name_provenance", "variants")
    fields = tuple(dict.fromkeys(fields))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(fields)
    writer.writerows([catalog._excel_safe(row.get(field)) for field in fields] for row in rows)
    catalog._atomic_bytes(path, stream.getvalue().encode("utf-8-sig"))


def enrich_export_files(rows, summary, directory, collection, catalog, assets):
    fields = catalog.CSV_FIELDS if collection == "textures" else assets.CSV_FIELDS
    basename = "textures" if collection == "textures" else "assets"
    _enriched_csv(directory / (basename + ".csv"), rows, fields, catalog)
    with closing(sqlite3.connect(directory / (basename + ".sqlite"))) as db:
        db.execute("CREATE TABLE IF NOT EXISTS plugin_provenance (asset_key TEXT PRIMARY KEY, plugins_json TEXT NOT NULL, names_json TEXT NOT NULL, key_aliases_json TEXT NOT NULL, variants_json TEXT NOT NULL)")
        db.executemany("INSERT OR REPLACE INTO plugin_provenance VALUES (?,?,?,?,?)", [(r["key"], json.dumps(r.get("plugins", []), ensure_ascii=False), json.dumps(r.get("name_provenance", []), ensure_ascii=False), json.dumps(r.get("key_aliases", [])), json.dumps(r.get("variants", []), ensure_ascii=False)) for r in rows])
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('summary',?)", (json.dumps(summary, ensure_ascii=False),))
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        db.commit()


def export_merged(rows, root, collection, report, catalog, assets):
    started = time.monotonic()
    directory = root if collection == "textures" else root / collection
    previous = json.loads((directory / "summary.json").read_text(encoding="utf-8")) if (directory / "summary.json").exists() else {}
    coverage = deepcopy(previous.get("capture_coverage", {}))
    coverage["plugin_merge"] = report
    raw_count = sum(len(row.get("observations", [])) for row in rows)
    if collection == "textures":
        summary = catalog.make_summary(rows, raw_count, coverage, started, phase="plugin_merged")
        summary["stats"]["duplicate_rows_note"] = "One row per valid canonical Roblox ID. Names and source keys are aliases; invalid placeholders remain separate."
        catalog.export_catalogue(rows, summary, root)
        fields, basename = catalog.CSV_FIELDS, "textures"
    else:
        tags = sorted({tag for row in rows for tag in row.get("tags", [])}, key=str.casefold)
        summary = assets.make_asset_summary(rows, raw_count, tags, coverage, collection, started, phase="plugin_merged")
        summary["notes"] = ["One row per valid canonical Roblox mesh ID; texture variants are retained in variants and references.", "Names, source plugin, aliases and immutable capture evidence are preserved.", "Preview downloads are Roblox thumbnails, not original mesh geometry."]
        assets.export_assets(rows, summary, directory)
        fields, basename = assets.CSV_FIELDS, "assets"
    summary["plugin_merge"] = report
    catalog._write_json(directory / "summary.json", summary)
    enrich_export_files(rows, summary, directory, collection, catalog, assets)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--backup", type=Path, help="ZIP path required when applying; excludes unchanged image assets")
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error("--apply requires --backup")
    root = args.root.resolve()
    sys.path.insert(0, str(root / "tool"))
    global _catalog
    _catalog = importlib.import_module("catalog")
    assets = importlib.import_module("asset_catalog")
    incoming = defaultdict(list)
    evidence, evidence_files = [], []
    metadata_files = list(args.captures.rglob("*-metadata.json"))
    for path in sorted(metadata_files or args.captures.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or "records" not in data:
            continue
        validate_capture(data, path)
        collection = str(data.get("collection") or ("meshes" if path.name.startswith("meshes-") else "textures")).casefold()
        collection = {"texture": "textures", "mesh": "meshes"}.get(collection, collection)
        if collection not in {"textures", "meshes"}:
            continue
        incoming[collection].extend(prepare_record(raw, data, path, collection, _catalog) for raw in data["records"])
        evidence.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "collection": collection, "records": len(data["records"])})
        evidence_files.append((path, collection))
    if not incoming:
        raise ValueError("No texture or mesh captures found")
    reports, prepared = [], {}
    for collection, rows in incoming.items():
        current = root / ("textures.json" if collection == "textures" else "meshes/assets.json")
        existing = json.loads(current.read_text(encoding="utf-8-sig")) if current.exists() else []
        # Collapse metadata first so one UI membership observation is added per ID.
        metadata_count = len(rows)
        rows, _ = merge_rows([], rows, collection)
        categories = apply_ui_memberships(rows, args.captures / "verified") if collection == "textures" else []
        prepared[collection], report = merge_rows(existing, rows, collection)
        report["metadata_rows"] = metadata_count
        report["collapsed_rows"] += metadata_count - len(rows)
        report["verified_ui_categories"] = categories
        reports.append(report)
    report = {"plugin": PLUGIN, "generated_at": _catalog.utc_now(), "applied": False, "apply_requested": args.apply, "phase": "prepared", "captures": evidence, "collections": reports, "completed_collections": []}
    _catalog._write_json(args.report, report)
    if args.apply:
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        if args.backup.exists():
            raise ValueError("Backup target exists; choose a new ZIP path")
        names = ["textures.json", "textures.csv", "textures.sqlite", "summary.json", "failures.json", "catalogue.html", "meshes/assets.json", "meshes/assets.csv", "meshes/assets.sqlite", "meshes/summary.json", "meshes/failures.json"]
        paths = [root / name for name in names]
        paths.extend((root / "tags").rglob("*"))
        paths.extend((root / "meshes/tags").rglob("*"))
        with zipfile.ZipFile(args.backup, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
        for path, collection in evidence_files:
            target = root / "source" / "vfx-studio" / collection / path.name
            if target.exists() and target.read_bytes() != path.read_bytes():
                target = target.with_name(target.stem + "-" + hashlib.sha256(path.read_bytes()).hexdigest()[:12] + ".json")
            _catalog._atomic_bytes(target, path.read_bytes())
        for path in sorted((args.captures / "verified").glob("*.json")):
            _catalog._atomic_bytes(root / "source/vfx-studio/verified" / path.name, path.read_bytes())
        for collection, rows in prepared.items():
            if args.download:
                from download import download_previews
                rows = download_previews(rows, root if collection == "textures" else root / collection, workers=args.workers)
            export_merged(rows, root, collection, next(r for r in reports if r["collection"] == collection), _catalog, assets)
            report["completed_collections"].append(collection)
            next(r for r in reports if r["collection"] == collection)["image_status_counts"] = dict(Counter(row.get("image_status") for row in rows))
            _catalog._write_json(args.report, report)
        assets.rebuild_root_gallery(root)
        report.update(applied=True, phase="complete", backup_sha256=hashlib.sha256(args.backup.read_bytes()).hexdigest())
        _catalog._write_json(args.report, report)
    print(json.dumps({"applied": args.apply, "collections": [{k: v for k, v in r.items() if k != "renamed"} for r in reports]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
