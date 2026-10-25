"""Public authoring helpers and transforms for compose includes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from . import fx_builder as B, fx_modules, fx_tools
    from .fx_schema import ValidationError, validate_project
except ImportError:
    import fx_builder as B
    import fx_modules
    import fx_tools
    from fx_schema import ValidationError, validate_project


class BuilderTests(unittest.TestCase):
    def make_piece(self):
        r = B.Recipe("Muzzle", 2)
        r.part("p", (1, 2, 3), (2, 4, 6), Orientation=[10, 20, 30])
        r.att("a", "p", (1, 0, 0), (0, 0, 90))
        r.att("b", "p", (0, 2, 0))
        r.em("e", "a", "rbxassetid://123", start=.2, count=7, Lifetime=B.NR(.2, .4),
             Speed=B.NR(5, 8), Acceleration=[0, -10, 0], Size=B.NS((0, .5, .1), (1, 0)),
             Color=B.CS((0, (1, .5, 0)), (1, (1, 0, 0))), Transparency=B.NS((0, 0), (1, 1)),
             **r.flip())
        r.trail("t", "p", "a", "b", Lifetime=.25)
        r.light("l", "a", .2, .2, (1, .5, 0), 10, 2)
        r.anim("p", "Position", [(0, (1, 2, 3)), (1, (3, 2, 3))])
        return r

    def near(self, actual, expected, places=7):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=places)

    def test_helpers_produce_portable_recipe_and_save(self):
        r = self.make_piece()
        self.assertEqual(B.NR(2), [2, 2])
        self.assertEqual(B.NR(2, 4), [2, 4])
        self.assertEqual(B.NS((0, 1), (1, 0))[0]["envelope"], 0)
        data = r.to_dict()
        self.assertEqual(validate_project(data), data)
        self.assertEqual(r.flip((3, 5))["FlipbookSizeY"], 5)
        with tempfile.TemporaryDirectory() as folder:
            target = r.save(Path(folder) / "nested" / "piece.json")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), data)
        with self.assertRaises(ValidationError):
            r.part("p")
        with self.assertRaises(ValidationError):
            r.flip(3)

    def test_merge_transforms_world_parts_local_attachments_dimensions_and_tracks(self):
        piece = self.make_piece()
        original = deepcopy(piece.d)
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "shot_", at=.4,
                                 position=[10, 0, 0], orientation=[0, 90, 0], scale=2)
        by_id = {n["id"]: n for n in merged["nodes"]}
        self.near(by_id["shot_p"]["properties"]["Position"], [16, 4, -2])
        self.near(by_id["shot_p"]["properties"]["Size"], [4, 8, 12])
        self.near(by_id["shot_a"]["properties"]["Position"], [2, 0, 0])
        self.near(by_id["shot_a"]["properties"]["Orientation"], [0, 0, 90])
        emitter = by_id["shot_e"]
        self.assertEqual(emitter["parent"], "shot_a")
        self.near(emitter["properties"]["Acceleration"], [0, -20, 0])
        self.assertEqual(emitter["properties"]["Speed"], [10, 16])
        self.assertEqual(emitter["properties"]["Size"][0], {"time": 0, "value": 1, "envelope": .2})
        self.assertEqual(emitter["properties"]["Color"], original["nodes"][3]["properties"]["Color"])
        self.assertEqual(emitter["properties"]["Lifetime"], [.2, .4])
        self.assertEqual(emitter["timing"]["count"], 7)
        self.assertAlmostEqual(emitter["timing"]["start"], .6)
        self.assertEqual(by_id["shot_t"]["properties"]["Attachment0"], "shot_a")
        self.assertEqual(by_id["shot_t"]["properties"]["Attachment1"], "shot_b")
        self.assertEqual(by_id["shot_l"]["properties"]["Range"], 20)
        track = next(t for t in merged["animations"] if t["node"] == "shot_p")
        self.assertEqual(track["keyframes"][0]["time"], .4)
        self.near(track["keyframes"][1]["value"], [16, 4, -6])
        self.assertEqual(merged["duration"], 2.4)
        self.assertEqual(piece.d, original, "source was not mutated")

    def test_yxz_composition_matches_matrix_including_gimbal_lock(self):
        for original in ([10, 20, 30], [90, 0, 0], [-90, 15, 20], [40, 150, -70]):
            for rotation in ([0, 90, 0], [20, 30, 40], [0, 0, 0]):
                piece = B.Recipe("Angles", 1)
                piece.part("p", Orientation=original)
                merged = B.merge_recipes(B.Recipe("Full", 1), piece, "x_", orientation=rotation)
                actual = B._rotation(merged["nodes"][0]["properties"]["Orientation"])
                expected = B._matmul(B._rotation(rotation), B._rotation(original))
                for a, b in zip(actual, expected):
                    self.near(a, b)

    def test_parts_in_models_remain_world_space_and_attachments_remain_local(self):
        piece = B.Recipe("Tree", 1)
        piece.d["nodes"].append({"id": "model", "class": "Model", "properties": {}})
        piece.part("p", [1, 0, 0], parent="model")
        piece.att("a", "p", [1, 0, 0])
        piece.anim("a", "Position", [(0, [1, 0, 0]), (1, [2, 0, 0])])
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "tree_", position=[10, 0, 0], orientation=[0, 90, 0], scale=2)
        by_id = {n["id"]: n for n in merged["nodes"]}
        self.near(by_id["tree_p"]["properties"]["Position"], [10, 0, -2])
        self.near(by_id["tree_a"]["properties"]["Position"], [2, 0, 0])
        self.near(merged["animations"][0]["keyframes"][1]["value"], [4, 0, 0])

    def test_scaling_materializes_dimensions_and_transforms_animated_acceleration(self):
        piece = B.Recipe("Defaults", 1)
        piece.d["nodes"] = [{"id": "p", "class": "Part", "properties": {}},
                            {"id": "e", "class": "ParticleEmitter", "parent": "p", "properties": {}}]
        piece.anim("e", "Acceleration", [(0, [1, 0, 0]), (1, [0, 0, -2])])
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "x_", scale=2, orientation=[0, 90, 0])
        by_id = {n["id"]: n for n in merged["nodes"]}
        self.near(by_id["x_p"]["properties"]["Size"], [8, 2, 4])
        self.assertEqual(by_id["x_e"]["properties"]["Speed"], [10, 10])
        self.assertEqual(by_id["x_e"]["properties"]["Size"][0]["value"], 2)
        self.near(merged["animations"][0]["keyframes"][0]["value"], [0, 0, -2])
        self.near(merged["animations"][0]["keyframes"][1]["value"], [-4, 0, 0])

    def test_orientation_tracks_unwrap_without_changing_key_rotations(self):
        piece = B.Recipe("Turn", 1)
        piece.part("p")
        piece.anim("p", "Orientation", [(0, [0, 80, 0]), (1, [0, 100, 0])])
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "x_", orientation=[0, 90, 0])
        keys = merged["animations"][0]["keyframes"]
        self.assertAlmostEqual(keys[1]["value"][1] - keys[0]["value"][1], 20)
        for key, source in zip(keys, piece.d["animations"][0]["keyframes"]):
            actual = B._rotation(key["value"])
            expected = B._matmul(B._rotation([0, 90, 0]), B._rotation(source["value"]))
            for a, b in zip(actual, expected):
                self.near(a, b)

    def test_merge_namespaces_parameters_and_markers(self):
        piece = B.Recipe("Ring", 1)
        piece.d["params"] = {"radius": {"default": 16}}
        piece.part("p")
        piece.em("e", "p", "", Size=B.NS((0, 1), (1, 0)), scaleWith={"Size": "radius"})
        full = B.Recipe("Full", 1).merge(piece, "a_").merge(piece, "b_", dt=1)
        self.assertEqual(set(full.d["params"]), {"a_radius", "b_radius"})
        self.assertEqual(next(n for n in full.d["nodes"] if n["id"] == "b_e")["scaleWith"], {"Size": "b_radius"})
        with self.assertRaises(ValidationError):
            full.merge(piece, "a_")

    def test_merge_preserves_explicit_runtime_flags(self):
        piece = self.make_piece().to_dict()
        piece["animations"][0]["runtime"] = False
        piece["animations"][-1]["runtime"] = True
        original = deepcopy(piece)
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "run_", at=.2,
                                 position_keys=[(0, [0, 0, 0]), (1, [0, 0, -5])])
        self.assertIs(merged["animations"][0]["runtime"], False)
        self.assertIs(merged["animations"][-1]["runtime"], True)
        self.assertEqual(piece, original)

    def test_optional_translation_path_combines_with_existing_part_motion(self):
        piece = self.make_piece()
        merged = B.merge_recipes(B.Recipe("Full", 1), piece, "fly_", at=.25, position=[10, 0, 0],
                                orientation=[0, 90, 0], scale=2,
                                position_keys=[(0, [0, 0, 0]), (.5, [0, 0, -5]), (1, [0, 0, -10])])
        track = next(t for t in merged["animations"] if t["node"] == "fly_p" and t["property"] == "Position")
        self.assertEqual([k["time"] for k in track["keyframes"]], [.25, .75, 1.25])
        self.near(track["keyframes"][1]["value"], [16, 4, -9])
        self.near(track["keyframes"][2]["value"], [16, 4, -16])
        for bad in (-1, 0, float("nan")):
            with self.assertRaises(ValidationError):
                B.merge_recipes(B.Recipe("Full", 1), piece, "bad_", scale=bad)

    def test_compose_includes_with_injectable_loader_and_unique_prefixes(self):
        piece = self.make_piece().to_dict()
        calls = []
        def loader(name):
            calls.append(name)
            return piece
        result = fx_modules.compose({"name": "Full", "blocks": [
            {"include": "A1_Muzzle", "at": .44, "position": [0, 0, -4], "orientation": [0, 90, 0], "scale": 2},
            {"block": "flash", "at": .8}, {"include": "A1_Muzzle", "at": 1},
        ]}, include_loader=loader)
        self.assertEqual(calls, ["A1_Muzzle", "A1_Muzzle"])
        self.assertEqual(len({n["id"] for n in result["nodes"]}), len(result["nodes"]))
        self.assertEqual(result["name"], "Full")
        self.assertGreaterEqual(result["duration"], 3)
        self.assertEqual(validate_project(result), result)

    def test_load_path_and_unique_short_name_and_compose_default_loader(self):
        piece = self.make_piece().to_dict()
        piece["name"] = "Unit · A1_Muzzle"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unit-muzzle.json"
            path.write_text(json.dumps(piece), encoding="utf-8")
            self.assertEqual(B.load_recipe(path), validate_project(piece))
            with mock.patch.object(fx_tools, "PROJECTS", Path(folder)):
                self.assertEqual(B.load_recipe("A1_Muzzle")["name"], piece["name"])
                self.assertEqual(B.load_recipe("unit-muzzle")["name"], piece["name"])
                result = fx_modules.compose({"blocks": [{"include": "A1_Muzzle"}]})
                self.assertEqual(len(result["nodes"]), len(piece["nodes"]))
            with self.assertRaises(ValidationError):
                B.load_recipe("definitely-absent")
        for plan in ({"blocks": [{"include": "x", "block": "flash"}]}, {"blocks": [{"include": "absent"}]}):
            with self.assertRaises(ValidationError):
                fx_modules.compose(plan)


if __name__ == "__main__":
    unittest.main()

