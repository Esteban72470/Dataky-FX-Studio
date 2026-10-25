"""Catalogue assets actually reach emitter/mesh properties and native exports."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

try:
    from . import fx_ai_assets as assets
    from .fx_export import _lua, export_library, mesh_export_manifest
    from .fx_rbxmx import export_rbxmx
    from .fx_mesh import import_obj
except ImportError:
    import fx_ai_assets as assets
    from fx_export import _lua, export_library, mesh_export_manifest
    from fx_rbxmx import export_rbxmx
    from fx_mesh import import_obj


TEXTURE = {"key": "textures:901234567", "collection": "textures", "id": "901234567", "uri": "rbxassetid://901234567",
           "name": "New frost sprite", "kind": "static", "tags": ["Ice"]}
FLIPBOOK = {"key": "textures:901234568", "collection": "textures", "id": "901234568", "uri": "rbxassetid://901234568",
            "name": "New frost atlas", "kind": "flipbook", "tags": ["Ice"],
            "flipbook": {"grid": 2, "estimated": True, "FlipbookLayout": "Grid2x2"}}
BEAM = {"key": "beams:901234569", "collection": "beams", "id": "901234569", "uri": "rbxassetid://901234569",
        "name": "New frost ribbon", "kind": "beam", "tags": ["Ice"]}
MESH = {"key": "meshes:901234570", "collection": "meshes", "id": "901234570", "uri": "rbxassetid://901234570",
        "mesh_id": "rbxassetid://901234570", "mesh_texture_id": "rbxassetid://901234571", "name": "New frost slash", "kind": "mesh"}
SNAPSHOT = {"revision": "fixture", "assets": [TEXTURE, FLIPBOOK, BEAM, MESH]}


def layer(block, **values):
    return {"block": block, "at": .4, "color": [.2, .5, 1], **values}


def compile_layers(blocks, selections, snapshot=SNAPSHOT, geometry=None):
    with patch.object(assets, "_catalogue", return_value=SimpleNamespace(load_geometry=lambda asset, root=None: deepcopy(geometry))):
        return assets.compile_plan({"name": "Frost", "blocks": blocks}, selections, snapshot=snapshot)


class AssetCompilerTests(unittest.TestCase):
    def test_every_particle_block_changes_main_texture_and_preserves_secondaries(self):
        blocks = [layer(name) for name in ("flash", "sparks", "shockwave", "smoke", "slash", "fire", "charge", "orb")]
        result = compile_layers(blocks, [TEXTURE] * len(blocks))
        by_id = {node["id"]: node for node in result["project"]["nodes"]}
        for binding in result["bindings"]:
            with self.subTest(block=binding["block"]):
                self.assertEqual(binding["asset_key"], TEXTURE["key"])
                self.assertTrue(binding["nodes"])
                for ident in binding["nodes"]:
                    props = by_id[ident]["properties"]
                    self.assertEqual(props["Texture"], TEXTURE["uri"])
                    self.assertEqual(props["FlipbookLayout"], "None")
        # The slash's supporting halo keeps its deliberate secondary mask.
        slash_nodes = [node for node in result["project"]["nodes"] if node["id"].startswith("ai5_") and node["class"] == "ParticleEmitter"]
        self.assertEqual(len(slash_nodes), 2)
        self.assertNotEqual(slash_nodes[1]["properties"]["Texture"], TEXTURE["uri"])

    def test_known_flipbook_replaces_grid_and_unknown_grid_is_explicit(self):
        result = compile_layers([layer("fire")], [FLIPBOOK])
        emitter = next(node for node in result["project"]["nodes"] if node["class"] == "ParticleEmitter")
        self.assertEqual(emitter["properties"]["FlipbookLayout"], "Grid2x2")
        self.assertEqual(emitter["properties"]["FlipbookMode"], "OneShot")
        self.assertTrue(any("estimée" in warning for warning in result["warnings"]))
        unknown = deepcopy(FLIPBOOK); unknown["flipbook"]["grid"] = 0
        result = compile_layers([layer("fire")], [unknown], {"assets": [unknown]})
        emitter = next(node for node in result["project"]["nodes"] if node["class"] == "ParticleEmitter")
        self.assertEqual(emitter["properties"]["FlipbookLayout"], "None")
        self.assertTrue(any("inconnue" in warning for warning in result["warnings"]))

    def test_beam_and_trail_receive_selected_ribbon_texture(self):
        result = compile_layers([layer("arc"), layer("swipe")], [BEAM["key"], {"key": BEAM["key"]}])
        targets = [node for node in result["project"]["nodes"] if node["class"] in {"Beam", "Trail"}]
        self.assertEqual({node["class"] for node in targets}, {"Beam", "Trail"})
        self.assertTrue(all(node["properties"]["Texture"] == BEAM["uri"] for node in targets))
        support_motion = next(track for track in result["project"]["animations"] if track["property"] == "Position")
        self.assertTrue(support_motion["runtime"], "AI trail support motion must also play in the native kit")
        root = ET.fromstring(export_rbxmx(result["project"]))
        self.assertIn(BEAM["uri"], ET.tostring(root).decode())

    def test_selection_is_resolved_from_snapshot_not_model_supplied_paths_or_uris(self):
        tampered = {**TEXTURE, "uri": "https://evil.test", "geometry_path": "../../private.json"}
        result = compile_layers([layer("sparks")], [tampered])
        emitter = next(node for node in result["project"]["nodes"] if node["class"] == "ParticleEmitter")
        self.assertEqual(emitter["properties"]["Texture"], TEXTURE["uri"])
        for selected in ("textures:999999", {"key": MESH["key"]}):
            with self.subTest(selected=selected), self.assertRaises(assets.AssetCompileError):
                compile_layers([layer("sparks")], [selected])

    def test_explicit_keys_reject_missing_or_different_selection(self):
        result = compile_layers([layer("flash", asset_key=TEXTURE["key"])], [None])
        self.assertEqual(result["bindings"][0]["asset_key"], TEXTURE["key"])
        with self.assertRaises(assets.AssetCompileError):
            compile_layers([layer("flash", asset_key=TEXTURE["key"])], [FLIPBOOK])
        with self.assertRaises(assets.AssetCompileError):
            compile_layers([layer("mesh")], [None])

    def test_mesh_catalogue_asset_becomes_native_mesh_with_shared_timeline(self):
        result = compile_layers([layer("mesh", duration=.6, size=[2, 1, 3], scale=2, expand=2,
                                       spin=[0, 180, 0], end_position=[2, 3, 4])], [MESH])
        project = result["project"]
        mesh = project["nodes"][0]
        self.assertEqual(mesh["properties"]["MeshId"], MESH["mesh_id"])
        self.assertEqual(mesh["properties"]["TextureID"], MESH["mesh_texture_id"])
        self.assertEqual(mesh["properties"]["Size"], [4, 2, 6])
        self.assertEqual(result["bindings"][0]["preview"], "placeholder")
        self.assertTrue(any("géométrie absente" in warning for warning in result["warnings"]))
        for prop in ("Transparency", "Position"):
            self.assertTrue(next(track for track in project["animations"] if track["property"] == prop)["runtime"])
        transparency = next(track for track in project["animations"] if track["property"] == "Transparency")["keyframes"]
        self.assertEqual(transparency[0], {"time": 0, "value": 1})
        self.assertEqual(transparency[-1], {"time": 1, "value": 1})
        self.assertTrue(mesh_export_manifest(project)["exportable"])
        exported = export_rbxmx(project)
        self.assertIn(MESH["mesh_id"], exported)
        self.assertIn(MESH["mesh_texture_id"], exported)

    def test_local_geometry_survives_compile_merge_and_requires_native_mapping(self):
        geometry = import_obj("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n")["mesh"]
        local = {"key": "meshes:local-fixture", "collection": "meshes", "id": "local-fixture", "uri": "", "mesh_id": "", "name": "Local mesh"}
        result = compile_layers([layer("mesh", expand=1)], [local], {"assets": [local]}, geometry)
        ident = result["project"]["nodes"][0]["id"]
        self.assertEqual(result["project"]["editor"]["meshes"][ident], geometry)
        self.assertEqual(result["bindings"][0]["preview"], "geometry")
        self.assertFalse(mesh_export_manifest(result["project"])["exportable"])

    def test_planar_local_mesh_can_shrink_without_invalid_thickness(self):
        geometry = import_obj("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n")["mesh"]
        local = {"key": "meshes:local-fixture", "collection": "meshes", "id": "local-fixture", "uri": "", "mesh_id": "", "name": "Flat mesh"}
        result = compile_layers([layer("mesh", scale=.5, expand=.25)], [local], {"assets": [local]}, geometry)
        self.assertEqual(result["project"]["nodes"][0]["properties"]["Size"], [1, 1, .001])
        self.assertTrue(any("minimale" in warning for warning in result["warnings"]))

    def test_registered_obj_is_loaded_from_real_catalogue_without_inline_model_geometry(self):
        try:
            from .fx_ai_catalog import register_mesh, snapshot
        except ImportError:
            from fx_ai_catalog import register_mesh, snapshot
        imported = import_obj("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n", name="Fresh mesh.obj")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for filename in ("textures.json", "beams/assets.json", "meshes/assets.json"):
                target = root / filename; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("[]", encoding="utf-8")
            registered = register_mesh(imported, root=root, tags=["Slash"])
            catalog = snapshot(root=root)
            canonical = next(asset for asset in catalog["assets"] if asset["id"] == registered["id"])
            self.assertNotIn("preview_geometry", canonical)
            result = assets.compile_plan({"name": "Local", "blocks": [layer("mesh", expand=1)]}, [canonical], snapshot=catalog, root=root)
            self.assertTrue(result["project"]["editor"]["meshes"])
            self.assertEqual(result["bindings"][0]["preview"], "geometry")
            self.assertFalse(mesh_export_manifest(result["project"])["exportable"])

    def test_layer_parameter_types_bounds_and_fields_are_checked(self):
        for bad in (layer("mesh", duration=True), layer("mesh", size=[1, 0, 1]), layer("mesh", spin=[0, float("nan"), 0]),
                    layer("mesh", size=[2048, 1, 1], expand=2), layer("flash", script="print(1)")):
            with self.subTest(layer=bad), self.assertRaises((assets.AssetCompileError, ValueError)):
                compile_layers([bad], [MESH if bad["block"] == "mesh" else TEXTURE])

    def test_inputs_are_immutable_and_default_texture_is_labelled(self):
        plan = {"name": "Frost", "blocks": [layer("flash")]}
        before = deepcopy(plan), deepcopy(SNAPSHOT)
        result = assets.compile_plan(plan, [None], snapshot=SNAPSHOT)
        self.assertEqual(plan, before[0]); self.assertEqual(SNAPSHOT, before[1])
        self.assertEqual(result["bindings"][0]["selection"], "legacy_default")
        self.assertTrue(result["warnings"])

    @unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent")
    def test_compiled_mesh_plays_gates_moves_and_cleans_up_in_actual_luau_runtime(self):
        result = compile_layers([layer("mesh", duration=.6, size=[2, 1, 3], expand=2, end_position=[2, 3, 4])], [MESH])
        folder = Path(__file__).resolve().parent
        source = (folder / "luau_roblox_mock.luau").read_text(encoding="utf-8")
        source += "\nlocal FX = (function()\n" + (folder / "fx_kit.lua").read_text(encoding="utf-8") + "\nend)()\n"
        source += "local R = " + _lua(result["project"]) + "\n"
        source += '''
FX.preload(R)
local h = FX.play(R, CFrame.new(0,0,0))
local p = h:Part("ai1_mesh")
assert(p.MeshId == "rbxassetid://901234570", "catalogue MeshId must survive preload and clone")
assert(p.TextureID == "rbxassetid://901234571", "catalogue TextureID must reach native MeshPart")
Step(.2)
assert(p.Transparency == 1, "mesh must remain hidden before its layer")
Step(.4)
assert(p.Transparency < .1, "mesh must be visible in its layer")
assert(p.Position.X > 0 and p.Position.Y > 1, "mesh trajectory must play natively")
h:Stop()
assert(p.Parent == nil, "Stop must clean mesh instances")
print("CATALOG_MESH_OK")
'''
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "catalogue-mesh.luau"
            script.write_text(source, encoding="utf-8")
            completed = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("CATALOG_MESH_OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
