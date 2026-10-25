"""Observed metadata must remain distinct from guesses based on asset names."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

try:
    from . import fx_assets, fx_tools
except ImportError:
    import fx_assets
    import fx_tools


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=")


class AssetMetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        rows = [{"asset_id": str(100 + i), "name": name, "kind": "static", "id_status": "valid", "tags": tags}
                for i, (name, tags) in enumerate([("Red anime ring", ["Circle"]), ("Curved slash", ["Slash"]), ("Mist", ["Smoke"])])]
        self.enterContext(mock.patch.object(fx_assets, "ROOT", self.root))
        self.enterContext(mock.patch.object(fx_tools, "ROOT", self.root))
        (self.root / "textures.json").write_text(json.dumps(rows), encoding="utf-8")
        self.enterContext(mock.patch.object(fx_tools, "_catalogs", {}))
        self.evidence = self.root / "observed.png"
        self.evidence.write_bytes(PNG)

    def annotate(self, ident="100", **metadata):
        return fx_assets.annotate_asset(ident, "textures", metadata, observer="human", evidence=self.evidence)

    def test_descriptive_name_never_becomes_visual_evidence(self):
        self.assertEqual(fx_assets.search(query="red anime")["total"], 1)
        self.assertEqual(fx_assets.search(color="red")["total"], 0)
        self.assertEqual(fx_assets.search(style="anime")["total"], 0)
        self.assertEqual(fx_assets.search(shape="ring")["total"], 0)
        item = fx_assets.search(category="circle")["items"][0]
        self.assertEqual(item["visual_status"], "unknown")
        self.assertEqual(item["metadata"]["color"], [])
        self.assertEqual(item["provenance"], {})
        self.assertFalse((self.root / "editor").exists(), "read-only search creates no metadata files")

    def test_progressive_observation_preserves_field_provenance_and_filters_before_pagination(self):
        first = self.annotate(shape=["Curved", "CURVED"], color="cyan", usage="focal")
        fx_assets.annotate_asset("rbxassetid://100", "textures", {"style": "ink"}, observer="vision", evidence=self.evidence)
        self.annotate("101", shape="curved", color="cyan")
        result = fx_assets.search(shape="curved", color="cyan", limit=1, offset=1)
        self.assertEqual((result["total"], result["items"][0]["id"]), (2, "101"))
        item = fx_assets.search(shape="curved", style="ink")["items"][0]
        self.assertEqual(item["metadata"]["shape"], ["curved"])
        self.assertEqual(item["provenance"]["shape"]["observer"], "human")
        self.assertEqual(item["provenance"]["style"]["observer"], "vision")
        self.assertEqual(item["provenance"]["shape"]["evidence"]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(item["provenance"]["shape"], first["provenance"]["shape"])
        self.annotate(color=[])
        self.assertEqual(fx_assets.search(color="cyan")["total"], 1)

    def test_annotation_requires_known_asset_real_visual_evidence_and_bounded_metadata(self):
        for metadata in ({"guess": "blue"}, {"shape": ["x"] * 17}, {"notes": "n" * 2001}, {"color": 7}):
            with self.subTest(metadata=str(metadata)[:30]), self.assertRaises(fx_tools.ToolError):
                self.annotate(**metadata)
        for kwargs in ({"observer": "automatic", "evidence": self.evidence},
                       {"observer": "human", "evidence": self.root / "missing.png"}):
            with self.assertRaises(fx_tools.ToolError):
                fx_assets.annotate_asset("100", "textures", {"shape": "ring"}, **kwargs)
        with self.assertRaises(fx_tools.ToolError):
            self.annotate("99999", shape="ring")
        self.assertFalse((self.root / "editor").exists())

    def test_corrupt_index_is_preserved_and_failed_atomic_replace_keeps_previous_observation(self):
        self.annotate(shape="curved")
        path = self.root / "editor/artistry/assets.json"
        original = path.read_bytes()
        with mock.patch.object(fx_assets.os, "replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.annotate(color="cyan")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".dataky-*")), [])
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(fx_tools.ToolError, "conservé"):
            self.annotate(style="ink")
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        self.assertFalse(path.with_suffix(".lock").exists())

    def test_simultaneous_annotations_do_not_lose_other_fields(self):
        jobs = [("shape", "curved"), ("style", "ink"), ("color", "cyan"), ("usage", "focal"), ("category", "blade")]
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(lambda pair: self.annotate(**{pair[0]: pair[1]}), jobs))
        item = fx_assets.search()["items"][0]
        self.assertEqual(item["metadata"], {key: [value] for key, value in jobs})

    def test_search_rejects_bad_limits_and_has_or_labels_and_and_fields(self):
        self.annotate(shape="crescent", color="cyan")
        self.assertEqual(fx_assets.search(shape=["circle", "crescent"], color="cyan")["total"], 1)
        self.assertEqual(fx_assets.search(shape="crescent", color="red")["total"], 0)
        for kwargs in ({"limit": 121}, {"limit": True}, {"offset": -1}, {"kind": "imaginary"}, {"collection": "unknown"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(fx_tools.ToolError):
                fx_assets.search(**kwargs)

    def test_reference_is_independent_copy_with_observations_and_can_be_relocated(self):
        ref = fx_assets.add_reference(self.evidence, "spritesheet", {"forms": ["Tapered arcs"], "rhythm": "A short hold, then a fast release"},
                                     observer="vision", name="Arc study", source="User-provided study")
        target = Path(ref["path"])
        self.assertEqual(target.read_bytes(), PNG)
        self.assertEqual(ref["evidence"]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertIn("original effect", ref["purpose"])
        self.evidence.unlink()
        self.assertTrue(fx_assets.get_reference(ref["id"])["available"])
        self.assertEqual(fx_assets.list_references()[0]["observations"]["forms"], ["tapered arcs"])
        with tempfile.TemporaryDirectory() as relocated:
            new_root = Path(relocated)
            shutil.copytree(self.root / "editor", new_root / "editor")
            with mock.patch.object(fx_assets, "ROOT", new_root):
                moved = fx_assets.get_reference(ref["id"])
                self.assertTrue(moved["available"])
                self.assertTrue(Path(moved["path"]).is_relative_to(new_root.resolve()))
        target.unlink()
        self.assertFalse(fx_assets.get_reference(ref["id"])["available"])
        with self.assertRaises(fx_tools.ToolError):
            fx_assets.get_reference("../../not-a-reference")

    def test_reference_validation_rejects_disguised_files_and_kind_mismatch(self):
        fake = self.root / "fake.png"
        fake.write_text("an executable disguised as an image", encoding="utf-8")
        for path, kind, observations in [(fake, "image", {"notes": "test"}), (self.evidence, "video", {"notes": "test"}),
                                         (self.evidence, None, {"notes": "test"}), (self.evidence, "image", {}),
                                         (self.evidence, "image", {"notes": ""}), (self.evidence, "image", {"confidence": .99})]:
            with self.subTest(kind=kind, observations=observations), self.assertRaises(fx_tools.ToolError):
                fx_assets.add_reference(path, kind, observations, observer="human")
        with mock.patch.object(fx_assets, "MAX_IMAGE", 10), self.assertRaisesRegex(fx_tools.ToolError, "volumineux"):
            fx_assets.add_reference(self.evidence, "image", {"notes": "A study"}, observer="human")
        self.assertFalse((self.root / "editor").exists())

    def test_video_registration_retains_original_and_does_not_claim_analysis(self):
        video = self.root / "reference.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20)
        ref = fx_assets.add_reference(video, "video", {"motion": "Observed manually: curved release"}, observer="human")
        self.assertEqual(Path(ref["path"]).read_bytes(), video.read_bytes())
        self.assertEqual(ref["observer"], "human")
        self.assertEqual(ref["kind"], "video")

    def test_reference_index_failure_removes_unregistered_copy(self):
        with mock.patch.object(fx_assets, "_write", side_effect=OSError("disk full")), self.assertRaises(OSError):
            fx_assets.add_reference(self.evidence, "image", {"notes": "Study"}, observer="human")
        directory = self.root / "editor/artistry/references"
        self.assertEqual(list(directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
