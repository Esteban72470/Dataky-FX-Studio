"""Reviewed catalogue names and layouts, separate from immutable source captures."""
from __future__ import annotations

import ast
from pathlib import Path

DATA_FILE = "tool/catalog_annotations_data.py"
MAX_BYTES = 2 * 1024 * 1024


def annotation_bytes(root):
    path = Path(root) / DATA_FILE
    try:
        with path.open("rb") as source:
            body = source.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return b""
    if len(body) > MAX_BYTES:
        raise ValueError("Catalogue annotations exceed 2 MiB")
    return body


def parse_annotations(body):
    if not body:
        return {}
    # This data-only Python file ships through the existing code updater. Never
    # execute it: accepting one literal assignment also makes edits auditable.
    tree = ast.parse(body.decode("utf-8-sig"))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign) or len(tree.body[0].targets) != 1 or not isinstance(tree.body[0].targets[0], ast.Name) or tree.body[0].targets[0].id != "DATA":
        raise ValueError("Catalogue annotations require one DATA literal")
    data = ast.literal_eval(tree.body[0].value)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("textures"), dict):
        raise ValueError("Invalid catalogue annotations")
    for ident, entry in data["textures"].items():
        if not isinstance(ident, str) or not ident.isdecimal() or not isinstance(entry, dict):
            raise ValueError("Invalid catalogue annotation identity")
        if "name" in entry and (not isinstance(entry["name"], str) or not entry["name"].strip() or len(entry["name"]) > 160):
            raise ValueError("Invalid reviewed name")
        for key in ("grid_columns", "grid_rows"):
            if key in entry and (type(entry[key]) is not int or not 1 <= entry[key] <= 64):
                raise ValueError("Invalid reviewed layout")
        if ("grid_columns" in entry) != ("grid_rows" in entry):
            raise ValueError("A reviewed layout requires columns and rows")
    return data["textures"]


def apply_annotations(rows, root=None, *, body=None, collection="textures"):
    if collection != "textures":
        return rows
    entries = parse_annotations(annotation_bytes(root) if body is None else body)
    result = []
    for original in rows:
        entry = entries.get(str(original.get("asset_id")))
        if not entry:
            result.append(original)
            continue
        row = dict(original)
        if entry.get("name"):
            old = row.get("original_name", row.get("name", ""))
            row["original_name"] = old
            aliases = list(row.get("aliases") or [])
            for alias in (old, row.get("name")):
                if alias and alias != entry["name"] and alias not in aliases:
                    aliases.append(alias)
            row.update(name=entry["name"], aliases=aliases, name_source="catalogue_review", name_observer=entry.get("name_observer", "vision"))
        columns, lines = entry.get("grid_columns"), entry.get("grid_rows")
        if row.get("kind") == "flipbook" and columns and lines and columns * lines > 1:
            row.update(grid=columns if columns == lines and columns in (2, 4, 8) else 0,
                       grid_columns=columns, grid_rows=lines, grid_source="verified",
                       grid_review_status="confirmed", grid_review_observer=entry.get("grid_observer", "vision"))
        elif entry.get("grid_review_status"):
            row["grid_review_status"] = entry["grid_review_status"]
            row["grid_review_observer"] = entry.get("grid_observer", "metadata")
        if entry.get("grid_review_note"):
            row["grid_review_note"] = entry["grid_review_note"]
        result.append(row)
    return result
