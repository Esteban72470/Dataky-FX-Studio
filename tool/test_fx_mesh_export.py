"""Local preview triangles must never masquerade as Roblox mesh assets."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

try:
    from .fx_export import MeshExportError, export_library, export_project, mesh_export_manifest, prepare_native_project, write_library
    from .fx_rbxmx import export_rbxmx, player_source
    from . import fx_tools
except ImportError:
    from fx_export import MeshExportError, export_library, export_project, mesh_export_manifest, prepare_native_project, write_library
    from fx_rbxmx import export_rbxmx, player_source
    import fx_tools


def local_mesh(mesh_id=""):
    return {
        "version": 1, "name": "Imported triangle", "duration": 1,
        "nodes": [{"id": "mesh", "class": "MeshPart", "properties": {
            "MeshId": mesh_id, "Size": [2, 2, .01], "Transparency": 0, "Position": [1, 2, 3],
        }}],
        "animations": [{"node": "mesh", "property": "Position", "runtime": True,
                        "keyframes": [{"time": 0, "value": [1, 2, 3]}, {"time": 1, "value": [4, 5, 6]}]}],
        "editor": {"version": 1, "curves": {}, "meshes": {"mesh": {
            "version": 1,
            "positions": [-.5, -.5, 0, .5, -.5, 0, 0, .5, 0],
            "normals": [0, 0, 1] * 3, "uvs": [0, 0, 1, 0, .5, 1], "indices": [0, 1, 2],
            "source": {"name": "triangle.obj", "format": "obj", "sha256": "a" * 64, "dimensions": [2, 2, .01]},
        }}},
    }


class MeshExportTests(unittest.TestCase):
    def test_unmapped_geometry_is_blocked_in_every_native_entrypoint(self):
        project = local_mesh()
        original = deepcopy(project)
        for operation in (export_project, export_rbxmx, player_source, prepare_native_project,
                          lambda value: export_library({"Triangle": value})):
            with self.subTest(operation=operation):
                with self.assertRaises(MeshExportError) as raised:
                    operation(project)
                self.assertFalse(raised.exception.manifest["exportable"])
                self.assertEqual(raised.exception.manifest["missing_assets"][0]["node"], "mesh")
                self.assertIn("MeshId", str(raised.exception))
        self.assertEqual(project, original)

    def test_local_rbxasset_paths_and_zero_are_not_persistent_upload_mappings(self):
        for value in ("0", "rbxassetid://0", "rbxasset://meshes/preview.mesh"):
            with self.subTest(value=value):
                with self.assertRaises(MeshExportError):
                    export_project(local_mesh(value))

    def test_mapping_strips_preview_buffers_but_keeps_tracks_and_native_properties(self):
        for mapping in ("123", "rbxassetid://123", "https://www.roblox.com/asset/?id=123"):
            project = local_mesh(mapping)
            original = deepcopy(project)
            native = prepare_native_project(project)
            self.assertNotIn("meshes", native["editor"])
            self.assertEqual(native["animations"], project["animations"])
            self.assertEqual(native["nodes"][0]["properties"], project["nodes"][0]["properties"])
            for source in (export_project(project), export_library({"Triangle": project}), export_rbxmx(project)):
                self.assertNotIn("triangle.obj", source)
                self.assertNotIn('["positions"]', source)
                self.assertIn('["runtime"]=true', source)
            root = ET.fromstring(export_rbxmx(project))
            mesh = root.find(".//Item[@class='MeshPart']")
            self.assertIsNotNone(mesh)
            self.assertEqual(mesh.find("Properties/Content[@name='MeshContent']/uri").text, "rbxassetid://123")
            self.assertEqual(project, original)

    def test_manifest_is_small_reproducible_and_explicit_about_manual_verification(self):
        missing = mesh_export_manifest(local_mesh())
        self.assertFalse(missing["exportable"])
        self.assertEqual(missing["missing_assets"][0]["source"]["sha256"], "a" * 64)
        self.assertTrue(missing["manual_steps"])
        mapped = mesh_export_manifest(local_mesh("123"))
        self.assertTrue(mapped["exportable"])
        self.assertEqual(mapped["mapped_assets"][0]["mesh_id"], "rbxassetid://123")
        self.assertIn("permissions", mapped["mapped_assets"][0]["verification"])
        self.assertNotIn("positions", json.dumps(mapped))
        self.assertEqual(mapped, mesh_export_manifest(local_mesh("123")))

    def test_json_and_manifest_exports_preserve_editable_geometry_when_native_blocked(self):
        project = local_mesh()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            json_path = fx_tools.export(project, "json", out / "editable.json")
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["editor"]["meshes"], project["editor"]["meshes"])
            manifest_path = fx_tools.export(project, "manifest", out / "assets.json")
            self.assertFalse(json.loads(manifest_path.read_text(encoding="utf-8"))["exportable"])
            target = out / "native.lua"
            with self.assertRaises(MeshExportError):
                fx_tools.export(project, "lua", target)
            self.assertFalse(target.exists())
            with self.assertRaises(MeshExportError):
                write_library({"Triangle": project}, target)
            self.assertFalse(target.exists())
            self.assertFalse((out / "DatakyFXKit.lua").exists())

    def test_legacy_recipes_need_no_preview_mapping(self):
        project = {"version": 1, "name": "Legacy", "duration": 1,
                   "nodes": [{"id": "part", "class": "Part", "properties": {}}]}
        self.assertTrue(mesh_export_manifest(project)["exportable"])
        self.assertFalse(mesh_export_manifest(project)["manual_steps"])
        self.assertIn("local Project", export_project(project))

    @unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent (DATAKY_LUAU)")
    def test_mapped_import_library_actually_plays_mesh_tracks_and_cleans_up_in_luau(self):
        project = local_mesh("rbxassetid://123")
        project["animations"].append({"node": "mesh", "property": "Transparency", "runtime": True,
            "keyframes": [{"time": 0, "value": .2}, {"time": 1, "value": .8}]})
        folder = Path(__file__).resolve().parent
        source = (folder / "luau_roblox_mock.luau").read_text(encoding="utf-8")
        source += "\nlocal FX = (function()\n" + (folder / "fx_kit.lua").read_text(encoding="utf-8") + "\nend)()\n"
        source += "local Recipes = (function()\n" + export_library({"Imported": project}) + "\nend)()\n"
        source += '''
local R = Recipes.Imported
assert(R.editor.meshes == nil, "local buffers must be omitted")
FX.preload(R)
local h = FX.play(R, CFrame.new(10,0,0)*CFrame.fromOrientation(0,math.pi/2,0), {scale=2})
Step(.5)
local p = h:Part("mesh")
local function near(a,b) assert(math.abs(a-b)<.00001,tostring(a).." ~= "..tostring(b)) end
near(p.Position.X,19); near(p.Position.Y,7); near(p.Position.Z,-5)
near(p.Transparency,.5); near(p.Size.X,4)
h:Stop()
assert(p.Parent == nil, "Stop must destroy mesh instances")
print("IMPORTED_MESH_OK")
'''
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "mapped-import.luau"
            script.write_text(source, encoding="utf-8")
            result = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), str(script)],
                                    capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IMPORTED_MESH_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
