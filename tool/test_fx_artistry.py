"""Evidence, iteration state, artistic plans and transactional authoring tests."""
from copy import deepcopy
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from . import fx_artistry as art, fx_tools
    from .fx_schema import ValidationError, validate_project
except ImportError:
    import fx_artistry as art
    import fx_tools
    from fx_schema import ValidationError, validate_project


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aFeQAAAAASUVORK5CYII=')


def recipe():
    return {"version": 1, "id": "art-test", "name": "Directional ink strike", "duration": 2,
            "camera": {"position": [12, 8, 14], "target": [0, 2, 0]}, "nodes": [
                {"id": "carrier", "class": "Part", "properties": {"Position": [0, 2, 0], "Transparency": 1}},
                {"id": "accent", "class": "ParticleEmitter", "parent": "carrier", "properties": {"Rate": 0},
                 "timing": {"start": .7, "duration": .1, "mode": "burst", "count": 80}},
                {"id": "core", "class": "ParticleEmitter", "parent": "carrier", "properties": {"Rate": 0},
                 "timing": {"start": .6, "duration": .1, "mode": "burst", "count": 80}},
                {"id": "light", "class": "PointLight", "parent": "carrier", "properties": {"Brightness": 8}},
            ], "animations": []}


def brief():
    return {"theme": "Calligraphic ink", "palette": [[.05, .1, .2], [.3, .7, 1]],
            "silhouette": "A narrow hooked slash", "motion": "Acceleration then a short recoil",
            "character": "A precise brush fighter", "readability": "Keep the centre open above the lane",
            "focal": [0, 2, 0], "power": 3, "layers": [
                {"id": "blade", "nodes": ["core"], "role": "primary", "phase": "release", "depth": "midground", "purpose": "Readable attack silhouette"},
                {"id": "ink", "nodes": ["accent"], "role": "accent", "phase": "secondary", "depth": "background", "purpose": "Show the direction after impact"},
            ]}


def observations(module=art):
    return {criterion: "Explicit test observation for " + criterion for criterion in module.CRITERIA}


def png_renderer(jobs):
    for job in jobs:
        target = Path(job["out"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PNG)
    return {"jobs": [{"files": [job["out"]]} for job in jobs], "browser_launches": 1}


class ArtistryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        root_patch = mock.patch.object(art, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.jobs = []
        def render(jobs):
            self.jobs.append(deepcopy(jobs))
            return png_renderer(jobs)
        renderer_patch = mock.patch.object(fx_tools, "render_batch", side_effect=render)
        renderer_patch.start()
        self.addCleanup(renderer_patch.stop)

    def session(self, **kwargs):
        return art.create_review(recipe(), art.create_plan(recipe(), brief()), **kwargs)

    def revise(self, session, project=None):
        captured = art.capture_review(session["id"], project)
        return art.submit_review(session["id"], attempt=len(captured["attempts"]), observer="human",
                                 decision="revise", observations=observations())

    def test_plan_persists_six_ordered_phases_layer_roles_and_independent_data(self):
        project, direction = recipe(), brief()
        original = deepcopy((project, direction))
        plan = art.save_plan(project, direction)
        self.assertEqual([phase["name"] for phase in plan["phases"]], list(art.PHASES))
        self.assertAlmostEqual(sum(p["duration"] for p in plan["phases"]), project["duration"])
        self.assertEqual(art.load_plan(plan["id"]), plan)
        self.assertEqual((project, direction), original)
        plan["layers"][0]["nodes"].append("carrier")
        self.assertEqual(art.load_plan(plan["id"])["layers"][0]["nodes"], ["core"])

    def test_plan_rejects_unknown_bindings_duplicate_layers_bad_palette_and_phase_overlap(self):
        base = art.create_plan(recipe(), brief())
        variants = []
        for mutator in (
            lambda b: b.update(palette=[[2, 0, 0], [0, 1, 0]]),
            lambda b: b["layers"][0].update(nodes=["missing"]),
            lambda b: b["layers"][1].update(nodes=["core"]),
            lambda b: b["layers"][1].update(id="blade"),
            lambda b: b["layers"][0].update(role="unimportant"),
            lambda b: b.update(budget={"untracked": 5}),
        ):
            value = brief()
            mutator(value)
            variants.append(value)
        phase_overlap = {**brief(), "phases": deepcopy(base["phases"])}
        phase_overlap["phases"][1]["start"] = 0
        variants.append(phase_overlap)
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                art.create_plan(recipe(), invalid)

    def test_inspection_reports_budget_and_layer_gaps_without_inventing_artistic_scores(self):
        plan = art.create_plan(recipe(), {**brief(), "budget": {"particles": 100}})
        plan["layers"] = []
        report = art.inspect(recipe(), plan)
        self.assertEqual(report["counts"]["particles"], 160)
        codes = {item["code"] for item in report["diagnostics"]}
        self.assertTrue({"budget_particles", "unassigned_layers", "missing_focal_layer"} <= codes)
        self.assertEqual(set(report["visual_review_required"]), set(art.CRITERIA))
        self.assertNotIn("score", report)
        self.assertIn("not peak", report["method"])

    def test_human_review_blocks_faked_vision_and_recapture_before_observations(self):
        session = self.session(vision=False)
        captured = art.capture_review(session["id"])
        self.assertEqual(captured["state"], "awaiting_human_review")
        with self.assertRaises(ValidationError):
            art.capture_review(session["id"])
        with self.assertRaisesRegex(ValidationError, "human"):
            art.submit_review(session["id"], attempt=1, observer="vision", decision="approve", observations=observations())
        self.assertIsNone(art.get_review(session["id"])["attempts"][0]["review"])

    def test_review_requires_exactly_nine_nonempty_criteria_and_latest_attempt(self):
        session = self.session(vision=True)
        art.capture_review(session["id"])
        for invalid in ({}, {**observations(), "score": "10"}, {**observations(), "depth": " "}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                art.submit_review(session["id"], attempt=1, observer="vision", decision="approve", observations=invalid)
        for invalid_attempt in (0, 2, True):
            with self.subTest(attempt=invalid_attempt), self.assertRaises(ValidationError):
                art.submit_review(session["id"], attempt=invalid_attempt, observer="vision", decision="approve", observations=observations())
        self.assertEqual(art.get_review(session["id"])["state"], "awaiting_vision_review")

    def test_attempt_limit_is_persisted_and_exhaustion_is_terminal(self):
        session = self.session(max_attempts=2)
        self.assertEqual(self.revise(session)["state"], "revise")
        changed = recipe()
        changed["nodes"][2]["timing"]["count"] = 40
        exhausted = self.revise(session, changed)
        self.assertEqual(exhausted["state"], "exhausted")
        self.assertEqual(len(art.get_review(session["id"])["attempts"]), 2)
        with self.assertRaises(ValidationError):
            art.capture_review(session["id"], recipe())
        for invalid in (0, 9, True):
            with self.subTest(max_attempts=invalid), self.assertRaises(ValidationError):
                self.session(max_attempts=invalid)

    def test_approval_requires_evidence_and_is_terminal(self):
        session = self.session(vision=True)
        with self.assertRaises(ValidationError):
            art.submit_review(session["id"], attempt=1, observer="vision", decision="approve", observations=observations())
        art.capture_review(session["id"])
        approved = art.submit_review(session["id"], attempt=1, observer="vision", decision="approve", observations=observations())
        self.assertEqual(approved["state"], "approved")
        self.assertEqual(approved["attempts"][0]["review"]["observations"], observations())
        with self.assertRaises(ValidationError):
            art.capture_review(session["id"])

    def test_captures_have_real_images_shared_comparison_camera_times_seed_and_backgrounds(self):
        session = self.session()
        captured = art.capture_review(session["id"])
        self.assertFalse(captured["attempts"][0]["comparison"])
        self.assertEqual(len(self.jobs[0]), 2)
        for image in captured["attempts"][0]["images"]:
            self.assertTrue(Path(image).read_bytes().startswith(b'\x89PNG'))
            self.assertTrue(Path(image).is_relative_to(self.root))
        art.submit_review(session["id"], attempt=1, observer="human", decision="revise", observations=observations())
        changed = recipe()
        changed["nodes"][2]["properties"]["Brightness"] = 2
        compared = art.capture_review(session["id"], changed)
        self.assertTrue(compared["attempts"][1]["comparison"])
        for old_job, new_job in zip(self.jobs[0], self.jobs[1]):
            self.assertEqual(new_job["backgrounds"], ["roblox", "dark"])
            self.assertEqual(new_job["seed"], 1)
            self.assertEqual(new_job["camera"], old_job["camera"])
            self.assertEqual(new_job["times"], old_job["times"])
            self.assertEqual(len(new_job["projects"]), 2)
            self.assertEqual(new_job["projects"][0], validate_project(recipe()))
            self.assertNotEqual(new_job["projects"][0], new_job["projects"][1])

    def test_cosmetic_changes_do_not_count_as_a_visual_correction(self):
        session = self.session()
        self.revise(session)
        changed = recipe()
        changed.update(id="different-id", name="A new title", editor={"version": 1, "curves": {}})
        changed["nodes"][0]["name"] = "Renamed carrier"
        self.assertEqual(art.fingerprint(changed), art.fingerprint(recipe()))
        with self.assertRaisesRegex(ValidationError, "inchang"):
            art.capture_review(session["id"], changed)
        self.assertEqual(len(art.get_review(session["id"])["attempts"]), 1)

    def test_missing_images_or_renderer_failure_do_not_consume_attempts(self):
        session = self.session()
        with mock.patch.object(fx_tools, "render_batch", return_value={}), self.assertRaises(ValidationError):
            art.capture_review(session["id"])
        self.assertEqual(art.get_review(session["id"])["state"], "ready")
        self.assertEqual(art.get_review(session["id"])["attempts"], [])
        with mock.patch.object(fx_tools, "render_batch", side_effect=RuntimeError("No WebGL")), self.assertRaisesRegex(RuntimeError, "WebGL"):
            art.capture_review(session["id"])
        self.assertEqual(art.get_review(session["id"])["attempts"], [])

    def test_a_revised_layer_plan_can_follow_a_real_node_removal(self):
        session = self.session()
        self.revise(session)
        changed = art.apply_operations(recipe(), [{"op": "remove_node", "node": "accent"}])
        with self.assertRaisesRegex(ValidationError, "nodes"):
            art.capture_review(session["id"], changed)
        direction = brief()
        direction["layers"] = direction["layers"][:1]
        plan = art.create_plan(changed, direction)
        revised = art.capture_review(session["id"], changed, plan=plan)
        self.assertEqual(revised["state"], "awaiting_human_review")
        self.assertEqual(revised["plan"]["layers"][0]["nodes"], ["core"])
        self.assertEqual(len(revised["plan"]["layers"]), 1)

    def test_batch_commits_complete_valid_copy_or_no_changes_on_failure(self):
        project = recipe()
        snapshot = deepcopy(project)
        operations = [
            {"op": "properties", "node": "core", "values": {"Brightness": 2}},
            {"op": "motion", "value": {"node": "carrier", "type": "arc", "to": [4, 3, -2], "samples": 3}},
        ]
        original = deepcopy(operations)
        result = art.apply_operations(project, operations)
        self.assertEqual(result["nodes"][2]["properties"]["Brightness"], 2)
        self.assertTrue(result["animations"][0]["runtime"])
        self.assertEqual(project, snapshot)
        self.assertEqual(operations, original)
        with self.assertRaises(ValidationError):
            art.apply_operations(project, operations + [{"op": "properties", "node": "core", "values": {"Lifetime": [-1, 1]}}])
        self.assertEqual(project, snapshot)

    def test_removal_cleans_descendants_and_animation_tracks(self):
        project = art.apply_operations(recipe(), [{"op": "motion", "value": {"node": "carrier", "type": "spin", "samples": 2}}])
        with self.assertRaisesRegex(ValidationError, "descendants"):
            art.apply_operations(project, [{"op": "remove_node", "node": "carrier", "descendants": False}])
        removed = art.apply_operations(project, [{"op": "remove_node", "node": "carrier"}])
        self.assertEqual(removed["nodes"], [])
        self.assertEqual(removed["animations"], [])
        self.assertEqual(len(project["nodes"]), 4)

    def test_low_profile_prioritizes_primary_silhouette_even_if_accent_is_first(self):
        project = recipe()
        snapshot = deepcopy(project)
        plan = art.create_plan(project, brief())
        result = art.quality_profile(project, "low", plan=plan, max_particles=90)
        nodes = {node["id"]: node for node in result["project"]["nodes"]}
        self.assertEqual(nodes["core"]["timing"]["count"], 60)
        self.assertEqual(nodes["accent"]["timing"]["count"], 30)
        self.assertLessEqual(result["report"]["counts"]["particles"], 90)
        self.assertEqual(nodes["core"]["timing"]["start"], .6)
        self.assertEqual(project, snapshot)

    def test_profile_bounds_keyed_rates_total_emissions_and_reduced_lights(self):
        project = recipe()
        project["nodes"].append({"id": "flow", "class": "ParticleEmitter", "parent": "carrier", "properties": {"Rate": 20},
                                 "timing": {"start": 0, "duration": 1.5, "mode": "continuous", "count": 1}})
        project["animations"] = [
            {"node": "flow", "property": "Rate", "keyframes": [{"time": 0, "value": 100}, {"time": 1, "value": 10}]},
            {"node": "light", "property": "Brightness", "keyframes": [{"time": 0, "value": 10}, {"time": 1, "value": 0}]},
        ]
        result = art.quality_profile(project, "medium", reduced=True, max_particles=75)
        self.assertLessEqual(result["report"]["counts"]["particles"], 75)
        nodes = {node["id"]: node for node in result["project"]["nodes"]}
        self.assertLess(nodes["flow"]["properties"]["Rate"], 20)
        self.assertLessEqual(nodes["light"]["properties"]["Brightness"], 1)
        light_track = next(track for track in result["project"]["animations"] if track["node"] == "light")
        self.assertTrue(all(key["value"] <= 1 for key in light_track["keyframes"]))
        for options in ({"quality": "ultra"}, {"max_particles": 0}, {"max_particles": True}, {"reduced": "yes"}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                art.quality_profile(project, **options)


if __name__ == "__main__":
    unittest.main()
