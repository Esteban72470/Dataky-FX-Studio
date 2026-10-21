"""Independently verify the offline Beams/Meshes exports without rewriting files.

No exporter, downloader, macro or gallery module is imported. Source inventory
membership and asset references are reconstructed before checking all exports.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys
from urllib.parse import parse_qs, urlsplit
import zlib


class VerificationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def token(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def plain(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).split()).casefold()


def category(label):
    return token(label) not in {"all", "personal", "recentlyused"}


def parse_reference(raw):
    """Prefer explicit URL ID parameters over image thumbnail dimensions."""
    raw = str(raw or "").strip()
    if raw.lower().startswith("rbxasset://"):
        return "", raw, "builtin_uri"
    parsed = urlsplit(raw)
    query_text = parsed.query
    if not query_text and parsed.scheme.casefold() == "rbxthumb":
        query_text = parsed.netloc + parsed.path
    elif not query_text and "://" not in raw:
        query_text = raw
    query = {}
    for name, values in parse_qs(query_text).items():
        query.setdefault(name.casefold(), values)
    candidate = ""
    for key in ("id", "assetid"):
        values = query.get(key, [])
        if values and re.fullmatch(r"[0-9]+", values[0]):
            candidate = values[0]
            break
    if not candidate:
        explicit = re.findall(r"rbxassetid://([0-9]+)", raw, re.IGNORECASE)
        numeric = re.findall(r"[0-9]+", raw)
        candidate = explicit[-1] if explicit else numeric[-1] if numeric else ""
    if not candidate:
        return "", raw, "invalid_missing_id"
    status = "valid" if re.fullmatch(r"[1-9][0-9]*", candidate) else "invalid_or_deleted_placeholder" if not candidate.strip("0") else "invalid_leading_zero_placeholder"
    return candidate, "rbxassetid://" + candidate, status


def raw_asset(record, collection):
    primary_raw = record.get("mesh_uri") if collection == "meshes" else record.get("raw_uri")
    primary_raw = primary_raw or record.get("raw_uri") or record.get("texture_uri") or ""
    primary = parse_reference(primary_raw)
    candidates = []
    for reference in record.get("references") or []:
        if isinstance(reference, dict):
            candidates.append((str(reference.get("label") or "AssetId"), reference.get("raw_uri") or reference.get("uri") or ""))
    if record.get("mesh_uri"):
        candidates.append(("MeshId", record["mesh_uri"]))
    if record.get("texture_uri"):
        candidates.append(("TextureId", record["texture_uri"]))
    if primary_raw:
        candidates.append(("MeshId" if collection == "meshes" else "TextureId", primary_raw))
    references = {}
    for label, raw in candidates:
        asset_id, uri, status = parse_reference(raw)
        key = label, uri
        entry = references.setdefault(key, {"asset_id": asset_id, "id_status": status, "raw_uris": set()})
        entry["raw_uris"].add(str(raw or "").strip())
    identity = primary[0] or primary[1], str(record.get("name") or "")
    return identity, primary, references


def local_file(directory, relative):
    require(isinstance(relative, str) and relative, "Empty or non-string local path")
    value = relative.replace("\\", "/")
    path = Path(value)
    require(not path.is_absolute() and ":" not in value and ".." not in path.parts, f"Unsafe local path: {relative}")
    resolved = (directory / path).resolve()
    require(resolved.is_relative_to(directory.resolve()), f"Local path escapes its collection: {relative}")
    require(resolved.is_file(), f"Missing local file: {relative}")
    return resolved


def png_size(path, *, deep=False):
    require(path.stat().st_size <= 32 * 1024 * 1024, f"Oversized PNG: {path.name}")
    content = path.read_bytes()
    require(content[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG signature: {path.name}")
    position, size, ended = 8, None, False
    while position + 12 <= len(content):
        length = struct.unpack(">I", content[position:position + 4])[0]
        end = position + 12 + length
        require(end <= len(content), f"Truncated PNG chunk: {path.name}")
        kind = content[position + 4:position + 8]
        data = content[position + 8:position + 8 + length]
        checksum = struct.unpack(">I", content[position + 8 + length:end])[0]
        require(zlib.crc32(kind + data) & 0xFFFFFFFF == checksum, f"PNG CRC mismatch: {path.name}")
        if size is None:
            require(kind == b"IHDR" and length == 13, f"PNG lacks first IHDR: {path.name}")
            size = struct.unpack(">II", data[:8])
            require(all(0 < value <= 16384 for value in size), f"Invalid PNG dimensions: {path.name}")
        position = end
        if kind == b"IEND":
            require(length == 0, f"Invalid PNG end marker: {path.name}")
            ended = True
            break
    require(ended and position == len(content), f"PNG missing end marker or has trailing bytes: {path.name}")
    if deep:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
    return size


class CatalogueData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.collect = False
        self.count = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "catalogue-data":
            self.collect = True
            self.count += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self.collect = False

    def handle_data(self, data):
        if self.collect:
            self.parts.append(data)


def verify_collection(root, collection, payload, *, verify_png=False):
    directory = root / collection
    captures, membership, expected_refs = {}, defaultdict(set), defaultdict(dict)
    observations, primary_by_identity = Counter(), {}
    for path in sorted((directory / "source").glob("*.json")):
        data = read_json(path)
        label = data.get("label")
        require(isinstance(label, str) and label and label not in captures, f"{collection}: duplicate/empty source label")
        require(data.get("collection") == collection and plain(data.get("active_collection")) == collection,
                f"{collection}/{label}: wrong active collection")
        require(plain(data.get("active_filter")) == ("tags" if token(label) == "all" else plain(label)),
                f"{collection}/{label}: wrong selected category")
        require(not str(data.get("search") or "").strip(), f"{collection}/{label}: active search")
        records = data.get("records")
        require(isinstance(records, list), f"{collection}/{label}: invalid records")
        require(all(isinstance(record, dict) for record in records), f"{collection}/{label}: source record is not an object")
        first, maximum = data.get("first_index"), data.get("max_index")
        require(type(first) is int and first >= 0 and type(maximum) is int and first - 1 <= maximum <= first + 1_000_000,
                f"{collection}/{label}: invalid index bounds")
        indexes = [r.get("index") for r in records]
        require(all(type(index) is int for index in indexes) and set(indexes) == set(range(first, maximum + 1)),
                f"{collection}/{label}: missing or out-of-range source indexes")
        require(data.get("missing_indexes") == [], f"{collection}/{label}: missing indexes not cleared")
        fingerprints = defaultdict(set)
        for record in records:
            fingerprints[record["index"]].add(json.dumps({key: record.get(key) for key in ("name", "raw_uri", "mesh_uri", "texture_uri", "references")}, sort_keys=True))
            identity, primary, references = raw_asset(record, collection)
            membership[identity].add(label)
            observations[identity] += 1
            require(identity not in primary_by_identity or primary_by_identity[identity] == primary,
                    f"{collection}: inconsistent primary identity {identity}")
            primary_by_identity[identity] = primary
            for key, ref in references.items():
                merged = expected_refs[identity].setdefault(key, {**ref, "raw_uris": set()})
                require(merged["asset_id"] == ref["asset_id"] and merged["id_status"] == ref["id_status"],
                        f"{collection}: reference normalization conflict")
                merged["raw_uris"].update(ref["raw_uris"])
        require(all(len(values) == 1 for values in fingerprints.values()), f"{collection}/{label}: conflicting source slot")
        captures[label] = data
    all_labels = [label for label in captures if token(label) == "all"]
    require(len(all_labels) == 1, f"{collection}: complete All inventory absent")
    available = captures[all_labels[0]].get("available_tags")
    require(isinstance(available, list) and all(isinstance(tag, str) and tag for tag in available),
            f"{collection}: original available tag list absent")
    required_tags = {tag for tag in available if category(tag)}
    require(required_tags.issubset(captures), f"{collection}: missing category captures {sorted(required_tags.difference(captures))}")
    tag_names = {label for label in captures if category(label)}

    rows, summary = read_json(directory / "assets.json"), read_json(directory / "summary.json")
    require(isinstance(rows, list), f"{collection}: assets.json is not a list")
    require(summary.get("collection") == collection and not summary.get("limited_smokecheck"), f"{collection}: partial sample export")
    coverage = summary.get("capture_coverage", {})
    require(coverage.get("complete") is True and not coverage.get("missing_required_labels") and not coverage.get("excluded_incomplete_labels"),
            f"{collection}: export capture coverage is partial")
    require(set(coverage.get("sources", {})) == set(captures) and all(info.get("complete") is True and not info.get("issues") for info in coverage["sources"].values()),
            f"{collection}: incomplete/stale coverage metadata")
    require(set(summary.get("tag_names", [])) == tag_names, f"{collection}: wrong exported tag list")
    by_identity = {(r["asset_id"] or r["uri"], r["name"]): r for r in rows}
    require(len(by_identity) == len(rows) and set(by_identity) == set(membership), f"{collection}: lost or duplicate identities")
    by_key = {r["key"]: r for r in rows}
    require(len(by_key) == len(rows), f"{collection}: duplicate stable keys")
    images = {}
    for identity, row in by_identity.items():
        require(row.get("collection") == collection and row.get("kind") == ("beam" if collection == "beams" else "mesh"), f"{collection}: wrong asset kind")
        require(isinstance(row["asset_id"], str), f"{collection}: non-string ID")
        require((row["asset_id"], row["uri"], row["id_status"]) == primary_by_identity[identity], f"{collection}: wrong primary ID/URI {identity}")
        labels = membership[identity]
        require(set(row["source_labels"]) == labels and row["observation_count"] == observations[identity], f"{collection}: source evidence lost")
        require(set(row["tags"]) == {label for label in labels if category(label)}, f"{collection}: incorrect category join {identity}")
        require(set(row["collections"]) == {label for label in labels if not category(label) and token(label) != "all"}, f"{collection}: incorrect special collection join")
        require(bool(row["in_all_inventory"]) == any(token(label) == "all" for label in labels), f"{collection}: wrong All membership")
        references = {(ref["label"], ref["uri"]): ref for ref in row["references"]}
        require(len(references) == len(row["references"]) and set(references) == set(expected_refs[identity]), f"{collection}: lost or duplicate secondary references {identity}")
        for key, ref in references.items():
            expected = expected_refs[identity][key]
            require((ref["asset_id"], ref["id_status"]) == (expected["asset_id"], expected["id_status"]) and ref["raw_uri"] in expected["raw_uris"],
                    f"{collection}: incorrect reference value {key}")
        for field in ("image_path", "preview_path"):
            if row.get(field):
                path = local_file(directory, row[field])
                if path not in images:
                    images[path] = png_size(path, deep=verify_png)
                if field == "image_path":
                    require((row.get("width"), row.get("height")) == images[path], f"{collection}: image dimensions disagree with metadata")
        if row["image_status"] in {"cached", "downloaded"}:
            require(bool(row.get("image_path")), f"{collection}: successful preview has no file")

    stats = summary["stats"]
    expected_stats = {"asset_identities": len(rows), "source_observations": sum(observations.values()),
        "extra_observations_collapsed": sum(observations.values()) - len(rows),
        "unique_asset_ids": len({r["asset_id"] for r in rows if r["asset_id"]}),
        "valid_unique_asset_ids": len({r["asset_id"] for r in rows if r["id_status"] == "valid"}),
        "invalid_or_deleted_identities": sum(r["id_status"] != "valid" for r in rows),
        "identities_with_image": sum(bool(r.get("image_path")) for r in rows),
        "unique_asset_ids_with_image": len({r["asset_id"] for r in rows if r.get("image_path")}),
        "identities_absent_from_all": sum(not r["in_all_inventory"] for r in rows),
        "reference_count": sum(len(r["references"]) for r in rows)}
    for name, value in expected_stats.items():
        require(stats.get(name) == value, f"{collection}: wrong summary count {name}")
    require(stats["image_status_counts"] == dict(Counter(r["image_status"] for r in rows)), f"{collection}: wrong image status counts")
    with (directory / "assets.csv").open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle, delimiter=";"))
    require(len(csv_rows) == len(rows) and {r["key"] for r in csv_rows} == set(by_key), f"{collection}: CSV identities differ")
    for entry in csv_rows:
        row = by_key[entry["key"]]
        require(entry["asset_id"] == row["asset_id"] and entry["uri"] == row["uri"], f"{collection}: CSV ID/URI changed")
        require(entry["name"] in {row["name"], "'" + row["name"]}, f"{collection}: CSV name changed")
        require(json.loads(entry["references"]) == row["references"] and set(json.loads(entry["tags"])) == set(row["tags"]), f"{collection}: CSV references/tags differ")
    database = directory / "assets.sqlite"
    require(database.is_file(), f"{collection}: SQLite database missing")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and not db.execute("PRAGMA foreign_key_check").fetchall(), f"{collection}: SQLite integrity failure")
        sql_data = db.execute("SELECT key,data_json FROM assets").fetchall()
        require(len(sql_data) == len(rows) and {key: json.loads(data) for key, data in sql_data} == by_key, f"{collection}: SQLite asset data differs")
        require(set(db.execute("SELECT asset_key,tag FROM asset_tags")) == {(r["key"], tag) for r in rows for tag in r["tags"]}, f"{collection}: SQLite category joins differ")
        require({tag for (tag,) in db.execute("SELECT name FROM tags")} == tag_names, f"{collection}: SQLite tag list differs")
        require(set(db.execute("SELECT asset_key,label,asset_id,uri,raw_uri,id_status FROM asset_references")) == {(r["key"], ref["label"], ref["asset_id"], ref["uri"], ref["raw_uri"], ref["id_status"]) for r in rows for ref in r["references"]}, f"{collection}: SQLite reference relations differ")
        require(json.loads(db.execute("SELECT value_json FROM metadata WHERE key='summary'").fetchone()[0]) == summary, f"{collection}: SQLite summary is stale")
    index = read_json(directory / "tags/index.json")
    require(set(index) == tag_names, f"{collection}: per-tag files are incomplete")
    for tag, files in index.items():
        expected = {key: r for key, r in by_key.items() if tag in r["tags"]}
        tagged = read_json(local_file(directory, files["json"]))
        require(len(tagged) == len(expected) == files["count"] and {r["key"]: r for r in tagged} == expected, f"{collection}: per-tag JSON differs for {tag}")
        with local_file(directory, files["csv"]).open(encoding="utf-8-sig", newline="") as handle:
            tagged_csv = list(csv.DictReader(handle, delimiter=";"))
        require(len(tagged_csv) == len(expected) and {r["key"] for r in tagged_csv} == set(expected), f"{collection}: per-tag CSV differs for {tag}")
        require(stats["per_tag"].get(tag) == len(expected), f"{collection}: wrong summary tag count")
    failures = read_json(directory / "failures.json")
    expected_failures = {r["key"] for r in rows if r["id_status"] != "valid" or r["image_status"] not in {"not_requested", "cached", "downloaded"}}
    require(len(failures) == len(expected_failures) and {r["key"] for r in failures} == expected_failures, f"{collection}: failures report differs")

    embedded_collection = payload.get("extra_collections", {}).get(collection)
    require(isinstance(embedded_collection, dict) and embedded_collection.get("summary") == summary, f"{collection}: root gallery collection absent or stale")
    embedded = {(r["asset_id"] or r["uri"], r["name"]): r for r in embedded_collection["records"]}
    require(len(embedded_collection["records"]) == len(rows) and set(embedded) == set(by_identity), f"{collection}: root gallery identities differ")
    for identity, row in by_identity.items():
        displayed = embedded[identity]
        for field in ("asset_id", "name", "uri", "kind", "tags", "image_status"):
            require(displayed.get(field) == row.get(field), f"{collection}: root gallery metadata differs: {field}")
        expected_references = {(ref["label"], ref["asset_id"], ref["uri"]) for ref in row["references"]}
        require({(ref["label"], ref["asset_id"], ref["uri"]) for ref in displayed["references"]} == expected_references, f"{collection}: root gallery references differ")
        for field in ("image_path", "preview_path"):
            expected = collection + "/" + row[field].replace("\\", "/") if row.get(field) else None
            require(displayed.get(field) == expected, f"{collection}: root image prefix is wrong: {field}")
            if expected:
                local_file(root, expected)
    require(embedded_collection["statuses"] == dict(Counter(r["image_status"] for r in rows)) and embedded_collection["with_image"] == sum(bool(r.get("image_path") or r.get("preview_path")) for r in rows), f"{collection}: root gallery image stats differ")
    return {"collection": collection, "captures": len(captures), "tags": len(tag_names),
            "identities": len(rows), "references": expected_stats["reference_count"],
            "local_png_files_checked": len(images), "failure_identities": len(failures),
            "capture_complete": True, "export_phase": summary.get("phase")}


def verify(root, *, verify_png=False):
    root = root.resolve()
    page = (root / "catalogue.html").read_text(encoding="utf-8")
    parser = CatalogueData()
    parser.feed(page)
    require(parser.count == 1, "Root gallery embedded data missing or duplicated")
    payload = json.loads("".join(parser.parts))
    for tab in ("textures", "beams", "meshes"):
        require(f'id="tab-{tab}"' in page, f"Root gallery tab absent: {tab}")
    textures = read_json(root / "textures.json")
    require(len(payload["records"]) == len(textures) and {(r["asset_id"], r["name"]) for r in payload["records"]} == {(r["asset_id"], r["name"]) for r in textures}, "Root gallery lost existing textures")
    reports = [verify_collection(root, collection, payload, verify_png=verify_png) for collection in ("beams", "meshes")]
    return {"result": "PASS", "collections": reports, "deep_png_validation": verify_png,
            "png_chunk_crc_validation": True, "existing_texture_identities": len(textures),
            "checks": ["complete source inventories and selected categories", "primary IDs and secondary references",
                       "exact category joins", "JSON/CSV/SQLite agreement", "per-tag exports",
                       "PNG CRC and dimensions", "summary and failure counts", "root gallery paths and data"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--verify-png", action="store_true", help="Also verify PNG content with Pillow")
    args = parser.parse_args()
    try:
        report = verify(args.root, verify_png=args.verify_png)
    except (VerificationError, OSError, ValueError, KeyError, TypeError, sqlite3.Error, struct.error) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
