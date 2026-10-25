"""Composition must preserve preview geometry and its native upload gate."""
from copy import deepcopy
import unittest

try:
    from .fx_builder import merge_recipes
    from .fx_export import MeshExportError, export_project, mesh_export_manifest
    from .fx_modules import compose
    from .fx_rbxmx import export_rbxmx
    from .test_fx_mesh_export import local_mesh
except ImportError:
    from fx_builder import merge_recipes
    from fx_export import MeshExportError, export_project, mesh_export_manifest
    from fx_modules import compose
    from fx_rbxmx import export_rbxmx
    from test_fx_mesh_export import local_mesh


BASE = {"version": 1, "name": "Base", "duration": 1, "nodes": [], "animations": []}


class MeshMergeTests(unittest.TestCase):
    def test_merge_remaps_unmapped_geometry_without_mutation_and_keeps_export_gate(self):
        source, base = local_mesh(), deepcopy(BASE)
        original_source, original_base = deepcopy(source), deepcopy(base)
        merged = merge_recipes(base, source, "piece_", scale=2, at=.5, position=[3, 1, 0])
        self.assertEqual(merged["editor"]["meshes"]["piece_mesh"], source["editor"]["meshes"]["mesh"])
        self.assertEqual(merged["nodes"][0]["properties"]["Size"], [4, 4, .02])
        manifest = mesh_export_manifest(merged)
        self.assertFalse(manifest["exportable"])
        self.assertEqual(manifest["missing_assets"][0]["node"], "piece_mesh")
        with self.assertRaises(MeshExportError):
            export_rbxmx(merged)
        merged["editor"]["meshes"]["piece_mesh"]["positions"][0] = .2
        self.assertEqual(source, original_source)
        self.assertEqual(base, original_base)

    def test_mapped_geometry_keeps_tracks_and_existing_base_mesh_metadata(self):
        base = local_mesh("rbxassetid://123")
        source = local_mesh("rbxassetid://456")
        original = deepcopy(base)
        merged = merge_recipes(base, source, "second_", at=.5)
        self.assertEqual(set(merged["editor"]["meshes"]), {"mesh", "second_mesh"})
        tracks = [track for track in merged["animations"] if track["node"] == "second_mesh"]
        self.assertTrue(tracks[0]["runtime"])
        self.assertEqual(tracks[0]["keyframes"][0]["time"], .5)
        self.assertTrue(mesh_export_manifest(merged)["exportable"])
        self.assertIn("rbxassetid://456", export_rbxmx(merged))
        self.assertNotIn("triangle.obj", export_project(merged))
        self.assertEqual(base, original)

    def test_compose_include_never_loses_unmapped_mesh_gate(self):
        source = local_mesh()
        merged = compose({"name": "Included mesh", "blocks": [
            {"include": "triangle", "prefix": "included_", "scale": 1.5}
        ]}, include_loader=lambda name: deepcopy(source))
        self.assertIn("included_mesh", merged["editor"]["meshes"])
        self.assertFalse(mesh_export_manifest(merged)["exportable"])
        with self.assertRaises(MeshExportError):
            export_project(merged)


if __name__ == "__main__":
    unittest.main()
