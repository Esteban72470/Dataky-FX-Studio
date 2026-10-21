"""Build isolated Beams/Meshes catalogues and integrate their offline previews.

Textures exports are read only. Each collection owns source/, assets.json,
assets.csv, assets.sqlite, tags/, images/, summary.json and failures.json.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing, redirect_stdout
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
import time

from catalog import _atomic_bytes, _excel_safe, _write_json, normalize_uri, utc_now


COLLECTIONS = ("beams", "meshes")
SPECIAL_LABELS = {"all", "personal", "recentlyused"}
IMAGE_FIELDS = ("image_path", "preview_path", "image_status", "image_error", "image_source", "width", "height")
CSV_FIELDS = ("key", "collection", "asset_id", "name", "uri", "tags", "collections", "id_status",
              "image_path", "preview_path", "image_status", "image_error", "width", "height",
              "references", "raw_uris", "normalization_warnings", "aliases")


def _plain(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).split())


def _token(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _is_tag(label):
    return _token(label) not in SPECIAL_LABELS


def normalize_reference(value):
    """Read explicit ID parameters before thumbnail width/height numbers."""
    raw = str(value or "").strip()
    if raw.lower().startswith("rbxasset://"):
        return {"asset_id": "", "uri": raw, "raw_uri": raw, "id_status": "builtin_uri",
                "normalization_warnings": [], "uri_parse_method": "builtin_uri"}
    query_id = re.search(r"(?:[?&]|^)(?:id|assetid)=([0-9]+)(?:[&#]|$)", raw, re.IGNORECASE)
    prefix_ids = re.findall(r"rbxassetid://([0-9]+)", raw, re.IGNORECASE)
    if query_id:
        candidate, method = query_id.group(1), "query_id"
    elif prefix_ids:
        candidate, method = prefix_ids[-1], "rbxassetid"
    elif re.fullmatch(r"[0-9]+", raw):
        candidate, method = raw, "numeric"
    else:
        values = re.findall(r"[0-9]+", raw)
        candidate, method = (values[-1] if values else ""), "numeric_fallback"
    normalized = normalize_uri("rbxassetid://" + candidate if candidate else raw)
    warnings = []
    if raw != normalized["uri"]:
        warnings.append("normalized_uri")
    if raw.lower().count("rbxassetid://") > 1:
        warnings.append("repeated_uri_prefix")
    if method == "numeric_fallback" and candidate:
        warnings.append("unrecognized_uri_used_last_numeric_token")
    if not candidate:
        warnings.append("no_numeric_id")
    return {**normalized, "raw_uri": raw, "normalization_warnings": warnings, "uri_parse_method": method}


def _references(record, collection):
    candidates = []
    for value in record.get("references", []) if isinstance(record.get("references"), list) else []:
        if isinstance(value, dict):
            candidates.append((str(value.get("label") or "AssetId"), value.get("raw_uri") or value.get("uri") or ""))
    if record.get("mesh_uri"):
        candidates.append(("MeshId", record["mesh_uri"]))
    if record.get("texture_uri"):
        candidates.append(("TextureId", record["texture_uri"]))
    primary = record.get("mesh_uri") if collection == "meshes" else record.get("raw_uri")
    primary = primary or record.get("raw_uri") or record.get("texture_uri") or ""
    if primary:
        candidates.append(("MeshId" if collection == "meshes" else "TextureId", primary))
    result, seen = [], set()
    for label, raw in candidates:
        normalized = normalize_reference(raw)
        key = (label, normalized["uri"])
        if key not in seen:
            result.append({"label": label, **normalized})
            seen.add(key)
    return normalize_reference(primary), result


def _source_coverage(data, path, collection):
    label = str(data.get("label") or path.stem)
    issues = []
    if data.get("collection") != collection:
        issues.append("collection_metadata_mismatch")
    if _plain(data.get("active_collection")).casefold() != collection:
        issues.append("active_collection_mismatch")
    expected_filter = "tags" if _token(label) == "all" else _plain(label).casefold()
    if not isinstance(data.get("active_filter"), str) or _plain(data.get("active_filter")).casefold() != expected_filter:
        issues.append("active_filter_mismatch")
    if str(data.get("search") or "").strip():
        issues.append("search_filter_was_active")
    first = data.get("first_index")
    maximum = data.get("max_index")
    if isinstance(first, bool) or not isinstance(first, int) or first < 0:
        issues.append("invalid_first_index")
        first = 3
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < first - 1:
        issues.append("invalid_max_index")
        maximum = first - 1
    records = data.get("records")
    if not isinstance(records, list):
        issues.append("records_not_list")
        records = []
    indexes, fingerprints = [], defaultdict(set)
    invalid_indexes = 0
    for record in records:
        if not isinstance(record, dict):
            invalid_indexes += 1
            continue
        index = record.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < first or index > maximum:
            invalid_indexes += 1
            continue
        indexes.append(index)
        fingerprints[index].add(json.dumps({key: record.get(key) for key in ("name", "raw_uri", "mesh_uri", "texture_uri", "references")}, sort_keys=True))
    if maximum - first > 1_000_000:
        issues.append("index_range_exceeds_safety_bound")
        missing = []
    else:
        missing = sorted(set(range(first, maximum + 1)).difference(indexes))
    if missing:
        issues.append("computed_missing_indexes")
    declared = data.get("missing_indexes")
    if not isinstance(declared, list):
        issues.append("missing_indexes_not_recorded")
    elif declared:
        issues.append("capture_reported_missing_indexes")
    if invalid_indexes:
        issues.append("invalid_record_indexes")
    conflicts = sorted(index for index, values in fingerprints.items() if len(values) > 1)
    if conflicts:
        issues.append("conflicting_records_at_same_index")
    return {"label": label, "file": path.name, "complete": not issues, "issues": issues,
            "raw_records": len(records), "first_index": first, "max_index": maximum,
            "unique_indexes": len(set(indexes)), "computed_missing_indexes": missing,
            "reported_missing_indexes": declared, "invalid_index_count": invalid_indexes,
            "conflicting_indexes": conflicts, "captured_at": data.get("captured_at"),
            "active_collection": data.get("active_collection"), "active_filter": data.get("active_filter"),
            "search": data.get("search"), "available_tags": data.get("available_tags")}


def load_asset_sources(source_dir, collection):
    captures, infos = {}, {}
    for path in sorted(Path(source_dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid source object: {path}")
        info = _source_coverage(data, path, collection)
        label = info["label"]
        if label in captures:
            raise ValueError(f"Duplicate {collection} source label: {label}")
        captures[label], infos[label] = data, info
    all_label = next((label for label in captures if _token(label) == "all"), None)
    expected_tags = None
    if all_label:
        inventory = captures[all_label]
        expected_tags = inventory.get("available_tags", inventory.get("expected_tags"))
        if not isinstance(expected_tags, list) or not all(isinstance(tag, str) and tag for tag in expected_tags):
            infos[all_label]["issues"].append("available_or_expected_tags_not_recorded")
            infos[all_label]["complete"] = False
            expected_tags = None
    expected_tags = sorted(set(tag for tag in (expected_tags or []) if _is_tag(tag)), key=str.casefold)
    missing = ([] if all_label else ["All"]) + [tag for tag in expected_tags if tag not in captures]
    incomplete = [label for label, info in infos.items() if not info["complete"]]
    coverage = {"complete": not missing and not incomplete, "required_labels": ["All"] + expected_tags,
                "missing_required_labels": missing, "excluded_incomplete_labels": incomplete,
                "expected_tags": expected_tags, "sources": infos}
    return {label: data for label, data in captures.items() if infos[label]["complete"]}, coverage


def normalize_assets(sources, collection):
    merged, raw_count = {}, 0
    tag_names = sorted((label for label in sources if _is_tag(label)), key=str.casefold)
    for label, data in sources.items():
        for raw in data.get("records", []):
            raw_count += 1
            name = str(raw.get("name") or "")
            primary, references = _references(raw, collection)
            identity = (primary["asset_id"] or primary["uri"], name)
            if identity not in merged:
                stable = json.dumps([collection, primary["uri"], name], ensure_ascii=False, separators=(",", ":"))
                merged[identity] = {"key": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24],
                    "collection": collection, "kind": "beam" if collection == "beams" else "mesh",
                    "grid": 0, "name": name, **primary, "raw_uris": [], "references": [],
                    "tags": [], "collections": [], "source_labels": [], "observations": [], "aliases": [],
                    "image_path": None, "preview_path": None, "image_status": "not_requested", "image_error": None}
            row = merged[identity]
            if primary["raw_uri"] not in row["raw_uris"]:
                row["raw_uris"].append(primary["raw_uri"])
            for warning in primary["normalization_warnings"]:
                if warning not in row["normalization_warnings"]:
                    row["normalization_warnings"].append(warning)
            if label not in row["source_labels"]:
                row["source_labels"].append(label)
            bucket = "tags" if _is_tag(label) else "collections"
            if _token(label) != "all" and label not in row[bucket]:
                row[bucket].append(label)
            existing_refs = {(ref["label"], ref["uri"]) for ref in row["references"]}
            for reference in references:
                if (reference["label"], reference["uri"]) not in existing_refs:
                    row["references"].append(reference)
                    existing_refs.add((reference["label"], reference["uri"]))
            row["observations"].append({"source": label, "index": raw.get("index"),
                "raw_uri": raw.get("raw_uri"), "image": raw.get("image"),
                "mesh_uri": raw.get("mesh_uri"), "texture_uri": raw.get("texture_uri"),
                "references": raw.get("references", [])})
    names_by_id = defaultdict(set)
    for row in merged.values():
        if row["asset_id"]:
            names_by_id[row["asset_id"]].add(row["name"])
    rows = list(merged.values())
    for row in rows:
        row["tags"].sort(key=str.casefold)
        row["collections"].sort(key=str.casefold)
        row["source_labels"].sort(key=str.casefold)
        row["in_all_inventory"] = any(_token(label) == "all" for label in row["source_labels"])
        row["observation_count"] = len(row["observations"])
        row["aliases"] = sorted(names_by_id[row["asset_id"]] - {row["name"]}) if row["asset_id"] else []
    rows.sort(key=lambda row: (row["name"].casefold(), row["asset_id"], row["key"]))
    return rows, raw_count, tag_names


def _tag_filename(tag):
    stem = "".join(character if character.isalnum() or character in "-_ " else "_" for character in tag).strip(" .")[:70]
    return f"{stem or 'tag'}-{hashlib.sha256(tag.encode('utf-8')).hexdigest()[:8]}"


def make_asset_summary(rows, raw_count, tags, coverage, collection, started, phase="indexed", limited=False):
    return {"collection": collection, "generated_at": utc_now(), "phase": phase,
        "elapsed_seconds": round(time.monotonic() - started, 2), "limited_smokecheck": limited,
        "capture_coverage": coverage, "tag_names": tags,
        "stats": {"asset_identities": len(rows), "source_observations": raw_count,
            "extra_observations_collapsed": raw_count - len(rows),
            "unique_asset_ids": len({row["asset_id"] for row in rows if row["asset_id"]}),
            "valid_unique_asset_ids": len({row["asset_id"] for row in rows if row["id_status"] == "valid"}),
            "invalid_or_deleted_identities": sum(row["id_status"] != "valid" for row in rows),
            "identities_with_image": sum(bool(row.get("image_path")) for row in rows),
            "unique_asset_ids_with_image": len({row["asset_id"] for row in rows if row.get("image_path")}),
            "identities_absent_from_all": sum(not row["in_all_inventory"] for row in rows),
            "reference_count": sum(len(row["references"]) for row in rows),
            "image_status_counts": dict(sorted(Counter(row["image_status"] for row in rows).items())),
            "per_tag": {tag: sum(tag in row["tags"] for row in rows) for tag in tags}},
        "notes": ["IDs and references come from the installed plugin's captured asset records.",
            "Images are public Roblox-generated thumbnails, not original mesh files or texture downloads.",
            "Primary asset IDs, secondary references, category membership and raw capture evidence are preserved.",
            "The textures JSON, CSV, SQLite and source files are never rewritten by this tool."]}


def _write_asset_csv(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_FIELDS)
    for row in rows:
        writer.writerow([_excel_safe(row.get(key)) for key in CSV_FIELDS])
    _atomic_bytes(path, buffer.getvalue().encode("utf-8-sig"))


def _write_asset_sqlite(path, rows, summary):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".assets-", suffix=".sqlite", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE assets (key TEXT PRIMARY KEY, collection TEXT NOT NULL, asset_id TEXT NOT NULL,
                    name TEXT NOT NULL, uri TEXT NOT NULL, kind TEXT NOT NULL, id_status TEXT NOT NULL,
                    image_path TEXT, preview_path TEXT, image_status TEXT NOT NULL, image_error TEXT,
                    width INTEGER, height INTEGER, data_json TEXT NOT NULL);
                CREATE TABLE tags (name TEXT PRIMARY KEY);
                CREATE TABLE asset_tags (asset_key TEXT REFERENCES assets(key), tag TEXT REFERENCES tags(name),
                    PRIMARY KEY(asset_key,tag));
                CREATE TABLE asset_references (asset_key TEXT REFERENCES assets(key), label TEXT NOT NULL,
                    asset_id TEXT NOT NULL, uri TEXT NOT NULL, raw_uri TEXT NOT NULL, id_status TEXT NOT NULL,
                    PRIMARY KEY(asset_key,label,uri));
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
                CREATE INDEX assets_asset_id ON assets(asset_id);
                CREATE INDEX assets_name ON assets(name COLLATE NOCASE);
                CREATE INDEX asset_tags_tag ON asset_tags(tag);
                CREATE INDEX asset_references_id ON asset_references(asset_id);
            """)
            db.executemany("INSERT INTO tags VALUES (?)", [(tag,) for tag in summary["tag_names"]])
            for row in rows:
                db.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    row["key"], row["collection"], row["asset_id"], row["name"], row["uri"], row["kind"], row["id_status"],
                    row.get("image_path"), row.get("preview_path"), row["image_status"], row.get("image_error"),
                    row.get("width"), row.get("height"), json.dumps(row, ensure_ascii=False)))
                db.executemany("INSERT INTO asset_tags VALUES (?,?)", [(row["key"], tag) for tag in row["tags"]])
                db.executemany("INSERT INTO asset_references VALUES (?,?,?,?,?,?)", [
                    (row["key"], ref["label"], ref["asset_id"], ref["uri"], ref["raw_uri"], ref["id_status"]) for ref in row["references"]])
            db.execute("INSERT INTO metadata VALUES ('summary',?)", (json.dumps(summary, ensure_ascii=False),))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Asset SQLite integrity check failed")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_assets(rows, summary, directory):
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(directory / "assets.json", rows)
    _write_asset_csv(directory / "assets.csv", rows)
    _write_asset_sqlite(directory / "assets.sqlite", rows, summary)
    tag_index = {}
    for tag in summary["tag_names"]:
        tagged = [row for row in rows if tag in row["tags"]]
        basename = _tag_filename(tag)
        _write_json(directory / "tags" / f"{basename}.json", tagged)
        _write_asset_csv(directory / "tags" / f"{basename}.csv", tagged)
        tag_index[tag] = {"json": f"tags/{basename}.json", "csv": f"tags/{basename}.csv", "count": len(tagged)}
    _write_json(directory / "tags" / "index.json", tag_index)
    failures = [{"key": row["key"], "asset_id": row["asset_id"], "name": row["name"], "tags": row["tags"],
                 "id_status": row["id_status"], "image_status": row["image_status"], "image_error": row.get("image_error")}
                for row in rows if row["id_status"] != "valid" or row["image_status"] not in {"not_requested", "downloaded", "cached"}]
    _write_json(directory / "failures.json", failures)
    _write_json(directory / "summary.json", summary)


def _reuse_cached_images(rows, directory, root):
    previous_path = directory / "assets.json"
    previous = {}
    if previous_path.is_file():
        data = json.loads(previous_path.read_text(encoding="utf-8"))
        previous = {row["key"]: row for row in data if isinstance(row, dict) and "key" in row}
    for row in rows:
        old = previous.get(row["key"], {})
        for field in IMAGE_FIELDS:
            if field in old:
                row[field] = old[field]
        if row.get("image_path") and not (directory / row["image_path"]).is_file():
            row.update(image_path=None, preview_path=None, image_status="not_requested", image_error=None)
    # Reuse verified public thumbnails already saved by the texture catalogue.
    # Only the new collection's directory is written.
    from download import _open_verified
    for asset_id in {row["asset_id"] for row in rows if row["id_status"] == "valid"}:
        target = directory / "images" / f"{asset_id}.png"
        shared = root / "images" / f"{asset_id}.png"
        if not target.is_file() and shared.is_file() and _open_verified(shared) is not None:
            _atomic_bytes(target, shared.read_bytes())
    for row in rows:
        target = directory / "images" / f"{row['asset_id']}.png"
        if row["id_status"] == "valid" and target.is_file():
            image = _open_verified(target)
            if image is not None:
                row.update(image_path=target.relative_to(directory).as_posix(), preview_path=target.relative_to(directory).as_posix(),
                           image_status="cached", image_error=None, image_source="Roblox thumbnail 420x420", width=image.width, height=image.height)


def rebuild_extra(root, collection, *, workers=12, skip_download=False, allow_partial=False, limit=None):
    if collection not in COLLECTIONS:
        raise ValueError(f"Unsupported collection: {collection}")
    started = time.monotonic()
    root = Path(root).resolve()
    sources, coverage = load_asset_sources(root / collection / "source", collection)
    if not coverage["complete"] and not allow_partial:
        raise ValueError(f"{collection}: capture incomplete; missing={coverage['missing_required_labels']}; excluded={coverage['excluded_incomplete_labels']}")
    if coverage["excluded_incomplete_labels"]:
        print(f"[{collection}] Excluded incomplete captures: {', '.join(coverage['excluded_incomplete_labels'])}", flush=True)
    rows, raw_count, tags = normalize_assets(sources, collection)
    if not sources:
        raise ValueError(f"{collection}: no complete source captures")
    directory = (root / "smokecheck" / collection) if limit else (root / collection)
    if limit:
        rows = rows[:limit]
        raw_count = sum(row["observation_count"] for row in rows)
    _reuse_cached_images(rows, directory, root)
    summary = make_asset_summary(rows, raw_count, tags, coverage, collection, started, limited=bool(limit))
    export_assets(rows, summary, directory)
    print(f"[{collection}] IDs saved: {len(rows)} identities; coverage complete: {coverage['complete']}", flush=True)
    if not skip_download:
        from download import download_previews
        rows = download_previews(rows, directory, workers=workers)
        summary = make_asset_summary(rows, raw_count, tags, coverage, collection, started, phase="downloaded", limited=bool(limit))
        export_assets(rows, summary, directory)
    return rows, summary


def _gallery_path(collection, path):
    if not isinstance(path, str) or not path:
        return None
    value = path.replace("\\", "/")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or ":" in value:
        return None
    return collection + "/" + value


def load_extra_collections(root):
    """Read isolated exports and prefix their local paths for the root gallery."""
    root = Path(root)
    extras = {}
    for collection in COLLECTIONS:
        records_path = root / collection / "assets.json"
        if not records_path.is_file():
            continue
        records = json.loads(records_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"Invalid exported {collection} records")
        summary_path = root / collection / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
        prepared = []
        for record in records:
            item = dict(record)
            for field in ("image_path", "preview_path"):
                item[field] = _gallery_path(collection, item.get(field))
            prepared.append(item)
        extras[collection] = {"records": prepared, "summary": summary}
    return extras


def rebuild_root_gallery(root):
    """Rewrite only catalogue.html; all texture exports remain byte-for-byte intact."""
    from gallery import build_gallery
    root = Path(root).resolve()
    textures = json.loads((root / "textures.json").read_text(encoding="utf-8")) if (root / "textures.json").is_file() else []
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8")) if (root / "summary.json").is_file() else {}
    with tempfile.TemporaryDirectory(prefix=".gallery-assets-", dir=root) as temporary:
        generated = build_gallery(textures, Path(temporary), summary, extra_collections=load_extra_collections(root))
        os.replace(generated, root / "catalogue.html")
    return root / "catalogue.html"


def _selftest():
    assert normalize_reference("rbxthumb://type=Asset&id=5922912225&w=150&h=150")["asset_id"] == "5922912225"
    assert normalize_reference("https://www.roblox.com/asset/?id=123&version=456")["asset_id"] == "123"
    assert normalize_reference("rbxassetid://rbxassetid://123")["asset_id"] == "123"
    assert normalize_reference("rbxassetid://01")["id_status"] != "valid"
    assert normalize_reference("rbxasset://textures/grid4.png")["asset_id"] == ""
    def row(index, name, mesh, texture=""):
        refs = [{"label": "MeshId", "raw_uri": mesh}]
        if texture:
            refs.append({"label": "TextureId", "raw_uri": texture})
        return {"index": index, "name": name, "raw_uri": mesh, "mesh_uri": mesh, "texture_uri": texture, "image": "", "references": refs}
    def capture(label, records):
        return {"collection": "meshes", "label": label, "records": records, "first_index": 3,
            "max_index": max((value["index"] for value in records), default=2), "missing_indexes": [],
            "active_collection": "Meshes", "active_filter": "Tags" if label == "All" else label,
            "search": "", "captured_at": utc_now(), "available_tags": ["Lightning", "Empty tag", "Personal", "Recently Used"]}
    with tempfile.TemporaryDirectory(prefix="zonito-asset-catalogue-test-") as temporary:
        root = Path(temporary)
        source = root / "meshes" / "source"
        source.mkdir(parents=True)
        data = [row(3, "Mesh A", "rbxassetid://123", "rbxassetid://456"), row(4, "Mesh A", "rbxassetid://rbxassetid://123", "rbxassetid://456"), row(5, "Invalid", "rbxassetid://0")]
        _write_json(source / "All.json", capture("All", data))
        _write_json(source / "Lightning.json", capture("Lightning", [row(3, "Mesh A", "rbxassetid://123", "rbxassetid://456")]))
        _write_json(source / "Empty.json", capture("Empty tag", []))
        sources, coverage = load_asset_sources(source, "meshes")
        assert coverage["complete"], coverage
        rows, count, tags = normalize_assets(sources, "meshes")
        assert len(rows) == 2 and count == 4 and tags == ["Empty tag", "Lightning"]
        mesh = next(value for value in rows if value["name"] == "Mesh A")
        assert mesh["tags"] == ["Lightning"] and mesh["observation_count"] == 3
        assert {(ref["label"], ref["asset_id"]) for ref in mesh["references"]} == {("MeshId", "123"), ("TextureId", "456")}
        _write_json(root / "textures.json", [{"sentinel": "existing texture data"}])
        before = (root / "textures.json").read_bytes()
        with redirect_stdout(io.StringIO()):
            exported, summary = rebuild_extra(root, "meshes", skip_download=True)
        assert (root / "textures.json").read_bytes() == before
        with closing(sqlite3.connect(root / "meshes" / "assets.sqlite")) as db:
            assert db.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 2
            assert db.execute("SELECT COUNT(*) FROM asset_references").fetchone()[0] == 3
            assert db.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 2
        assert (root / "meshes" / "assets.csv").read_bytes().startswith(b"\xef\xbb\xbf")
        exported[0]["image_path"] = "images/123.png"
        exported[0]["preview_path"] = "images/123.png"
        _write_json(root / "meshes" / "assets.json", exported)
        loaded = load_extra_collections(root)
        assert loaded["meshes"]["records"][0]["image_path"] == "meshes/images/123.png"
        rebuild_root_gallery(root)
        rendered = (root / "catalogue.html").read_text(encoding="utf-8")
        assert "meshes/images/123.png" in rendered
        assert (root / "textures.json").read_bytes() == before
        broken = capture("Lightning", [row(3, "Mesh A", "rbxassetid://123"), row(5, "Mesh A", "rbxassetid://123")])
        _write_json(source / "Lightning.json", broken)
        filtered, incomplete = load_asset_sources(source, "meshes")
        assert not incomplete["complete"] and "Lightning" not in filtered
        try:
            rebuild_extra(root, "meshes", skip_download=True)
            raise AssertionError("Incomplete tag capture was accepted")
        except ValueError:
            pass
        (source / "Empty.json").unlink()
        _, missing = load_asset_sources(source, "meshes")
        assert "Empty tag" in missing["missing_required_labels"]
        wrong = capture("All", data)
        wrong["active_collection"] = "Beams"
        assert not _source_coverage(wrong, source / "All.json", "meshes")["complete"]
    print("[self-test] PASS: query IDs, secondary references, exact tag joins, source coverage, incomplete exclusion, SQLite, CSV, root image paths and unchanged texture data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--collections", nargs="+", choices=COLLECTIONS, default=list(COLLECTIONS))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--limit", type=int, help="Write a separate smokecheck sample and leave the root gallery unchanged")
    parser.add_argument("--no-gallery", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 24:
        parser.error("--workers must be between 1 and 24")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.self_test:
        _selftest()
        return
    try:
        # Validate every selected collection before starting the first download.
        for collection in dict.fromkeys(args.collections):
            _, coverage = load_asset_sources(Path(args.root) / collection / "source", collection)
            if not coverage["complete"] and not args.allow_partial:
                raise ValueError(f"{collection}: capture incomplete; missing={coverage['missing_required_labels']}; excluded={coverage['excluded_incomplete_labels']}")
        for collection in dict.fromkeys(args.collections):
            _, summary = rebuild_extra(args.root, collection, workers=args.workers, skip_download=args.skip_download,
                                       allow_partial=args.allow_partial, limit=args.limit)
            print(json.dumps({"collection": collection, **summary["stats"]}, ensure_ascii=False), flush=True)
        if not args.no_gallery and not args.limit:
            print(f"[gallery] {rebuild_root_gallery(args.root)}", flush=True)
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"[assets] ERROR: {exc}\n")


if __name__ == "__main__":
    main()
