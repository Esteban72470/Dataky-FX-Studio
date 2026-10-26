"""Build the local ZonitoVisuals texture database from captured tag inventories.

Source captures are never modified. By default, All and every required category
must be complete before exports/downloads begin. --limit writes a separate
smokecheck folder, so a sample cannot replace a complete catalogue.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing, redirect_stdout
import csv
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time


TAGS = ("Circle", "Crescent", "Effect", "Fire", "Flare", "GUI", "Grid", "Ground",
        "Impact", "Lightning", "Smoke", "Spec", "Star", "Swirl", "Text", "Water",
        "Wind", "Slash", "Other")
REQUIRED = ("All",) + TAGS
SPECIAL_COLLECTIONS = {"all", "personal", "recentlyused", "static", "statics", "flipbook", "flipbooks"}
IMAGE_FIELDS = ("image_path", "preview_path", "image_status", "image_error", "image_source",
                "width", "height", "preview_error")
CSV_FIELDS = ("key", "asset_id", "name", "uri", "tags", "kind", "grid", "grid_source",
              "id_status", "image_path", "preview_path", "image_status", "image_error",
              "width", "height", "creator", "raw_uris", "normalization_warnings", "aliases", "collections",
              "kind_source", "observed_rect_kinds", "type_collection_ambiguous",
              "grid_columns", "grid_rows", "name_source")


def _label_token(label):
    return re.sub(r"[^a-z0-9]", "", str(label).casefold())


def _is_category(label):
    return _label_token(label) not in SPECIAL_COLLECTIONS


def _tag_names(labels=(), rows=()):
    names = set(TAGS)
    names.update(str(label) for label in labels if _is_category(label))
    names.update(tag for row in rows for tag in row.get("tags", []))
    return list(TAGS) + sorted(names.difference(TAGS), key=lambda value: (value.casefold(), value))


def _tag_filename(tag):
    if tag in TAGS:
        return tag
    # Custom tag labels may contain characters invalid in Windows filenames or
    # differ only by case. A short label hash makes each export path unambiguous.
    stem = "".join(character if character.isalnum() or character in "-_ " else "_" for character in tag).strip(" .")[:70]
    suffix = hashlib.sha256(tag.encode("utf-8")).hexdigest()[:8]
    return f"{stem or 'tag'}-{suffix}"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_uri(value):
    """Extract the final numeric ID; retain broken/deleted placeholders honestly."""
    raw = str(value or "").strip()
    tokens = re.findall(r"[0-9]+", raw)
    asset_id = tokens[-1] if tokens else ""
    warnings = []
    if not asset_id:
        return {"asset_id": "", "uri": raw, "id_status": "invalid_missing_id", "normalization_warnings": ["no_numeric_id"]}
    if asset_id == "0" or not asset_id.strip("0"):
        status = "invalid_or_deleted_placeholder"
    elif asset_id.startswith("0"):
        # Values such as 01 are placeholders in the captured library. Do not
        # silently turn them into asset 1, download an unrelated image, or drop.
        status = "invalid_leading_zero_placeholder"
    else:
        status = "valid"
    uri = "rbxassetid://" + asset_id
    if raw != uri:
        warnings.append("normalized_uri")
    if raw.count("rbxassetid://") > 1:
        warnings.append("repeated_uri_prefix")
    if len(tokens) > 1:
        warnings.append("multiple_numeric_tokens_used_last")
    return {"asset_id": asset_id, "uri": uri, "id_status": status, "normalization_warnings": warnings}


def _pair(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return (0, 0)
    try:
        return (float(value[0]), float(value[1]))
    except (ValueError, TypeError):
        return (0, 0)


def _grid_from_name(name):
    match = re.search(r"(?<![0-9])([248])\s*[xX×]\s*\1(?![0-9])", name)
    return int(match.group(1)) if match else 0


def _classification(name, observations, collections=()):
    sizes = [_pair(row.get("rect_size")) for row in observations]
    kinds = {"flipbook" if x > 0 or y > 0 else "static" for x, y in sizes}
    rect_kind = "flipbook" if "flipbook" in kinds else "static"
    kind = rect_kind
    memberships = {_label_token(label) for label in collections}
    has_static = bool(memberships.intersection({"static", "statics"}))
    has_flipbook = bool(memberships.intersection({"flipbook", "flipbooks"}))
    ambiguous = has_static and has_flipbook
    kind_source = "observed_rect"
    if ambiguous:
        kind_source = "ambiguous_type_collections_rect_fallback"
    elif has_static:
        kind, kind_source = "static", "type_collection"
    elif has_flipbook:
        kind, kind_source = "flipbook", "type_collection"
    evidence = {"kind_source": kind_source, "observed_rect_kinds": sorted(kinds),
                "type_collection_ambiguous": ambiguous,
                "kind_source_labels": sorted(label for label in collections if _label_token(label) in {"static", "statics", "flipbook", "flipbooks"})}
    inferred = set()
    for x, y in sizes:
        if x > 0 and y > 0 and x == y:
            candidate = 1024 / x
            if candidate in (2, 4, 8):
                inferred.add(int(candidate))
    explicit = _grid_from_name(name)
    conflicts = []
    if len(kinds) > 1:
        conflicts.append("static_and_flipbook_rect_observations")
    if ambiguous:
        conflicts.append("both_static_and_flipbook_type_collections")
    elif kind_source == "type_collection" and kind != rect_kind:
        conflicts.append("rect_kind_differs_from_type_collection")
    if len(inferred) > 1:
        conflicts.append("inconsistent_grid_rect_observations")
    if explicit and inferred and inferred != {explicit}:
        conflicts.append("name_grid_differs_from_1024_rect_inference")
    if kind == "static":
        return {"kind": kind, "grid": 0, "grid_source": "static_type_collection" if has_static and not ambiguous else "static_rect", "classification_conflicts": conflicts, **evidence}
    if explicit:
        grid, source = explicit, "name"
    elif len(inferred) == 1:
        grid, source = next(iter(inferred)), "inferred_from_1024_sheet"
    else:
        grid, source = 0, "unknown"
    return {"kind": kind, "grid": grid, "grid_source": source, "classification_conflicts": conflicts, **evidence}


def _capture_coverage(data, path):
    records = data.get("records", [])
    issues = []
    if not isinstance(records, list):
        records = []
        issues.append("records_not_list")
    indexes = []
    invalid_indexes = 0
    fingerprint_by_index = defaultdict(set)
    for row in records:
        if not isinstance(row, dict):
            invalid_indexes += 1
            continue
        index = row.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 3:
            invalid_indexes += 1
            continue
        indexes.append(index)
        fingerprint_by_index[index].add(json.dumps({k: row.get(k) for k in ("name", "raw_uri", "image", "rect_size")}, sort_keys=True))
    maximum = data.get("max_index")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 2:
        maximum = max(indexes, default=2)
        issues.append("invalid_or_missing_max_index")
    # A malformed source cannot induce an unbounded range allocation.
    if maximum > 1_000_000:
        missing = []
        issues.append("max_index_exceeds_safety_bound")
    else:
        missing = sorted(set(range(3, maximum + 1)).difference(indexes))
    if missing:
        issues.append("computed_missing_indexes")
    declared = data.get("missing_indexes")
    if not isinstance(declared, list):
        issues.append("missing_indexes_not_recorded")
    elif declared:
        issues.append("capture_reported_missing_indexes")
    if invalid_indexes:
        issues.append("invalid_indexes")
    outside = sorted(index for index in set(indexes) if index > maximum)
    if outside:
        issues.append("indexes_exceed_max_index")
    conflicting = sorted(index for index, values in fingerprint_by_index.items() if len(values) > 1)
    if conflicting:
        issues.append("conflicting_records_at_same_index")
    if str(data.get("search") or "").strip():
        issues.append("search_filter_was_active")
    label = str(data.get("label") or path.stem)
    # Capture labels alone cannot prove the plugin was actually displaying that
    # category. Reject combined/incorrect filters even when indexes are gapless.
    active_filter = data.get("active_filter")
    normalized_filter = None
    if not isinstance(active_filter, str):
        issues.append("active_filter_not_recorded")
    else:
        normalized_filter = " ".join(html.unescape(re.sub(r"<[^>]*>", "", active_filter)).split()).casefold()
        expected_label = label.replace("_", " ") if _label_token(label) == "recentlyused" else label
        is_type_capture = _label_token(label) in {"static", "statics", "flipbook", "flipbooks"}
        expected_filter = "tags" if label.casefold() == "all" or is_type_capture else " ".join(expected_label.split()).casefold()
        if normalized_filter != expected_filter:
            issues.append("active_filter_does_not_match_single_category")
    active_type = data.get("active_type")
    if active_type is not None:
        type_value = _label_token(html.unescape(re.sub(r"<[^>]*>", "", str(active_type))))
        label_type = _label_token(label)
        expected_types = {"static", "statics"} if label_type in {"static", "statics"} else {"flipbook", "flipbooks"} if label_type in {"flipbook", "flipbooks"} else {"all"}
        if type_value not in expected_types:
            issues.append("active_type_does_not_match_capture")
    return {"label": label, "file": path.name, "complete": not issues, "issues": issues,
            "raw_records": len(records), "unique_indexes": len(set(indexes)),
            "max_index": maximum, "computed_missing_indexes": missing,
            "reported_missing_indexes": declared, "invalid_index_count": invalid_indexes,
            "duplicate_index_observations": len(indexes) - len(set(indexes)),
            "conflicting_indexes": conflicting, "indexes_above_maximum": outside,
            "captured_at": data.get("captured_at"), "search": data.get("search"),
            "active_filter": active_filter, "normalized_active_filter": normalized_filter,
            "active_type": active_type,
            "canvas_height": data.get("canvas_height"), "window_height": data.get("window_height")}


def load_sources(source_dir):
    """Return complete captures and independent coverage for every source file.

    Incomplete optional type captures must never influence classification. All
    incomplete captures are excluded here, before joins/type inference, even
    when the caller explicitly chooses a partial catalogue.
    """
    sources, coverage = {}, {}
    for path in sorted(Path(source_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read source {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Source {path.name} is not an object")
        info = _capture_coverage(data, path)
        label = info["label"]
        if label in sources:
            raise ValueError(f"Duplicate source label: {label}")
        sources[label] = data
        coverage[label] = info
    missing = [label for label in REQUIRED if label not in sources]
    incomplete = [label for label, info in coverage.items() if not info["complete"]]
    required_incomplete = [label for label in REQUIRED if label in incomplete]
    report = {"complete": not missing and not incomplete,
              "required_labels": list(REQUIRED), "missing_required_labels": missing,
              "incomplete_required_labels": required_incomplete,
              "incomplete_optional_labels": [label for label in incomplete if label not in REQUIRED],
              "excluded_incomplete_labels": incomplete,
              "sources": coverage}
    complete_sources = {label: data for label, data in sources.items() if coverage[label]["complete"]}
    return complete_sources, report


def normalize_records(sources):
    """Join exact ID+name identities; a filter-local index is only evidence."""
    merged = {}
    raw_count = 0
    category_order = {label: index for index, label in enumerate(_tag_names(sources))}
    for label, data in sources.items():
        for raw in data.get("records", []):
            if not isinstance(raw, dict):
                continue
            raw_count += 1
            name = str(raw.get("name") or "")
            raw_uri = str(raw.get("raw_uri") or raw.get("image") or "")
            normalized = normalize_uri(raw_uri)
            identity = (normalized["asset_id"] or normalized["uri"], name)
            row = merged.get(identity)
            if row is None:
                stable = json.dumps([normalized["uri"], name], ensure_ascii=False, separators=(",", ":"))
                row = {"key": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24],
                       "name": name, **normalized, "raw_uri": raw_uri, "raw_uris": [],
                       "aliases": [], "tags": [], "collections": [], "source_labels": [], "observations": [],
                       "image_path": None, "preview_path": None, "image_status": "not_requested",
                       "image_error": None}
                merged[identity] = row
            if raw_uri not in row["raw_uris"]:
                row["raw_uris"].append(raw_uri)
            for warning in normalized["normalization_warnings"]:
                if warning not in row["normalization_warnings"]:
                    row["normalization_warnings"].append(warning)
            if label not in row["source_labels"]:
                row["source_labels"].append(label)
            if _is_category(label) and label not in row["tags"]:
                row["tags"].append(label)
            elif _label_token(label) != "all" and not _is_category(label) and label not in row["collections"]:
                row["collections"].append(label)
            row["observations"].append({"source": label, "index": raw.get("index"),
                                        "raw_uri": raw_uri, "image": raw.get("image"),
                                        "rect_size": raw.get("rect_size"),
                                        "rect_offset": raw.get("rect_offset")})
    names_by_id = defaultdict(set)
    for row in merged.values():
        if row["asset_id"]:
            names_by_id[row["asset_id"]].add(row["name"])
    rows = []
    for row in merged.values():
        row.update(_classification(row["name"], row["observations"], row["collections"]))
        row["aliases"] = sorted(names_by_id[row["asset_id"]] - {row["name"]}) if row["asset_id"] else []
        row["tags"] = sorted(row["tags"], key=category_order.__getitem__)
        row["collections"] = sorted(row["collections"], key=str.casefold)
        row["source_labels"] = sorted(row["source_labels"])
        row["in_all_inventory"] = "All" in row["source_labels"]
        row["observation_count"] = len(row["observations"])
        rows.append(row)
    rows.sort(key=lambda row: (row["name"].casefold(), row["asset_id"], row["key"]))
    return rows, raw_count


def _reuse_images(rows, output_dir):
    prior = output_dir / "textures.json"
    if not prior.is_file():
        return
    try:
        old = json.loads(prior.read_text(encoding="utf-8"))
        by_key = {row["key"]: row for row in old if isinstance(row, dict) and "key" in row}
    except (OSError, ValueError, TypeError):
        return
    for row in rows:
        previous = by_key.get(row["key"], {})
        for key in IMAGE_FIELDS:
            if key in previous:
                row[key] = previous[key]
        path = row.get("image_path")
        if path and not (output_dir / path).is_file():
            row.update(image_path=None, preview_path=None, image_status="not_requested", image_error=None)


def make_summary(rows, raw_count, coverage, started, *, limited=False, phase="indexed"):
    assets = {row["asset_id"] for row in rows if row["asset_id"]}
    valid_assets = {row["asset_id"] for row in rows if row["id_status"] == "valid"}
    image_assets = {row["asset_id"] for row in rows if row.get("image_path")}
    all_rows = [row for row in rows if row["in_all_inventory"]]
    tag_names = _tag_names(coverage.get("sources", {}), rows)
    return {"generated_at": utc_now(), "phase": phase,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "limited_smokecheck": limited, "capture_coverage": coverage, "tag_names": tag_names,
            "stats": {"source_observations": raw_count, "texture_identities": len(rows),
                      "all_inventory_identities": len(all_rows), "unique_asset_ids": len(assets),
                      "valid_unique_asset_ids": len(valid_assets),
                      "extra_observations_collapsed": raw_count - len(rows),
                      "duplicate_rows_note": "One row per valid canonical Roblox ID; names and source keys are aliases, invalid placeholders stay separate." if coverage.get("plugin_merge") else "An identity is canonical ID + exact name. Tag observations and repeated rows collapse into one identity.",
                      "invalid_or_deleted_identities": sum(row["id_status"] != "valid" for row in rows),
                      "normalized_uri_identities": sum(bool(row["normalization_warnings"]) for row in rows),
                      "classification_conflict_identities": sum(bool(row["classification_conflicts"]) for row in rows),
                      "kind_from_type_collection_identities": sum(row["kind_source"] == "type_collection" for row in rows),
                      "ambiguous_type_collection_identities": sum(row["type_collection_ambiguous"] for row in rows),
                      "tag_identities_absent_from_all": sum(not row["in_all_inventory"] for row in rows),
                      "static_identities": sum(row["kind"] == "static" for row in rows),
                      "flipbook_identities": sum(row["kind"] == "flipbook" for row in rows),
                      "unknown_flipbook_grid_identities": sum(row["kind"] == "flipbook" and not row["grid"] for row in rows),
                      "unique_asset_ids_with_image": len(image_assets),
                      "identities_with_image": sum(bool(row.get("image_path")) for row in rows),
                      "image_status_counts": dict(sorted(Counter(row["image_status"] for row in rows).items())),
                      "per_tag": {tag: sum(tag in row["tags"] for row in rows) for tag in tag_names}},
            "notes": ["Images are public Roblox-generated thumbnail previews, not original texture downloads.",
                      "Tags come from exact membership in each captured category, not name guesses.",
                      "Static/flipbook kind uses type-collection membership when available; raw rectangle observations remain in the evidence.",
                      "Some flipbook grids are inferred from a 1024-pixel sheet; grid_source records this assumption.",
                      "Asset IDs are stored as strings in JSON and SQLite."]}


def _atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_json(path, value):
    _atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _excel_safe(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    # CSV quoting does not neutralize spreadsheet formulas. A leading apostrophe
    # makes attacker-controlled names/URIs literal text when opened in Excel.
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        text = "'" + text
    return text


def _write_csv(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_FIELDS)
    for row in rows:
        writer.writerow([_excel_safe(row.get(field)) for field in CSV_FIELDS])
    _atomic_bytes(path, buffer.getvalue().encode("utf-8-sig"))


def _write_sqlite(path, rows, summary):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".textures-", suffix=".sqlite", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE textures (
                    key TEXT PRIMARY KEY, asset_id TEXT NOT NULL, name TEXT NOT NULL,
                    uri TEXT NOT NULL, raw_uri TEXT NOT NULL, id_status TEXT NOT NULL,
                    kind TEXT NOT NULL, grid INTEGER NOT NULL, grid_source TEXT NOT NULL,
                    image_path TEXT, preview_path TEXT, image_status TEXT NOT NULL,
                    image_error TEXT, width INTEGER, height INTEGER, creator TEXT,
                    aliases_json TEXT NOT NULL, raw_uris_json TEXT NOT NULL,
                    observations_json TEXT NOT NULL, normalization_warnings_json TEXT NOT NULL,
                    classification_conflicts_json TEXT NOT NULL, in_all_inventory INTEGER NOT NULL,
                    collections_json TEXT NOT NULL, kind_source TEXT NOT NULL,
                    observed_rect_kinds_json TEXT NOT NULL, type_collection_ambiguous INTEGER NOT NULL,
                    kind_source_labels_json TEXT NOT NULL);
                CREATE TABLE tags (name TEXT PRIMARY KEY);
                CREATE TABLE texture_tags (texture_key TEXT NOT NULL REFERENCES textures(key),
                    tag TEXT NOT NULL REFERENCES tags(name), PRIMARY KEY(texture_key, tag));
                CREATE INDEX textures_asset_id ON textures(asset_id);
                CREATE INDEX textures_name ON textures(name COLLATE NOCASE);
                CREATE INDEX textures_kind ON textures(kind);
                CREATE INDEX texture_tags_tag ON texture_tags(tag);
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            """)
            db.executemany("INSERT INTO tags(name) VALUES (?)", [(tag,) for tag in summary["tag_names"]])
            for row in rows:
                db.execute("INSERT INTO textures VALUES (" + ",".join("?" for _ in range(27)) + ")", (
                    row["key"], row["asset_id"], row["name"], row["uri"], row["raw_uri"], row["id_status"],
                    row["kind"], row["grid"], row["grid_source"], row.get("image_path"), row.get("preview_path"),
                    row["image_status"], row.get("image_error"), row.get("width"), row.get("height"), row.get("creator"),
                    json.dumps(row["aliases"], ensure_ascii=False), json.dumps(row["raw_uris"], ensure_ascii=False),
                    json.dumps(row["observations"], ensure_ascii=False), json.dumps(row["normalization_warnings"]),
                    json.dumps(row["classification_conflicts"]), int(row["in_all_inventory"]),
                    json.dumps(row.get("collections", []), ensure_ascii=False), row["kind_source"],
                    json.dumps(row["observed_rect_kinds"]), int(row["type_collection_ambiguous"]),
                    json.dumps(row["kind_source_labels"], ensure_ascii=False)))
                db.executemany("INSERT INTO texture_tags VALUES (?,?)", [(row["key"], tag) for tag in row["tags"]])
            db.execute("ALTER TABLE textures ADD COLUMN grid_columns INTEGER")
            db.execute("ALTER TABLE textures ADD COLUMN grid_rows INTEGER")
            db.execute("ALTER TABLE textures ADD COLUMN name_source TEXT")
            db.executemany("UPDATE textures SET grid_columns=?,grid_rows=?,name_source=? WHERE key=?", [
                (row.get("grid_columns", row.get("grid") or None), row.get("grid_rows", row.get("grid") or None), row.get("name_source"), row["key"]) for row in rows])
            db.execute("INSERT INTO metadata VALUES (?,?)", ("summary", json.dumps(summary, ensure_ascii=False)))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity check failed")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_catalogue(rows, summary, output_dir):
    from catalog_annotations import apply_annotations
    rows[:] = apply_annotations(rows, output_dir)
    if "stats" in summary:
        summary["stats"]["unknown_flipbook_grid_identities"] = sum(r["kind"] == "flipbook" and not (r.get("grid") or r.get("grid_columns")) for r in rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "textures.json", rows)
    _write_csv(output_dir / "textures.csv", rows)
    _write_sqlite(output_dir / "textures.sqlite", rows, summary)
    tag_files = {}
    for tag in summary["tag_names"]:
        tagged = [row for row in rows if tag in row["tags"]]
        basename = _tag_filename(tag)
        _write_json(output_dir / "tags" / f"{basename}.json", tagged)
        _write_csv(output_dir / "tags" / f"{basename}.csv", tagged)
        tag_files[tag] = {"json": f"tags/{basename}.json", "csv": f"tags/{basename}.csv", "count": len(tagged)}
    _write_json(output_dir / "tags" / "index.json", tag_files)
    failures = [{"key": row["key"], "asset_id": row["asset_id"], "name": row["name"],
                 "tags": row["tags"], "id_status": row["id_status"],
                 "image_status": row["image_status"], "image_error": row.get("image_error")}
                for row in rows if row["id_status"] != "valid" or row["image_status"] not in {"not_requested", "downloaded", "cached"}]
    _write_json(output_dir / "failures.json", failures)
    _write_json(output_dir / "summary.json", summary)
    # gallery.py writes one HTML file. Generate it in a temporary sibling folder
    # and rename it atomically without changing its relative image references.
    from gallery import build_gallery
    from asset_catalog import load_extra_collections
    with tempfile.TemporaryDirectory(prefix=".gallery-", dir=output_dir) as temporary:
        generated = build_gallery(rows, Path(temporary), summary, extra_collections=load_extra_collections(output_dir))
        os.replace(generated, output_dir / "catalogue.html")
    if any("VFX Studio" in row.get("plugins", []) for row in rows):
        from import_vfx_studio import enrich_export_files
        import asset_catalog
        enrich_export_files(rows, summary, output_dir, "textures", sys.modules[__name__], asset_catalog)


def run(args):
    started = time.monotonic()
    root = Path(args.root).resolve()
    sources, coverage = load_sources(root / "source")
    if not coverage["complete"] and not args.allow_partial:
        missing = ", ".join(coverage["missing_required_labels"]) or "none"
        incomplete = ", ".join(coverage["incomplete_required_labels"] + coverage["incomplete_optional_labels"]) or "none"
        raise ValueError(f"Capture incomplete. Missing: {missing}. Incomplete: {incomplete}. Use --allow-partial only for an explicitly partial catalogue.")
    if args.allow_partial and coverage["excluded_incomplete_labels"]:
        print("[catalogue] Excluded incomplete captures: " + ", ".join(coverage["excluded_incomplete_labels"]), flush=True)
    rows, raw_count = normalize_records(sources)
    from import_vfx_studio import merge_saved_plugin
    rows, plugin_merge = merge_saved_plugin(root, rows, "textures", sys.modules[__name__])
    if plugin_merge:
        coverage["plugin_merge"] = plugin_merge
        raw_count = sum(len(row.get("observations", [])) for row in rows)
    if not rows:
        raise ValueError("No captured texture records were found")
    output_dir = root / "smokecheck" if args.limit else root
    from catalog_annotations import apply_annotations
    rows = apply_annotations(rows, root)
    _reuse_images(rows, output_dir)
    if args.limit:
        rows = rows[:args.limit]
        # Count only retained observations in sample statistics.
        raw_count = sum(len(row["observations"]) for row in rows)
    summary = make_summary(rows, raw_count, coverage, started, limited=bool(args.limit))
    export_catalogue(rows, summary, output_dir)
    print(f"[catalogue] IDs saved: {len(rows)} identities, {len(sources)} captures. Coverage complete: {coverage['complete']}", flush=True)
    if not args.skip_download:
        from download import download_previews
        rows = download_previews(rows, output_dir, workers=args.workers)
        summary = make_summary(rows, raw_count, coverage, started, limited=bool(args.limit), phase="downloaded")
        export_catalogue(rows, summary, output_dir)
    print(f"[catalogue] {output_dir / 'catalogue.html'}", flush=True)
    print(json.dumps(summary["stats"], ensure_ascii=False), flush=True)
    return rows, summary


def _selftest():
    def capture(label, records):
        return {"label": label, "records": records, "max_index": max((r["index"] for r in records), default=2),
                "missing_indexes": [], "canvas_height": 100, "window_height": 100, "search": "", "captured_at": "2026-10-21T00:00:00Z",
                "active_filter": "Tags" if label == "All" else label}
    def record(index, name, uri, size=None):
        return {"index": index, "name": name, "raw_uri": uri, "image": uri,
                "rect_size": size or [0, 0], "rect_offset": [0, 0]}
    all_records = [record(3, "A", "rbxassetid://123"), record(4, "A", "rbxassetid://rbxassetid://123"),
                   record(5, "Alternate name", "rbxassetid://123"), record(6, "Deleted", "rbxassetid://0"),
                   record(7, "Placeholder", "rbxassetid://01"), record(8, "Burst8x8", "rbxassetid://456", [256, 256])]
    with tempfile.TemporaryDirectory(prefix="zonito-catalogue-test-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        for tag in TAGS:
            _write_json(source / f"{tag}.json", capture(tag, []))
        _write_json(source / "All.json", capture("All", all_records))
        _write_json(source / "Circle.json", capture("Circle", [record(3, "A", "rbxassetid://123")]))
        _write_json(source / "Effect.json", capture("Effect", [record(3, "Burst8x8", "rbxassetid://456", [256, 256])]))
        _write_json(source / "Custom.json", capture("Magic / aura", [record(3, "A", "rbxassetid://123")]))
        _write_json(source / "EmptyCustom.json", capture("Empty custom tag", []))
        _write_json(source / "Personal.json", capture("Personal", [record(3, "A", "rbxassetid://123")]))
        sources, coverage = load_sources(source)
        assert coverage["complete"], coverage
        rows, count = normalize_records(sources)
        assert len(rows) == 5 and count == 10, (rows, count)
        by_name = {row["name"]: row for row in rows}
        assert by_name["A"]["tags"] == ["Circle", "Magic / aura"]
        assert by_name["A"]["collections"] == ["Personal"]
        assert by_name["A"]["observation_count"] == 5
        assert "repeated_uri_prefix" in by_name["A"]["normalization_warnings"]
        assert by_name["A"]["aliases"] == ["Alternate name"]
        assert by_name["Deleted"]["asset_id"] == "0" and by_name["Deleted"]["id_status"] != "valid"
        assert by_name["Placeholder"]["asset_id"] == "01" and by_name["Placeholder"]["id_status"] != "valid"
        assert by_name["Burst8x8"]["kind"] == "flipbook" and by_name["Burst8x8"]["grid"] == 8
        assert by_name["Burst8x8"]["grid_source"] == "name" and by_name["Burst8x8"]["classification_conflicts"]
        assert _classification("Untitled", [{"rect_size": [128, 128]}])["grid_source"] == "inferred_from_1024_sheet"
        static_override = _classification("Untitled", [{"rect_size": [128, 128]}], ["Statics"])
        assert static_override["kind"] == "static" and static_override["grid"] == 0 and static_override["kind_source"] == "type_collection"
        flip_override = _classification("Burst4x4", [{"rect_size": [0, 0]}], ["Flipbooks"])
        assert flip_override["kind"] == "flipbook" and flip_override["grid"] == 4 and flip_override["observed_rect_kinds"] == ["static"]
        ambiguous_type = _classification("Untitled", [{"rect_size": [128, 128]}], ["Statics", "Flipbooks"])
        assert ambiguous_type["type_collection_ambiguous"] and "both_static_and_flipbook_type_collections" in ambiguous_type["classification_conflicts"]
        assert _excel_safe("  =HYPERLINK(\"bad\")").startswith("'")
        summary = make_summary(rows, count, coverage, time.monotonic())
        export_catalogue(rows, summary, root)
        with closing(sqlite3.connect(root / "textures.sqlite")) as db:
            assert db.execute("SELECT COUNT(*) FROM textures").fetchone()[0] == 5
            assert db.execute("SELECT COUNT(*) FROM texture_tags WHERE tag='Circle'").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM texture_tags WHERE tag='Magic / aura'").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM tags WHERE name='Empty custom tag'").fetchone()[0] == 1
            assert db.execute("SELECT asset_id FROM textures WHERE name='Placeholder'").fetchone()[0] == "01"
        assert (root / "textures.csv").read_bytes().startswith(b"\xef\xbb\xbf")
        tag_index = json.loads((root / "tags" / "index.json").read_text(encoding="utf-8"))
        assert tag_index["Magic / aura"]["count"] == 1
        assert (root / tag_index["Magic / aura"]["json"]).is_file()
        assert len(json.loads((root / "failures.json").read_text(encoding="utf-8"))) == 2
        # An optional but incomplete type capture must not override a flipbook
        # identity, even when --allow-partial is explicitly requested.
        incomplete_statics = capture("Statics", [record(3, "Burst8x8", "rbxassetid://456"), record(5, "Burst8x8", "rbxassetid://456")])
        incomplete_statics.update(active_filter="Tags", active_type="Static")
        _write_json(source / "Statics.json", incomplete_statics)
        clean_sources, optional_incomplete = load_sources(source)
        assert not optional_incomplete["complete"]
        assert optional_incomplete["incomplete_optional_labels"] == ["Statics"]
        assert optional_incomplete["excluded_incomplete_labels"] == ["Statics"]
        assert "Statics" not in clean_sources
        clean_rows, _ = normalize_records(clean_sources)
        clean_burst = next(row for row in clean_rows if row["name"] == "Burst8x8")
        assert clean_burst["kind"] == "flipbook" and "Statics" not in clean_burst["source_labels"]
        cli_arguments = argparse.Namespace(root=str(root), workers=1, skip_download=True, allow_partial=False, limit=None)
        try:
            run(cli_arguments)
            raise AssertionError("Default CLI accepted incomplete optional capture")
        except ValueError as exc:
            assert "Statics" in str(exc)
        cli_arguments.allow_partial = True
        with redirect_stdout(io.StringIO()) as partial_output:
            partial_rows, partial_summary = run(cli_arguments)
        assert "Excluded incomplete captures: Statics" in partial_output.getvalue()
        assert not partial_summary["capture_coverage"]["complete"]
        partial_burst = next(row for row in partial_rows if row["name"] == "Burst8x8")
        assert partial_burst["kind"] == "flipbook" and "Statics" not in partial_burst["collections"]
        (source / "Statics.json").unlink()
        broken = capture("All", [all_records[0], all_records[2]])
        _write_json(source / "All.json", broken)
        _, incomplete = load_sources(source)
        assert not incomplete["complete"] and incomplete["sources"]["All"]["computed_missing_indexes"] == [4]
        (source / "Other.json").unlink()
        _, missing = load_sources(source)
        assert "Other" in missing["missing_required_labels"]
        combined = capture("Circle", [record(3, "A", "rbxassetid://123")])
        combined["active_filter"] = "<b>circle</b>, crescent"
        assert "active_filter_does_not_match_single_category" in _capture_coverage(combined, source / "Circle.json")["issues"]
        combined["active_filter"] = "  <b>CiRcLe</b>  "
        assert _capture_coverage(combined, source / "Circle.json")["complete"]
        combined.pop("active_filter")
        assert "active_filter_not_recorded" in _capture_coverage(combined, source / "Circle.json")["issues"]
        type_capture = capture("Statics", [])
        type_capture.update(active_filter="Tags", active_type="Static")
        assert _capture_coverage(type_capture, source / "Statics.json")["complete"]
        type_capture["active_type"] = "Flipbook"
        assert "active_type_does_not_match_capture" in _capture_coverage(type_capture, source / "Statics.json")["issues"]
    print("[self-test] PASS: ID normalization, placeholder preservation, deduplication, exact tag joins, aliases, grid conflicts, capture/filter coverage, CSV safety and SQLite relations")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Catalogue directory containing source/")
    parser.add_argument("--workers", type=int, default=12, help="Parallel image workers (1-24)")
    parser.add_argument("--skip-download", action="store_true", help="Only export captured IDs/tags; preserve existing image metadata")
    parser.add_argument("--allow-partial", action="store_true", help="Allow missing captures; exclude incomplete captures and report coverage gaps")
    parser.add_argument("--limit", type=int, help="Smokecheck only: output at most N identities to a separate smokecheck/ folder")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if not 1 <= args.workers <= 24:
        parser.error("--workers must be between 1 and 24")
    if args.self_test:
        _selftest()
        return
    try:
        run(args)
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"[catalogue] ERROR: {exc}\n")


if __name__ == "__main__":
    main()
