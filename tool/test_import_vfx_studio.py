import importlib
from contextlib import closing
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import import_vfx_studio as merger

LIBRARY = Path(os.environ.get("DATAKY_LIBRARY", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(LIBRARY / "tool"))
merger._catalog = catalog = importlib.import_module("catalog")
assets = importlib.import_module("asset_catalog")


def capture(raw, label="All", collection="textures"):
    return merger.prepare_record(raw, {"label": label, "active_type": "All", "captured_at": "2026-10-25", "collection": collection}, Path(label + ".json"), collection, catalog)


class MergeTests(unittest.TestCase):
    def test_id_normalization_ignores_thumbnail_dimensions_and_invalid(self):
        self.assertEqual(merger.canonical_id("rbxthumb://type=Asset&id=12345&w=150&h=150"), "12345")
        self.assertEqual(merger.canonical_id("rbxassetid://rbxassetid://12345"), "12345")
        for value in ("rbxasset://textures/grid4.png", "0", "01", "https://somewhere/12345.png"):
            self.assertIsNone(merger.canonical_id(value))

    def test_merges_id_enriches_name_preserves_keys_aliases_tags_images(self):
        first = capture({"name": "Circle19", "raw_uri": "rbxassetid://123"}, "Circle")
        first.update(key="old-stable-key", image_path="images/123.png", preview_path="images/123.png", image_status="cached", plugins=["ZonitoVisuals"])
        second = capture({"name": "Splash Circle", "raw_uri": "rbxthumb://type=Asset&id=123&w=150&h=150"}, "Water")
        rows, report = merger.merge_rows([first], [second], "textures")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["key"], "old-stable-key")
        self.assertEqual(row["name"], "Splash Circle")
        self.assertIn("Circle19", row["aliases"])
        self.assertEqual(set(row["tags"]), {"Circle", "Water"})
        self.assertEqual(row["image_path"], "images/123.png")
        self.assertEqual(report["new_ids"], 0)
        again, _ = merger.merge_rows(rows, [second], "textures")
        self.assertEqual(again, rows)

    def test_invalid_placeholders_are_not_mistaken_for_same_asset(self):
        rows, _ = merger.merge_rows([], [capture({"name": "Deleted Smoke", "raw_uri": "rbxassetid://0"}), capture({"name": "Deleted Slash", "raw_uri": "rbxassetid://0"})], "textures")
        self.assertEqual(len(rows), 2)

    def test_mesh_id_is_unique_without_losing_different_texture_variants(self):
        first = capture({"name": "Wind", "mesh_uri": "rbxassetid://123"}, "Wind", "meshes")
        second = capture({"name": "Wind Fire", "mesh_uri": "rbxassetid://123", "texture_uri": "rbxassetid://456"}, "Fire", "meshes")
        third = capture({"name": "Wind Blue", "mesh_uri": "rbxassetid://123", "texture_uri": "rbxassetid://789"}, "Water", "meshes")
        rows, report = merger.merge_rows([first], [second, third], "meshes")
        self.assertEqual(len(rows), 1)
        self.assertEqual([v["texture_uri"] for v in rows[0]["variants"]], ["", "rbxassetid://456", "rbxassetid://789"])
        self.assertEqual(report["mesh_texture_variants"], 3)
        self.assertEqual(rows[0]["primary_texture_uri"], "")

    def test_incomplete_capture_rejected(self):
        with self.assertRaises(ValueError):
            merger.validate_capture({"records": [], "missing_indexes": [3]}, Path("All.json"))
        with self.assertRaises(ValueError):
            merger.validate_capture({"records": [], "search": "smoke"}, Path("All.json"))

    def test_mesh_sqlite_reference_identity_ignores_raw_uri_spelling(self):
        a = capture({"name": "Wind", "mesh_uri": "rbxassetid://123"}, "Wind", "meshes")
        b = capture({"name": "Wind", "mesh_uri": "https://www.roblox.com/asset/?id=123"}, "Wind", "meshes")
        rows, report = merger.merge_rows([a], [b], "meshes")
        self.assertEqual(len(rows[0]["references"]), 1)
        with tempfile.TemporaryDirectory() as temp:
            merger.export_merged(rows, Path(temp), "meshes", report, catalog, assets)

    def test_new_flipbook_type_and_explicit_grid_are_retained(self):
        raw = {"name": "Smoke Burst", "raw_uri": "rbxassetid://555", "grid": 4}
        source = merger.prepare_record(raw, {"label": "Smoke", "active_type": "Flipbook"}, Path("Smoke.json"), "textures", catalog)
        rows, _ = merger.merge_rows([], [source], "textures")
        self.assertEqual(rows[0]["kind"], "flipbook")
        self.assertEqual(rows[0]["grid"], 4)
        self.assertEqual(rows[0]["observed_rect_kinds"], [])
        self.assertEqual(rows[0]["classification_conflicts"], [])

    def test_merged_key_alias_and_mesh_variants_resolve_in_runtime(self):
        module = importlib.import_module("fx_ai_catalog")
        first = capture({"name": "Wind", "mesh_uri": "rbxassetid://123"}, "Wind", "meshes")
        first["key"] = "legacy-untextured-key"
        second = capture({"name": "Fire Wind", "mesh_uri": "rbxassetid://123", "texture_uri": "rbxassetid://456"}, "Fire", "meshes")
        second["key"] = "legacy-textured-key"
        rows, _ = merger.merge_rows([first, second], [], "meshes")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "meshes").mkdir()
            (root / "meshes/assets.json").write_text(json.dumps(rows), encoding="utf-8")
            snapshot = module.snapshot(root)
            self.assertEqual(snapshot["counts"]["meshes"], 2)
            self.assertEqual(module.get_asset("legacy-untextured-key", snapshot=snapshot)["mesh_texture_id"], "")
            self.assertEqual(module.get_asset("legacy-textured-key", snapshot=snapshot)["mesh_texture_id"], "rbxassetid://456")
            self.assertEqual(len(module.editor_catalog(root)["meshes"]), 1)
            self.assertEqual(module.search("legacy-textured-key", snapshot=snapshot)["items"][0]["key"], "meshes:123@456")

    def test_exports_sqlite_csv_tags_gallery_without_changing_evidence(self):
        rows, report = merger.merge_rows([], [capture({"name": "Splash Circle", "raw_uri": "rbxassetid://123"}, "Water")], "textures")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            merger.export_merged(rows, root, "textures", report, catalog, assets)
            import sqlite3
            with closing(sqlite3.connect(root / "textures.sqlite")) as db:
                self.assertEqual(db.execute("SELECT name,asset_id FROM textures").fetchone(), ("Splash Circle", "123"))
                self.assertEqual(json.loads(db.execute("SELECT plugins_json FROM plugin_provenance").fetchone()[0]), ["VFX Studio"])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(len(json.loads((root / "tags/Water.json").read_text(encoding="utf-8"))), 1)
            self.assertIn("name_provenance", (root / "textures.csv").read_text(encoding="utf-8-sig"))
            self.assertTrue((root / "catalogue.html").is_file())

    def test_normal_texture_rebuild_retains_saved_second_plugin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label in catalog.REQUIRED:
                records = [{"index": 3, "name": "Old Circle", "raw_uri": "rbxassetid://123", "rect_size": [0, 0]}] if label == "All" else []
                catalog._write_json(root / "source" / (label + ".json"), {"label": label, "records": records, "max_index": 3 if records else 2, "missing_indexes": [], "search": "", "active_filter": "Tags" if label == "All" else label})
            catalog._write_json(root / "source/vfx-studio/textures/textures-metadata.json", {"source": {"plugin": "VFX Studio"}, "records": [{"asset_id": "456", "uri": "rbxassetid://456", "name": "New Spark", "tags": ["Star"], "kind": "static", "grid": 0}]})
            args = SimpleNamespace(root=str(root), allow_partial=False, limit=None, skip_download=True, workers=1)
            rows, _ = catalog.run(args)
            self.assertEqual({r["asset_id"] for r in rows}, {"123", "456"})
            again, _ = catalog.run(args)
            self.assertEqual(rows, again)

    def test_normal_mesh_rebuild_retains_saved_second_plugin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = [{"index": 3, "name": "Old Wind", "mesh_uri": "rbxassetid://123", "raw_uri": "rbxassetid://123"}]
            catalog._write_json(root / "meshes/source/All.json", {"collection": "meshes", "label": "All", "records": records, "first_index": 3, "max_index": 3, "missing_indexes": [], "search": "", "active_collection": "Meshes", "active_filter": "Tags", "available_tags": []})
            catalog._write_json(root / "source/vfx-studio/meshes/meshes-metadata.json", {"source": {"plugin": "VFX Studio"}, "records": [{"asset_id": "456", "uri": "rbxassetid://456", "mesh_uri": "rbxassetid://456", "name": "New Wind"}]})
            rows, _ = assets.rebuild_extra(root, "meshes", skip_download=True)
            self.assertEqual({r["asset_id"] for r in rows}, {"123", "456"})
            again, _ = assets.rebuild_extra(root, "meshes", skip_download=True)
            self.assertEqual(rows, again)


if __name__ == "__main__":
    unittest.main()
