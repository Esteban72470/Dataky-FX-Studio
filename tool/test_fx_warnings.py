"""PNG alpha cache and advisory warnings, with synthetic image evidence."""
from copy import deepcopy
from collections import Counter
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from fx_texture_cache import png_pixels, frame_statistics, texture_stats
from fx_grid_overrides import confirm_grid, read_grid_overrides
from fx_warnings import validation_warnings, visible_area
from fx_schema import validate_project
from test_fx_server import project


def png(width, height, raw, color=6, depth=8, extra=()):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)) + b"".join(chunk(k, v) for k, v in extra) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class AlphaCacheTests(unittest.TestCase):
    def test_rgba_sub_up_average_paeth_and_palette_alpha(self):
        # Two identical red pixels: the second row's predictors are known.
        for filter_type, encoded in ((0, bytes([255, 0, 0, 128])), (2, bytes(4)),
                                     (3, bytes([128, 0, 0, 64])), (4, bytes(4))):
            image = png(1, 2, bytes([0, 255, 0, 0, 128, filter_type]) + encoded)
            self.assertEqual(png_pixels(image)[2], [(255, 0, 0, 128)] * 2)
        image = png(2, 1, bytes([1, 255, 0, 0, 128, 0, 0, 0, 0]))
        self.assertEqual(png_pixels(image)[2], [(255, 0, 0, 128)] * 2)
        palette = png(2, 1, b"\x00\x40", color=3, depth=1,
                      extra=((b"PLTE", bytes([0, 0, 0, 255, 255, 255])), (b"tRNS", b"\x00\xff")))
        self.assertEqual(png_pixels(palette)[2], [(0, 0, 0, 0), (255, 255, 255, 255)])
        gray16 = png(1, 1, b"\x00\xff\xff\x80\x00", color=4, depth=16)
        self.assertEqual(png_pixels(gray16)[2], [(255, 255, 255, 127)])

    def test_grid_statistics_and_cache_invalidation_leave_image_untouched(self):
        image = png(2, 2, bytes([0, 255, 255, 255, 0, 255, 255, 255, 255] * 2))
        stats = frame_statistics(image, 2)
        self.assertEqual([f["alpha_mean"] for f in stats["frames"]], [0, 1, 0, 1])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "images").mkdir()
            path, cache = root / "images/123.png", root / "tool/cache.json"
            path.write_bytes(image)
            first = texture_stats("123", 2, root=root, cache_path=cache)
            before = cache.read_bytes()
            self.assertEqual(texture_stats("123", 2, root=root, cache_path=cache), first)
            self.assertEqual(cache.read_bytes(), before)
            self.assertEqual(path.read_bytes(), image)
            replacement = png(2, 2, bytes([0, 255, 255, 255, 255, 255, 255, 255, 255] * 2))
            path.write_bytes(replacement)
            second = texture_stats("123", 2, root=root, cache_path=cache)
            self.assertNotEqual(second["sha256"], first["sha256"])
            self.assertEqual(second["frames"][0]["alpha_mean"], 1)
            self.assertEqual(json.loads(cache.read_text())["version"], 1)
            self.assertIsNone(texture_stats("../123", root=root, cache_path=cache))

    def test_malformed_cache_shapes_and_invalid_frame_values_are_recomputed(self):
        image = png(1, 1, bytes([0, 255, 255, 255, 128]))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "images").mkdir()
            (root / "images/123.png").write_bytes(image)
            cache = root / "cache.json"
            expected = texture_stats("123", root=root, cache_path=cache)
            invalid_entries = [None, "bad entry", [], {}, {**expected, "frames": []},
                               {**expected, "frames": [None]}, {**expected, "width": 0},
                               {**expected, "columns": 2}, {**expected, "height": True}]
            for field in ("alpha_mean", "coverage", "luma_alpha_mean"):
                for invalid in (None, True, "0.5", -0.1, 1.1, float("nan"), float("inf")):
                    entry = deepcopy(expected)
                    entry["frames"][0][field] = invalid
                    invalid_entries.append(entry)
            malformed_caches = [[], None, "cache", {"version": 1, "items": []}]
            malformed_caches += [{"version": 1, "items": {"123:1x1": entry}} for entry in invalid_entries]
            for malformed in malformed_caches:
                with self.subTest(cache=malformed):
                    cache.write_text(json.dumps(malformed), encoding="utf-8")
                    self.assertEqual(texture_stats("123", root=root, cache_path=cache), expected)
                    self.assertEqual(json.loads(cache.read_text())["items"]["123:1x1"], expected)
            self.assertEqual((root / "images/123.png").read_bytes(), image)


class WarningTests(unittest.TestCase):
    def test_cli_advisories_work_with_a_windows_legacy_console_encoding(self):
        data = project()
        data["nodes"][-1]["properties"].update(LightEmission=1, Color=[[0, [1, 0, 1]], [1, [1, 0, 1]]])
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "warning.json"
            file.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("fx.py")), "validate", str(file)],
                                    env={**os.environ, "PYTHONIOENCODING": "cp1252"}, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("cp1252"))
        self.assertIn(b"[additive_white]", result.stdout)

    def test_all_requested_traps_are_advisory_and_do_not_change_recipe(self):
        data = project()
        data["nodes"][-1]["properties"].update(
            Texture="rbxassetid://123", Orientation="VelocityParallel", Squash=[[0, 2], [1, 1]],
            LightEmission=.8, Color=[[0, [1, 0, 1]], [1, [1, 1, 0]]],
            Size=[[0, 1], [1, 1]], Transparency=[[0, 0], [1, 0]],
            FlipbookLayout="Grid4x4", FlipbookMode="OneShot", Lifetime=[.2, .45])
        data = validate_project(data)
        before = deepcopy(data)
        stats = {"frames": [{"alpha_mean": .01, "coverage": .03}] * 16}
        calls = []
        def loader(*args):
            calls.append(args)
            return stats
        warnings = validation_warnings(data, assets={"123": {"grid_source": "inferred_alpha"}}, stats_loader=loader, include_infos=True, grid_overrides={})
        self.assertEqual({w["code"] for w in warnings}, {"positive_parallel_squash", "abrupt_transparency", "additive_white", "estimated_grid", "flipbook_low_opacity", "flipbook_empty_start"})
        end_warning = next(w for w in warnings if w["code"] == "abrupt_transparency")
        self.assertTrue(end_warning["abrupt_size"])
        self.assertEqual(end_warning["end_size"], 1)
        self.assertEqual(calls, [("123", 4, 4)])
        self.assertEqual(data, before)
        self.assertEqual(validate_project(data), data)

    def test_sensible_recipe_has_no_static_trap_warnings_and_missing_image_is_ok(self):
        data = validate_project(project())
        data["nodes"][-1]["properties"]["Transparency"] = [{"time": 0, "value": 0, "envelope": 0}, {"time": 1, "value": 1, "envelope": 0}]
        self.assertEqual(validation_warnings(data, assets={}, stats_loader=lambda *args: None), [])

    def test_custom_flipbook_uses_explicit_columns_and_rows(self):
        data = validate_project(project())
        data["nodes"][-1]["properties"].update(FlipbookLayout="Custom", FlipbookSizeX=3.0, FlipbookSizeY=5)
        calls = []
        def loader(*args):
            calls.append(args)
            return None
        validation_warnings(data, assets={"123": {"grid": 4}}, stats_loader=loader)
        self.assertEqual(calls, [("123", 3, 5)])

    def test_measured_flame_thumbnail_empty_start_is_detected_without_id_special_case(self):
        cache = Path(__file__).with_name("texture_frames.json")
        if not cache.is_file():
            self.skipTest("cache de la miniature mesurée absent")
        stats = json.loads(cache.read_text())["items"].get("70418763522849:4x4")
        if not stats:
            self.skipTest("texture mesurée absente du cache")
        data = validate_project(project())
        data["nodes"][-1]["properties"].update(Texture="rbxassetid://999", FlipbookLayout="Grid4x4", FlipbookMode="OneShot", Lifetime=[.2, .45])
        warnings = validation_warnings(data, assets={}, stats_loader=lambda *args: stats)
        self.assertIn("flipbook_empty_start", {w["code"] for w in warnings})

    def test_end_opacity_threshold_and_residual_size_share_one_diagnostic(self):
        for opacity in (.949, .95, .99, 1):
            with self.subTest(transparency=opacity):
                data = validate_project(project())
                data["nodes"][-1]["properties"].update(
                    Size=[[0, 2], [1, 2]], Transparency=[[0, 0], [1, opacity]])
                warnings = validation_warnings(data, assets={}, stats_loader=lambda *args: None)
                self.assertEqual([w["code"] for w in warnings], ["abrupt_transparency"] if opacity < .95 else [])
                if warnings:
                    self.assertTrue(warnings[0]["abrupt_size"])
                    self.assertEqual(warnings[0]["end_size"], 2)

    def test_visible_area_integrates_size_and_opacity_instead_of_midlife_sampling(self):
        # Integral 0..1 of .5 * (2t)^2 * (1-t) = 1/6.
        self.assertAlmostEqual(visible_area([{"alpha_mean": .5}], [[0, 0], [1, 2]], [[0, 0], [1, 1]]), 1 / 6)
        # OneShot cell boundaries matter: alpha=1 until t=.5, then alpha=0.
        self.assertAlmostEqual(visible_area([{"alpha_mean": 1}, {"alpha_mean": 0}], [[0, 0], [1, 1]], [[0, 0], [1, 0]], one_shot=True), 1 / 24)
        # A quarter of hard opaque pixels in a size=2 quad is one opaque stud²,
        # without multiplying a second time by coverage.
        self.assertEqual(visible_area([{"alpha_mean": .25, "coverage": .25}], [[0, 2], [1, 2]], [[0, 0], [1, 0]]), 1)

    def test_same_sparse_texture_is_quiet_when_large_and_warns_when_tiny(self):
        data = validate_project(project())
        props = data["nodes"][-1]["properties"]
        props.update(Size=[[0, .2], [1, .2]], Transparency=[[0, 0], [1, 1]])
        stats = {"frames": [{"alpha_mean": .1, "coverage": .1}]}
        warnings = validation_warnings(data, assets={}, stats_loader=lambda *args: stats)
        self.assertEqual([w["code"] for w in warnings], ["pale_small_texture"])
        props["Size"] = [[0, 3], [1, 3]]
        self.assertEqual(validation_warnings(data, assets={}, stats_loader=lambda *args: stats), [])

    def test_estimated_grids_are_optional_infos_deduplicated_per_texture(self):
        data = validate_project(project())
        data["nodes"][-1]["properties"].update(FlipbookLayout="Grid4x4", Transparency=[[0, 0], [1, 1]])
        second = deepcopy(data["nodes"][-1])
        second["id"] = "second"
        data["nodes"].append(second)
        options = {"assets": {"123": {"grid_source": "inferred_alpha"}}, "stats_loader": lambda *args: None, "grid_overrides": {}}
        self.assertEqual(validation_warnings(data, **options), [])
        infos = validation_warnings(data, include_infos=True, **options)
        self.assertEqual([(w["code"], w["level"], w["texture"]) for w in infos], [("estimated_grid", "info", "123")])
        options["grid_overrides"] = {"123": 4}
        self.assertEqual(validation_warnings(data, include_infos=True, **options), [])
        options["grid_overrides"] = {"123": 8}
        self.assertEqual(len(validation_warnings(data, include_infos=True, **options)), 1)


class GridOverrideTests(unittest.TestCase):
    def test_confirmation_preserves_other_ids_and_does_not_mutate_recipe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_overrides.json"
            self.assertEqual(read_grid_overrides(path), {})
            result = confirm_grid("123", 4, path=path)
            self.assertEqual(result, {"texture": "123", "grid": 4, "confirmed": True, "path": str(path)})
            confirm_grid(456, 8, path=path)
            self.assertEqual(read_grid_overrides(path), {"123": 4, "456": 8})
            data = validate_project(project())
            data["nodes"][-1]["properties"].update(FlipbookLayout="Grid4x4", Transparency=[[0, 0], [1, 1]])
            before = deepcopy(data)
            with patch("fx_grid_overrides.DEFAULT_PATH", path):
                self.assertEqual(validation_warnings(data, assets={"123": {"grid_source": "inferred_alpha"}}, stats_loader=lambda *args: None, include_infos=True), [])
            self.assertEqual(data, before)

    def test_manual_confirmation_file_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_overrides.json"
            path.write_text(json.dumps({"version": 1, "grids": {"123": 4}}), encoding="utf-8-sig")
            self.assertEqual(read_grid_overrides(path), {"123": 4})

    def test_invalid_confirmation_inputs_and_files_are_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_overrides.json"
            confirm_grid("123", 4, path=path)
            before = path.read_bytes()
            for asset_id, grid in (("../123", 4), (True, 4), ("0", 4), ("123", True), ("123", 3), ("123", 4.0)):
                with self.subTest(asset_id=asset_id, grid=grid), self.assertRaises(ValueError):
                    confirm_grid(asset_id, grid, path=path)
                self.assertEqual(path.read_bytes(), before)
            for invalid in ([], None, {"version": True, "grids": {}}, {"version": 2, "grids": {}},
                            {"version": 1, "grids": []}, {"version": 1, "grids": {"123": 3}},
                            {"version": 1, "grids": {"../123": 4}}):
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    read_grid_overrides(path)
            with patch("fx_grid_overrides.DEFAULT_PATH", path):
                data = validate_project(project())
                data["nodes"][-1]["properties"]["Transparency"] = [[0, 0], [1, 1]]
                self.assertEqual(validation_warnings(data, assets={}, stats_loader=lambda *args: None), [])
                infos = validation_warnings(data, assets={}, stats_loader=lambda *args: None, include_infos=True)
                self.assertEqual([(w["code"], w["level"]) for w in infos], [("grid_overrides_unavailable", "info")])


class BulbitoRegressionTests(unittest.TestCase):
    """Real immutable observations assert facts; production rules contain no IDs."""
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent / "fixtures/bulbito"
        cls.before = {p.name: p.read_bytes() for p in cls.root.glob("*.json")}
        cls.observations = json.loads(cls.before["play_observations.json"])
        cls.diagnostics = {}
        for name, content in cls.before.items():
            if name == "play_observations.json":
                continue
            data = validate_project(json.loads(content))
            cls.diagnostics[Path(name).stem] = validation_warnings(data, include_infos=True, grid_overrides={})

    @classmethod
    def tearDownClass(cls):
        for name, content in cls.before.items():
            if (cls.root / name).read_bytes() != content:
                raise AssertionError("Fixture modified: " + name)

    def test_observed_visible_emitters_have_no_visibility_warning(self):
        codes = self.observations["visibility_codes"]
        for name, nodes in self.observations["visible"].items():
            for node in nodes:
                with self.subTest(fixture=name, node=node):
                    self.assertEqual([w for w in self.diagnostics[name] if w["node"] == node and w["code"] in codes], [])

    def test_observed_invisible_pillar_keeps_empty_start(self):
        self.assertIn("flipbook_empty_start", [w["code"] for w in self.diagnostics["Pillar_InvisibleInPlay"] if w["node"] == "Burst"])

    def test_end_of_life_and_info_counts_and_deduplication(self):
        warnings = [w for name, entries in self.diagnostics.items() if name != "Pillar_InvisibleInPlay" for w in entries if w["level"] != "info"]
        counts = Counter(w["code"] for w in warnings)
        self.assertEqual(counts["abrupt_size"], 0)
        # Lot 3: Ting/Stars/Star shrink to zero, so only residual-size ends warn.
        self.assertEqual(counts["abrupt_transparency"], 2)
        self.assertEqual(counts["additive_white"], 1)
        for name, node, size in (("A1_Tracer", "Glow", .2), ("A3_Fuse", "Spark", .6)):
            warning = next(w for w in self.diagnostics[name] if w["node"] == node and w["code"] == "abrupt_transparency")
            self.assertTrue(warning["abrupt_size"])
            self.assertEqual(warning["end_size"], size)
        for entries in self.diagnostics.values():
            infos = [w for w in entries if w["code"] == "estimated_grid"]
            self.assertEqual(len(infos), len({w["texture"] for w in infos}))
            self.assertTrue(all(w["level"] == "info" for w in infos))

    def test_unknown_observations_remain_explicitly_unverified(self):
        codes = self.observations["visibility_codes"]
        expected = {("A1_Muzzle", "Flash"): ["flipbook_empty_start"],
                    ("A3_Glint", "Shine"): ["flipbook_empty_start"], ("Idle_Puff", "Wisp"): []}
        for (name, node), result in expected.items():
            self.assertEqual([w["code"] for w in self.diagnostics[name] if w["node"] == node and w["code"] in codes], result)


class BlueberrinniRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent / "fixtures/blueberrinni"
        cls.before = {p.name: p.read_bytes() for p in cls.root.glob("*.json")}

    @classmethod
    def tearDownClass(cls):
        for name, content in cls.before.items():
            if (cls.root / name).read_bytes() != content:
                raise AssertionError("Fixture modified: " + name)

    def recipe(self, name):
        return validate_project(json.loads(self.before[name + ".json"]))

    def warnings(self, data, code):
        return [w for w in validation_warnings(data, assets={}, stats_loader=lambda *args: None) if w["code"] == code]

    def test_size_fading_to_zero_does_not_need_transparency_to_reach_one(self):
        data = validate_project(project())
        props = data["nodes"][-1]["properties"]
        for final in (0, .001, .049):
            props.update(Size=[[0, .34], [1, final]], Transparency=[[0, 0], [1, .4]])
            self.assertEqual(self.warnings(data, "abrupt_transparency"), [])
        props["Size"] = [[0, .34], [1, .1]]
        self.assertEqual(len(self.warnings(data, "abrupt_transparency")), 1)

    def test_flat_negative_zoffset_matches_measured_ground_layers_only(self):
        bad = self.recipe("Splat_NegativeZOffset")
        self.assertEqual({w["node"] for w in self.warnings(bad, "flat_layer_negative_zoffset")}, {"splat", "ripple"})
        self.assertEqual(self.warnings(self.recipe("A1_Splat"), "flat_layer_negative_zoffset"), [])
        layer = next(n for n in bad["nodes"] if n["id"] == "splat")
        layer["properties"]["Orientation"] = "FacingCamera"
        self.assertNotIn("splat", [w["node"] for w in self.warnings(bad, "flat_layer_negative_zoffset")])
        layer["properties"]["Orientation"] = "VelocityPerpendicular"
        layer["properties"]["EmissionDirection"] = "Front"
        self.assertNotIn("splat", [w["node"] for w in self.warnings(bad, "flat_layer_negative_zoffset")])

    def test_dark_only_swirl_is_reported_and_concurrent_light_swirl_covers_it(self):
        self.assertEqual([w["node"] for w in self.warnings(self.recipe("Gather_DarkInkOnly"), "dark_ground_contrast")], ["swirl"])
        self.assertEqual(self.warnings(self.recipe("A2_Gather"), "dark_ground_contrast"), [])

    def test_dark_contrast_ignores_disabled_empty_or_invisible_bright_layers(self):
        for change in ({"Enabled": False}, {"Transparency": [[0, 1], [1, 1]]}, {"Size": [[0, 0], [1, 0]]}, {"LightEmission": .19}):
            data = self.recipe("A2_Gather")
            layer = next(n for n in data["nodes"] if n["id"] == "swirlLight")
            layer["properties"].update(change)
            self.assertIn("swirl", [w["node"] for w in self.warnings(data, "dark_ground_contrast")], change)
        data = self.recipe("A2_Gather")
        next(n for n in data["nodes"] if n["id"] == "swirlLight")["timing"]["count"] = 0
        self.assertIn("swirl", [w["node"] for w in self.warnings(data, "dark_ground_contrast")])

    def test_light_must_cover_presence_including_lifetime_not_merely_overlap(self):
        for start, lifetime in ((.1, .48), (0, .1), (.5, .48)):
            data = self.recipe("A2_Gather")
            layer = next(n for n in data["nodes"] if n["id"] == "swirlLight")
            layer["timing"]["start"] = start
            layer["properties"]["Lifetime"] = [lifetime, lifetime]
            self.assertIn("swirl", [w["node"] for w in self.warnings(data, "dark_ground_contrast")])
        data = self.recipe("A2_Gather")
        next(n for n in data["nodes"] if n["id"] == "swirlLight")["properties"]["TimeScale"] = .5
        self.assertEqual(self.warnings(data, "dark_ground_contrast"), [])

    def test_continuous_rate_and_enabled_animation_affect_covering_windows(self):
        data = self.recipe("A2_Gather")
        light = next(n for n in data["nodes"] if n["id"] == "swirlLight")
        light["timing"].update(mode="continuous", duration=.48)
        light["properties"]["Rate"] = 0
        self.assertIn("swirl", [w["node"] for w in self.warnings(data, "dark_ground_contrast")])
        light["properties"]["Rate"] = 30
        self.assertEqual(self.warnings(data, "dark_ground_contrast"), [])
        data["animations"] = [{"node": "swirlLight", "property": "Enabled", "keyframes": [{"time": 0, "value": False}, {"time": .2, "value": True}]}]
        self.assertIn("swirl", [w["node"] for w in self.warnings(data, "dark_ground_contrast")])

    def test_dark_disabled_or_fully_transparent_layer_is_quiet(self):
        for change in ({"Enabled": False}, {"Transparency": [[0, 1], [1, 1]]}):
            data = self.recipe("Gather_DarkInkOnly")
            next(n for n in data["nodes"] if n["id"] == "swirl")["properties"].update(change)
            self.assertEqual(self.warnings(data, "dark_ground_contrast"), [])


if __name__ == "__main__":
    unittest.main()
