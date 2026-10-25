"""Procedural trajectory, authoring validation and real export integration tests."""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

try:
    from .fx_motion import bake_motion, motion_schema
    from .fx_schema import ValidationError, validate_project
    from .fx_export import export_project, export_library
    from .fx_rbxmx import export_rbxmx
except ImportError:
    from fx_motion import bake_motion, motion_schema
    from fx_schema import ValidationError, validate_project
    from fx_export import export_project, export_library
    from fx_rbxmx import export_rbxmx


def recipe():
    return {"version": 1, "name": "Motion", "duration": 2, "nodes": [
        {"id": "root", "class": "Part", "properties": {"Position": [10, 3, 0], "Size": [2, 4, 6], "Transparency": 0}},
        {"id": "tip", "class": "Attachment", "parent": "root", "properties": {"Position": [1, 0, 0]}},
        {"id": "mesh", "class": "SpecialMesh", "parent": "root", "properties": {"MeshType": "Sphere"}},
        {"id": "light", "class": "PointLight", "parent": "root", "properties": {"Brightness": 3}},
    ], "animations": []}


class MotionTests(unittest.TestCase):
    def motion(self, kind, **spec):
        return bake_motion(recipe(), {"node": "tip", "type": kind, **spec})["animations"][0]

    def near(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=8)

    def test_cubic_bezier_uses_actual_control_points_and_exact_endpoints(self):
        track = self.motion("bezier", points=[[0, 0, 0], [0, 4, 2], [4, 4, 2], [4, 0, 0]], samples=3)
        self.assertEqual([f["time"] for f in track["keyframes"]], [0, 1, 2])
        self.near(track["keyframes"][0]["value"], [0, 0, 0])
        self.near(track["keyframes"][1]["value"], [2, 3, 1.5])
        self.near(track["keyframes"][-1]["value"], [4, 0, 0])
        self.assertNotIn("runtime", track, "Attachment Position retains local semantics")

    def test_arc_adds_signed_peak_to_interpolated_path_in_a_subinterval(self):
        track = self.motion("arc", **{"from": [1, 2, 3], "to": [9, 4, 7], "height": -3,
                                     "axis": "z", "start": .25, "duration": 1.5, "samples": 3})
        self.assertEqual([f["time"] for f in track["keyframes"]], [.25, 1, 1.75])
        self.near(track["keyframes"][1]["value"], [5, 3, 2])

    def test_orbit_and_helix_have_right_handed_planes_and_radial_growth(self):
        for axis, quarter in (("x", [0, 0, 2]), ("y", [0, 0, -2]), ("z", [0, 2, 0])):
            track = self.motion("orbit", center=[0, 0, 0], axis=axis, radius=2, turns=1, samples=5)
            self.near(track["keyframes"][1]["value"], quarter)
            self.near(track["keyframes"][0]["value"], track["keyframes"][-1]["value"])
        track = self.motion("spiral", center=[0, 0, 0], radius=1, end_radius=3, turns=2,
                            height=5, start_angle=90, samples=9)
        self.near(track["keyframes"][0]["value"], [0, 0, -1])
        self.near(track["keyframes"][-1]["value"], [0, 5, -3])

    def test_easing_changes_progress_preserves_endpoints_and_allows_back_overshoot(self):
        values = {}
        for easing in ("linear", "in", "out", "inOut", "backOut"):
            track = self.motion("tween", property="Position", **{"from": [0, 0, 0], "to": [1, 0, 0],
                                                                "samples": 5, "easing": easing})
            self.near(track["keyframes"][0]["value"], [0, 0, 0])
            self.near(track["keyframes"][-1]["value"], [1, 0, 0])
            values[easing] = [f["value"][0] for f in track["keyframes"]]
        self.assertLess(values["in"][1], values["linear"][1])
        self.assertGreater(values["out"][1], values["linear"][1])
        self.assertLess(values["inOut"][1], .25)
        self.assertGreater(max(values["backOut"]), 1)

    def test_bounded_transparency_and_colors_keep_valid_native_values(self):
        result = bake_motion(recipe(), [
            {"node": "root", "type": "tween", "property": "Transparency", "from": 0, "to": 1, "easing": "backOut"},
            {"node": "root", "type": "tween", "property": "Color", "from": [0, 0, 0], "to": [1, .5, .25], "easing": "backOut"},
        ])
        self.assertTrue(result["animations"][0]["runtime"])
        self.assertTrue(all(0 <= frame["value"] <= 1 for frame in result["animations"][0]["keyframes"]))
        self.assertTrue(all(0 <= c <= 1 for frame in result["animations"][1]["keyframes"] for c in frame["value"]))
        with self.assertRaisesRegex(ValidationError, "maximum 1"):
            bake_motion(recipe(), {"node": "root", "type": "tween", "property": "Transparency", "to": 2})

    def test_oscillation_supports_vector_and_scalar_with_phase_and_damping(self):
        track = self.motion("oscillation", amplitude=[0, 2, 0], offset=[1, 0, 0], cycles=1, samples=5)
        self.near(track["keyframes"][1]["value"], [1, 2, 0])
        self.near(track["keyframes"][3]["value"], [1, -2, 0])
        result = bake_motion(recipe(), {"node": "light", "type": "oscillation", "property": "Brightness",
                                       "offset": 3, "amplitude": 2, "cycles": 1, "phase": 90, "decay": 2, "samples": 5})
        frames = result["animations"][0]["keyframes"]
        self.assertAlmostEqual(frames[0]["value"], 5)
        self.assertAlmostEqual(frames[-1]["value"], 3 + 2 * math.exp(-2))

    def test_unwrapped_spin_and_volume_preserving_squash(self):
        spin = self.motion("spin", degrees=720, axis="z", samples=3)
        self.near(spin["keyframes"][1]["value"], [0, 0, 360])
        self.near(spin["keyframes"][-1]["value"], [0, 0, 720])
        result = bake_motion(recipe(), {"node": "root", "type": "squash", "amount": .5, "samples": 3})
        frames = result["animations"][0]["keyframes"]
        self.near(frames[0]["value"], [2, 4, 6])
        self.near(frames[-1]["value"], [2, 4, 6])
        self.assertAlmostEqual(frames[1]["value"][1], 2)
        for frame in frames:
            self.assertAlmostEqual(math.prod(frame["value"]), 48)
        mesh = bake_motion(recipe(), {"node": "mesh", "type": "squash", "samples": 3})
        self.assertEqual(mesh["animations"][0]["property"], "Scale")

    def test_no_mutation_atomic_batch_and_explicit_track_replacement(self):
        source = recipe()
        snapshot = deepcopy(source)
        specs = [{"node": "root", "type": "arc", "to": [3, 4, 5], "samples": 2},
                 {"node": "root", "type": "spin", "degrees": 180, "samples": 2}]
        original_specs = deepcopy(specs)
        result = bake_motion(source, specs)
        self.assertEqual(source, snapshot)
        self.assertEqual(specs, original_specs)
        self.assertEqual(validate_project(result), result)
        self.assertEqual(len(result["animations"]), 2)
        self.assertTrue(result["animations"][0]["runtime"])
        with self.assertRaisesRegex(ValidationError, "replace:true"):
            bake_motion(result, specs[0])
        result["editor"] = {"version": 1, "curves": {"root::Position": {"obsolete": True}, "root::Orientation": {"other": True}}}
        replaced = bake_motion(result, {**specs[0], "replace": True})
        self.assertNotIn("root::Position", replaced["editor"]["curves"])
        self.assertIn("root::Orientation", replaced["editor"]["curves"])
        with self.assertRaises(ValidationError):
            bake_motion(source, [specs[0], {"node": "missing", "type": "spin"}])
        self.assertEqual(source, snapshot, "a failing batch never leaves partial changes")

    def test_rejects_invalid_specs_with_actionable_field_errors(self):
        cases = [
            ({"type": "unknown"}, "type"), ({"node": "absent"}, "node"),
            ({"samples": 1}, "samples"), ({"samples": 242}, "samples"),
            ({"samples": True}, "samples"), ({"samples": 2.5}, "samples"),
            ({"easing": "magic"}, "easing"), ({"replace": "yes"}, "replace"),
            ({"axis": "q"}, "axis"), ({"start": -1}, "start"),
            ({"duration": 0}, "duration"), ({"start": 1, "duration": 2}, "duration"),
            ({"start": 2}, "duration"), ({"height": float("inf")}, "height"),
            ({"height": True}, "height"), ({"height": 1e100}, "height"),
            ({"to": [1, float("nan"), 2]}, "to"), ({"to": [1, 2]}, "to"),
            ({"property": "Size"}, "property"), ({"property": "Fake"}, "property"),
            ({"unexpected": 1}, "inconnu"),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValidationError, error):
                self.motion("arc", **{"to": [0, 0, 0], **changes})
        for invalid in ([], [None], "arc", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                bake_motion(recipe(), invalid)
        with self.assertRaisesRegex(ValidationError, "quatre"):
            self.motion("bezier", points=[[0, 0, 0]] * 3)
        with self.assertRaisesRegex(ValidationError, "numérique"):
            self.motion("tween", property="Visible", to=True)
        with self.assertRaisesRegex(ValidationError, "sans les combiner"):
            self.motion("spin", to=[0, 0, 0], degrees=360)
        with self.assertRaisesRegex(ValidationError, "maximum 2048"):
            bake_motion(recipe(), {"node": "root", "type": "squash", "from": [2, 3000, 1]})
        with self.assertRaisesRegex(ValidationError, "minimum 0"):
            bake_motion(recipe(), {"node": "light", "type": "oscillation", "property": "Brightness", "amplitude": 1, "offset": -2})

    def test_project_interval_limits_and_finest_sample_count(self):
        result = self.motion("arc", to=[3, 2, 1], start=.25, samples=241)
        self.assertEqual(len(result["keyframes"]), 241)
        self.assertEqual(result["keyframes"][-1]["time"], 2)
        self.assertTrue(all(a["time"] < b["time"] for a, b in zip(result["keyframes"], result["keyframes"][1:])))

    def test_exports_preserve_baked_keys_and_gameplay_opt_in(self):
        result = bake_motion(recipe(), {"node": "root", "type": "bezier", "samples": 9,
                                       "points": [[10, 3, 0], [12, 5, -2], [14, 5, -2], [16, 3, 0]]})
        for source in (export_project(result), export_library({"Shot": result})):
            self.assertIn('["runtime"]=true', source)
            self.assertIn('["property"]="Position"', source)
            self.assertIn('["value"]={16.0,3.0,0.0}', source)
        xml = ET.fromstring(export_rbxmx(result))
        self.assertEqual(xml.tag, "roblox")
        source = xml.find('.//ProtectedString[@name="Source"]').text
        self.assertIn('["runtime"]=true', source)
        self.assertIn('["value"]={16.0,3.0,0.0}', source)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_generated_motion_is_played_by_actual_browser_simulator(self):
        result = bake_motion(recipe(), [{"node": "root", "type": "arc", "to": [18, 3, 0], "height": 4, "samples": 5},
                                       {"node": "tip", "type": "spin", "axis": "y", "degrees": 360, "samples": 5}])
        script = "const E=require('./editor/emulator.js');let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const sim=E.createSimulation(JSON.parse(s));sim.seek(1);process.stdout.write(JSON.stringify(sim.frameOf(sim.byId.get('tip')).p));});"
        completed = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps(result),
                                   text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True, timeout=15)
        self.near(json.loads(completed.stdout), [15, 7, 0])

    def test_schema_is_json_portable_complete_and_independent(self):
        schema = motion_schema()
        self.assertEqual(json.loads(json.dumps(schema)), schema)
        self.assertTrue({"bezier", "arc", "orbit", "helix", "spiral", "oscillation", "spin", "squash", "tween"} <= schema["types"].keys())
        schema["types"]["arc"]["height"] = "modified"
        self.assertNotEqual(motion_schema()["types"]["arc"]["height"], "modified")


if __name__ == "__main__":
    unittest.main()
