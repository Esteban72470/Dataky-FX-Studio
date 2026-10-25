"""Existing CLI/MCP catalogue reads observe disk updates without a process restart."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import fx_tools


class ExistingCatalogueRefresh(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(mock.patch.object(fx_tools, "ROOT", self.root))
        self.enterContext(mock.patch.object(fx_tools, "_catalogs", {}))
        self.enterContext(mock.patch.object(fx_tools, "_catalog_fingerprints", {}))
        self.file = self.root / "textures.json"
        self.write([self.asset("101", "Alpha")])

    @staticmethod
    def asset(ident, name):
        return {"asset_id": ident, "uri": "rbxassetid://" + ident, "name": name,
                "kind": "static", "id_status": "valid", "tags": ["Impact"]}

    def write(self, rows):
        self.file.write_text(json.dumps(rows), encoding="utf-8")

    def test_add_change_remove_are_seen_by_search_in_the_same_process(self):
        self.assertEqual(fx_tools.search_assets(query="Alpha")["total"], 1)
        self.write([self.asset("101", "Alpha"), self.asset("202", "Beta")])
        self.assertEqual(fx_tools.search_assets(query="Beta")["items"][0]["id"], "202")
        self.write([self.asset("101", "Gamma")])
        self.assertEqual(fx_tools.search_assets(query="Gamma")["items"][0]["id"], "101")
        self.assertEqual(fx_tools.search_assets(query="Beta")["total"], 0)
        self.file.unlink()
        self.assertEqual(fx_tools.search_assets()["total"], 0)

    def test_same_length_and_preserved_timestamp_changes_are_detected(self):
        first = fx_tools.catalog("textures")
        stamp = self.file.stat()
        self.write([self.asset("101", "Omega")])
        self.assertEqual(self.file.stat().st_size, stamp.st_size)
        os.utime(self.file, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(first[0]["name"], "Alpha")
        self.assertEqual(fx_tools.catalog("textures")[0]["name"], "Omega")

    def test_unchanged_bytes_reuse_json_parse_and_root_changes_do_not_reuse_rows(self):
        original_parser = json.loads
        with mock.patch.object(fx_tools.json, "loads", wraps=original_parser) as parse:
            fx_tools.catalog("textures")
            fx_tools.catalog("textures")
        self.assertEqual(parse.call_count, 1)
        other = self.root / "another-copy"
        other.mkdir()
        (other / "textures.json").write_text(json.dumps([self.asset("303", "Other")]), encoding="utf-8")
        with mock.patch.object(fx_tools, "ROOT", other):
            self.assertEqual(fx_tools.catalog("textures")[0]["asset_id"], "303")
        self.assertEqual(fx_tools.catalog("textures")[0]["asset_id"], "101")

    def test_malformed_updates_never_silently_reuse_old_rows(self):
        self.assertEqual(len(fx_tools.catalog("textures")), 1)
        for content in ("{", "{}", "[1]"):
            self.file.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(fx_tools.ToolError):
                fx_tools.catalog("textures")
        self.write([self.asset("202", "Fixed")])
        self.assertEqual(fx_tools.catalog("textures")[0]["name"], "Fixed")

    def test_each_collection_refreshes_independently(self):
        (self.root / "beams").mkdir()
        (self.root / "meshes").mkdir()
        for collection, ident in (("beams", "404"), ("meshes", "505")):
            file = self.root / collection / "assets.json"
            file.write_text(json.dumps([self.asset(ident, "First")]), encoding="utf-8")
            self.assertEqual(fx_tools.catalog(collection)[0]["asset_id"], ident)
            file.write_text(json.dumps([self.asset(ident, "Changed")]), encoding="utf-8")
            self.assertEqual(fx_tools.catalog(collection)[0]["name"], "Changed")
        self.assertEqual(fx_tools.catalog("textures")[0]["name"], "Alpha")


if __name__ == "__main__":
    unittest.main()
