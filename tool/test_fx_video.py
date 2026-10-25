"""A real synthetic local video tests extraction; it is never a user reference."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import fx_video as video
except ImportError:
    import fx_video as video


class VideoPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.source = Path(cls.folder.name) / "synthetic-test-only.avi"
        cv2, numpy, _, _ = video._dependencies()
        writer = cv2.VideoWriter(str(cls.source), cv2.VideoWriter_fourcc(*"MJPG"), 20, (160, 90))
        if not writer.isOpened():
            raise RuntimeError("Synthetic AVI encoder unavailable; real extraction test cannot run")
        try:
            for i in range(80):
                frame = numpy.zeros((90, 160, 3), dtype=numpy.uint8)
                if 20 <= i < 60:
                    cv2.circle(frame, (20+(i-20)*3, 45), 12, (220, 80, 160), -1)
                if 40 <= i < 44:
                    frame[:] = (245, 245, 245)
                writer.write(frame)
        finally:
            writer.release()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def imported(self):
        return video.import_video(self.source, root=self.root, source_url="https://example.com/reference", rights_note="Synthetic test fixture, not an artistic reference")

    def test_actual_local_import_metadata_and_idempotence(self):
        record = self.imported()
        self.assertEqual(record["metadata"]["width"], 160)
        self.assertEqual(record["metadata"]["height"], 90)
        self.assertAlmostEqual(record["metadata"]["duration_seconds"], 4)
        self.assertFalse(record["content_observed_by_model"])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), record["id"])
        self.assertEqual(record, self.imported())
        self.assertEqual(len(video.list_videos(root=self.root)), 1)

    def test_sparse_detection_and_adaptive_contact_sheets_are_real_files(self):
        record = self.imported()
        result = video.analyze_video(record["id"], root=self.root, sample_interval=.5, level="A", max_samples=20)
        self.assertFalse(result["cache_hit"])
        self.assertLessEqual(len(result["samples"]), 20)
        self.assertGreater(max(sample["score"] for sample in result["samples"]), 0)
        self.assertTrue(result["segments"])
        self.assertTrue(result["contact_sheets"])
        self.assertTrue(result["selected_frames"])
        for segment in result["segments"]:
            self.assertLessEqual(segment["selected_frame_count"], 8)
            self.assertEqual(segment["validation"], "required")
        folder = self.root / result["relative_directory"]
        self.assertTrue(all((folder / name).is_file() for name in result["contact_sheets"]))
        self.assertTrue(all((folder / item["file"]).is_file() for item in result["selected_frames"]))
        self.assertEqual(result["metrics"]["multimodal_calls"], 0)
        self.assertIsNone(result["metrics"]["multimodal_tokens"])
        self.assertEqual(result["artistic_analysis"]["status"], "not_analyzed_by_model")
        self.assertTrue(result["artistic_analysis"]["human_validation_required"])

    def test_cache_avoids_decoding_and_parameters_change_cache_identity(self):
        record = self.imported()
        first = video.analyze_video(record["id"], root=self.root, sample_interval=1)
        with patch.object(video, "_dependencies", side_effect=AssertionError("cache should not decode")):
            second = video.analyze_video(record["id"], root=self.root, sample_interval=1)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["id"], second["id"])
        detailed = video.analyze_video(record["id"], root=self.root, sample_interval=1, level="B")
        self.assertNotEqual(first["id"], detailed["id"])

    def test_manual_boundaries_phases_and_measured_timestamps_are_preserved(self):
        record = self.imported()
        segments = [{"start": .5, "end": 3.5, "label": "Human selected interval",
                     "phases": [{"name": "charge", "start": .5, "end": 1.1}, {"name": "impact", "start": 2, "end": 2.2}]}]
        result = video.analyze_video(record["id"], root=self.root, segments=segments, level="B", sample_interval=1)
        segment = result["segments"][0]
        self.assertEqual(segment["start"], .5)
        self.assertEqual(segment["end"], 3.5)
        self.assertEqual(segment["phases"][1]["start"], 2)
        self.assertEqual(segment["source"], "manual")
        times = [frame["timestamp"] for frame in result["selected_frames"]]
        self.assertEqual(times, sorted(times))
        self.assertIsNone(result["selected_frames"][0]["delta_previous_seconds"])
        self.assertTrue(all("requested_timestamp" in item for item in result["selected_frames"]))
        self.assertEqual(segments[0]["phases"][0], {"name": "charge", "start": .5, "end": 1.1})

    def test_frame_budget_is_adaptive_and_tier_bounded(self):
        record = self.imported()
        short = video.analyze_video(record["id"], root=self.root, segments=[{"start": 0, "end": .3}], level="C")
        long = video.analyze_video(record["id"], root=self.root, segments=[{"start": 0, "end": 3.9}], level="C")
        self.assertLess(short["segments"][0]["selected_frame_budget"], long["segments"][0]["selected_frame_budget"])
        self.assertLessEqual(long["segments"][0]["selected_frame_count"], 32)

    def test_missing_cached_frame_is_rebuilt(self):
        record = self.imported()
        first = video.analyze_video(record["id"], root=self.root)
        frame = self.root / first["relative_directory"] / first["selected_frames"][0]["file"]
        frame.unlink()
        second = video.analyze_video(record["id"], root=self.root)
        self.assertFalse(second["cache_hit"])
        self.assertTrue(frame.is_file())

    def test_modified_imported_content_is_rejected(self):
        record = self.imported()
        (self.root / record["relative_path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(video.VideoError, "changé"):
            video.analyze_video(record["id"], root=self.root)

    def test_network_import_invalid_segments_and_paths_are_rejected(self):
        with self.assertRaisesRegex(video.VideoError, "local"):
            video.import_video("https://youtube.com/watch?v=anything", root=self.root)
        with self.assertRaises(video.VideoError):
            video.get_video("../../anything", root=self.root)
        record = self.imported()
        for segments in ([], [{"start": 3, "end": 1}], [{"start": -1, "end": 1}], [{"start": 0, "end": 9}], [{"start": 0, "end": 1, "execute": "code"}]):
            with self.subTest(segments=segments), self.assertRaises(video.VideoError):
                video.analyze_video(record["id"], root=self.root, segments=segments)
        for kwargs in ({"level": "D"}, {"max_samples": 999999}, {"sample_interval": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(video.VideoError):
                video.analyze_video(record["id"], root=self.root, **kwargs)

    def test_list_analyses_reports_actual_budgets_without_artist_claims(self):
        record = self.imported()
        result = video.analyze_video(record["id"], root=self.root)
        values = video.list_analyses(root=self.root)
        self.assertEqual(values[0]["id"], result["id"])
        self.assertEqual(values[0]["metrics"]["multimodal_calls"], 0)
        self.assertEqual(video.get_analysis(result["id"], root=self.root)["metadata"]["width"], 160)


if __name__ == "__main__":
    unittest.main()
