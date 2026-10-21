"""Read-only, independent verification of the exported Zonito catalogue.

This verifier does not import the exporter, downloader, gallery or macro. It
reconstructs identities and category memberships directly from source captures,
then compares JSON, CSV, SQLite, tag indexes and embedded HTML data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys


BASE_TAGS = ("Circle", "Crescent", "Effect", "Fire", "Flare", "GUI", "Grid",
             "Ground", "Impact", "Lightning", "Smoke", "Spec", "Star", "Swirl",
             "Text", "Water", "Wind", "Slash", "Other")
SPECIAL = {"all", "personal", "recentlyused", "static", "statics", "flipbook", "flipbooks"}


class VerificationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def token(text):
    return re.sub(r"[^a-z0-9]", "", str(text).casefold())


def visible_text(text):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(text))).split()).casefold()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def raw_identity(record):
    uri = str(record.get("raw_uri") or record.get("image") or "").strip()
    digits = re.findall(r"[0-9]+", uri)
    return (digits[-1] if digits else uri, str(record.get("name") or ""))


def local_file(root, relative):
    require(isinstance(relative, str) and relative, "Empty or non-text local path")
    path = Path(relative)
    require(not path.is_absolute() and ":" not in relative and ".." not in path.parts,
            f"Unsafe local path: {relative!r}")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root), f"Path escapes library: {relative!r}")
    require(resolved.is_file(), f"Missing local file: {relative}")
    return resolved


class EmbeddedData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.parts = []
        self.count = 0
        self.external_scripts = []

    def handle_starttag(self, name, attrs):
        attributes = dict(attrs)
        if name == "script":
            if "src" in attributes:
                self.external_scripts.append(attributes["src"])
            if attributes.get("id") == "catalogue-data":
                self.inside = True
                self.count += 1

    def handle_endtag(self, name):
        if name == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def verify(root: Path, *, verify_png=False):
    root = root.resolve()
    sources = {}
    identities = set()
    memberships = defaultdict(set)
    observation_counts = Counter()
    for path in sorted((root / "source").glob("*.json")):
        capture = read_json(path)
        label = capture.get("label")
        require(isinstance(label, str) and label, f"Missing capture label: {path.name}")
        require(label not in sources, f"Duplicate capture label: {label}")
        records = capture.get("records")
        require(isinstance(records, list), f"Invalid capture records: {label}")
        indexes = [r.get("index") for r in records]
        require(all(type(i) is int and i >= 3 for i in indexes), f"Invalid source index: {label}")
        maximum = capture.get("max_index")
        require(type(maximum) is int and 2 <= maximum <= 1_000_000, f"Invalid maximum index: {label}")
        require(set(indexes) == set(range(3, maximum + 1)), f"Incomplete or out-of-range capture: {label}")
        require(not capture.get("missing_indexes"), f"Capture reports missing indexes: {label}")
        require(not str(capture.get("search") or "").strip(), f"Search filter was active: {label}")
        fingerprints = defaultdict(set)
        for record in records:
            fingerprints[record["index"]].add(json.dumps({key: record.get(key) for key in ("name", "raw_uri", "image", "rect_size")}, sort_keys=True))
        require(all(len(values) == 1 for values in fingerprints.values()), f"Conflicting records at the same source index: {label}")
        kind_capture = token(label) in {"static", "statics", "flipbook", "flipbooks"}
        expected_filter = "tags" if token(label) == "all" or kind_capture else visible_text(label)
        require("active_filter" in capture and visible_text(capture["active_filter"]) == expected_filter,
                f"Capture label does not match single selected filter: {label}")
        if "active_type" in capture:
            expected_types = {"static", "statics"} if token(label) in {"static", "statics"} else {"flipbook", "flipbooks"} if kind_capture else {"all"}
            require(token(visible_text(capture["active_type"])) in expected_types,
                    f"Wrong texture-type filter for capture: {label}")
        if kind_capture:
            require("active_type" in capture, f"Type capture lacks its selected type: {label}")
        for record in records:
            identity = raw_identity(record)
            identities.add(identity)
            memberships[identity].add(label)
            observation_counts[identity] += 1
        sources[label] = capture
    required = {"All", "Statics", "Flipbooks", *BASE_TAGS}
    require(required.issubset(sources), f"Required captures absent: {sorted(required.difference(sources))}")

    rows = read_json(root / "textures.json")
    require(isinstance(rows, list), "textures.json is not a list")
    by_identity = {(r["asset_id"] or r["uri"], r["name"]): r for r in rows}
    require(len(by_identity) == len(rows), "Duplicate identity in textures.json")
    require(set(by_identity) == identities, "Exported identities differ from source captures")
    by_key = {r["key"]: r for r in rows}
    require(len(by_key) == len(rows), "Duplicate exported stable key")
    all_identities = {raw_identity(r) for r in sources["All"]["records"]}
    typed_identities = {raw_identity(r) for label, capture in sources.items()
                        if token(label) in {"static", "statics", "flipbook", "flipbooks"}
                        for r in capture["records"]}
    require(typed_identities == all_identities, "Exact type captures do not cover the All inventory")
    image_files = {}
    for identity, row in by_identity.items():
        require(isinstance(row["asset_id"], str), "An ID lost its string representation")
        labels = memberships[identity]
        expected_tags = {label for label in labels if token(label) not in SPECIAL}
        expected_collections = {label for label in labels if token(label) in SPECIAL and token(label) != "all"}
        require(set(row["tags"]) == expected_tags, f"Incorrect category join: {identity}")
        require(set(row["collections"]) == expected_collections, f"Incorrect collection join: {identity}")
        require(set(row["source_labels"]) == labels, f"Lost source labels: {identity}")
        require(row["observation_count"] == observation_counts[identity], f"Lost observations: {identity}")
        require(bool(row["in_all_inventory"]) == (identity in all_identities), f"Incorrect All membership: {identity}")
        require(row["kind"] in {"static", "flipbook"} and row["grid"] in {0, 2, 4, 8}, f"Unsupported classification: {identity}")
        if row["kind"] == "static":
            require(row["grid"] == 0, f"Static texture has a flipbook grid: {identity}")
        has_static = any(token(label) in {"static", "statics"} for label in labels)
        has_flipbook = any(token(label) in {"flipbook", "flipbooks"} for label in labels)
        require(bool(row["type_collection_ambiguous"]) == (has_static and has_flipbook), f"Incorrect ambiguity flag: {identity}")
        if has_static != has_flipbook:
            require(row["kind"] == ("static" if has_static else "flipbook") and row["kind_source"] == "type_collection",
                    f"Type does not follow exact captured filter membership: {identity}")
        numeric = row["asset_id"]
        if numeric:
            require(row["uri"] == "rbxassetid://" + numeric, f"Noncanonical exported URI: {identity}")
            valid = bool(re.fullmatch(r"[1-9][0-9]*", numeric))
            require((row["id_status"] == "valid") == valid, f"Incorrect placeholder/ID validity: {identity}")
        for field in ("image_path", "preview_path"):
            if row.get(field):
                path = local_file(root, row[field])
                if path not in image_files:
                    with path.open("rb") as handle:
                        header = handle.read(24)
                    require(header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) == 24, f"Not a PNG: {row[field]}")
                    size = struct.unpack(">II", header[16:24])
                    require(all(0 < value <= 16384 for value in size), f"Invalid PNG dimensions: {row[field]}")
                    image_files[path] = size
                if field == "image_path":
                    require((row.get("width"), row.get("height")) == image_files[path], f"Image dimensions disagree with metadata: {identity}")
        if row["image_status"] in {"cached", "downloaded"}:
            require(bool(row.get("image_path")), f"Successful image has no local path: {identity}")

    if verify_png:
        from PIL import Image
        for path in image_files:
            with Image.open(path) as image:
                image.verify()

    summary = read_json(root / "summary.json")
    require(summary.get("phase") == "downloaded" and not summary.get("limited_smokecheck"), "Final export is partial or not downloaded")
    stats = summary["stats"]
    expected_counts = {
        "source_observations": sum(observation_counts.values()),
        "texture_identities": len(rows),
        "all_inventory_identities": len(all_identities),
        "unique_asset_ids": len({r["asset_id"] for r in rows if r["asset_id"]}),
        "valid_unique_asset_ids": len({r["asset_id"] for r in rows if r["id_status"] == "valid"}),
        "identities_with_image": sum(bool(r.get("image_path")) for r in rows),
        "static_identities": sum(r["kind"] == "static" for r in rows),
        "flipbook_identities": sum(r["kind"] == "flipbook" for r in rows),
    }
    for name, expected in expected_counts.items():
        require(stats.get(name) == expected, f"Incorrect summary count: {name}")
    require(stats["image_status_counts"] == dict(Counter(r["image_status"] for r in rows)), "Incorrect image status counts")
    expected_tags = set(BASE_TAGS) | {label for label in sources if token(label) not in SPECIAL}
    require(set(summary["tag_names"]) == expected_tags, "Summary tag list differs from captured categories")

    with (root / "textures.csv").open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle, delimiter=";"))
    require(len(csv_rows) == len(rows) and {r["key"] for r in csv_rows} == set(by_key), "CSV export differs from JSON")
    for record in csv_rows:
        row = by_key[record["key"]]
        require(record["asset_id"] == row["asset_id"], "CSV ID changed")
        require(record["name"] in {row["name"], "'" + row["name"]}, "CSV name changed beyond formula protection")
        require(set(json.loads(record["tags"])) == set(row["tags"]), "CSV tags differ")

    database = root / "textures.sqlite"
    require(database.is_file(), "SQLite export absent")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity check failed")
        require(not db.execute("PRAGMA foreign_key_check").fetchall(), "SQLite has broken foreign keys")
        sql_rows = db.execute("SELECT key,asset_id,name,kind,grid,grid_source,image_path,image_status,kind_source FROM textures").fetchall()
        expected_sql = {(r["key"], r["asset_id"], r["name"], r["kind"], r["grid"], r["grid_source"], r.get("image_path"), r["image_status"], r["kind_source"]) for r in rows}
        require(len(sql_rows) == len(rows) and set(sql_rows) == expected_sql, "SQLite rows differ from JSON")
        require(set(db.execute("SELECT texture_key,tag FROM texture_tags")) == {(r["key"], tag) for r in rows for tag in r["tags"]}, "SQLite tag joins differ")
        require({r[0] for r in db.execute("SELECT name FROM tags")} == expected_tags, "SQLite tag list differs")
        require(json.loads(db.execute("SELECT value_json FROM metadata WHERE key='summary'").fetchone()[0]) == summary, "SQLite summary differs")

    tag_index = read_json(root / "tags/index.json")
    require(set(tag_index) == expected_tags, "Per-tag index is incomplete")
    for tag, paths in tag_index.items():
        expected_keys = {r["key"] for r in rows if tag in r["tags"]}
        tagged = read_json(local_file(root, paths["json"]))
        require(len(tagged) == paths["count"] == len(expected_keys), f"Wrong per-tag JSON count: {tag}")
        require({r["key"] for r in tagged} == expected_keys, f"Wrong per-tag JSON contents: {tag}")
        require(stats["per_tag"].get(tag) == len(expected_keys), f"Wrong summary tag count: {tag}")
        with local_file(root, paths["csv"]).open(encoding="utf-8-sig", newline="") as handle:
            tagged_csv = list(csv.DictReader(handle, delimiter=";"))
        require(len(tagged_csv) == len(expected_keys) and {r["key"] for r in tagged_csv} == expected_keys, f"Wrong per-tag CSV: {tag}")

    expected_failures = {r["key"] for r in rows if r["id_status"] != "valid" or r["image_status"] not in {"cached", "downloaded", "not_requested"}}
    failures = read_json(root / "failures.json")
    require(len(failures) == len(expected_failures) and {r["key"] for r in failures} == expected_failures, "Failure report differs from JSON statuses")

    page = (root / "catalogue.html").read_text(encoding="utf-8")
    parser = EmbeddedData()
    parser.feed(page)
    require(parser.count == 1 and not parser.external_scripts, "HTML data script missing/duplicated or remote script present")
    payload = json.loads("".join(parser.parts))
    require(payload["summary"] == summary, "HTML summary is stale")
    embedded = {(r["asset_id"], r["name"]): r for r in payload["records"]}
    require(len(payload["records"]) == len(rows), "HTML row count differs")
    require(set(embedded) == {(r["asset_id"], r["name"]) for r in rows}, "HTML identities differ")
    for row in rows:
        displayed = embedded[(row["asset_id"], row["name"])]
        for field in ("tags", "kind", "kind_source", "type_collection_ambiguous", "grid", "grid_source", "image_path", "preview_path", "image_status"):
            require(displayed.get(field) == row.get(field), f"HTML metadata is stale: {field}, {row['name']}")
    require(payload["statuses"] == dict(Counter(r["image_status"] for r in rows)), "HTML image statuses differ")
    require(payload["with_image"] == sum(bool(r.get("image_path") or r.get("preview_path")) for r in rows), "HTML image count differs")
    require("Type enregistré depuis le filtre du plugin" in page and "Type ambigu" in page, "Type provenance hint absent from HTML")
    return {"result": "PASS", "captures": len(sources), "identities": len(rows),
            "tags": len(expected_tags), "local_png_files_checked": len(image_files),
            "deep_png_validation": verify_png, "failure_identities": len(failures),
            "checks": ["capture coverage and selected filters", "identity and tag preservation",
                       "exact static/flipbook filter membership", "JSON/CSV/SQLite agreement",
                       "per-tag exports", "local image paths and dimensions", "summary and failure counts",
                       "embedded offline HTML metadata and provenance"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--verify-png", action="store_true", help="Also verify every PNG with Pillow")
    args = parser.parse_args()
    try:
        report = verify(args.root, verify_png=args.verify_png)
    except (VerificationError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
