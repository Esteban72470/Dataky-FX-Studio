"""Real local decoding and real Chromium reference workflow; no fake vision."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import fx_server
import fx_video


class VideoIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_folder = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.fixture_folder.name) / "Synthetic video fixture.avi"
        cv2, numpy, _, _ = fx_video._dependencies()
        writer = cv2.VideoWriter(str(cls.fixture), cv2.VideoWriter_fourcc(*"MJPG"), 20, (160, 90))
        if not writer.isOpened():
            raise RuntimeError("Synthetic AVI encoder is required for the integration test")
        try:
            for i in range(50):
                frame = numpy.zeros((90, 160, 3), dtype=numpy.uint8)
                cv2.circle(frame, (20+i*2, 45), 7+i%10, (240, 120, 180), -1)
                writer.write(frame)
        finally:
            writer.release()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_folder.cleanup()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        original = Path(__file__).resolve().parents[1]
        (self.root / "editor").mkdir()
        for file in (original / "editor").iterdir():
            if file.is_file() and file.suffix in {".js", ".css", ".html"}:
                shutil.copy2(file, self.root / "editor" / file.name)
        for directory in ("beams", "meshes"):
            (self.root / directory).mkdir()
            (self.root / directory / "assets.json").write_text("[]")
        (self.root / "textures.json").write_text("[]")
        self.server = fx_server.create_server(self.root, port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, data=None):
        request = Request(self.origin+path, data=None if data is None else json.dumps(data).encode(),
                          headers={} if data is None else {"Content-Type": "application/json"})
        with urlopen(request, timeout=30) as reply:
            value = reply.read()
            return json.loads(value) if reply.headers.get_content_type() == "application/json" else value

    def test_http_import_prepare_actual_jpegs_and_persistent_human_notes(self):
        record = self.request("/api/video/import", {"path": str(self.fixture), "rights_note": "Synthetic test only"})
        self.assertEqual(self.request("/api/video/references")["references"][0]["id"], record["id"])
        result = self.request("/api/video/analyze", {"reference_id": record["id"], "sample_interval": .5})
        self.assertEqual(result["metrics"]["multimodal_calls"], 0)
        image = self.request("/api/video/file/"+result["id"]+"/"+result["contact_sheets"][0])
        self.assertTrue(image.startswith(b"\xff\xd8"), "the endpoint serves actual generated JPEG bytes")
        note = self.request("/api/video/annotate", {"analysis_id": result["id"], "observations": {"palette": "Human observation: magenta", "technique_hypotheses": "Could be a billboard; unknown implementation"}})
        self.assertEqual(note["observer"], "human")
        loaded = self.request("/api/video/analysis/"+result["id"])
        self.assertEqual(loaded["annotations"][0]["id"], note["id"])
        self.assertFalse(note["technical_implementation_recovered"])
        self.assertEqual(self.request("/api/video/analyses")["analyses"][0]["id"], result["id"])
        cached = self.request("/api/video/analyze", {"reference_id": record["id"], "sample_interval": .5})
        self.assertTrue(cached["cache_hit"])

    def test_file_endpoint_rejects_traversal_and_unlisted_images(self):
        record = self.request("/api/video/import", {"path": str(self.fixture)})
        result = self.request("/api/video/analyze", {"reference_id": record["id"]})
        for suffix in ("../analysis.json", "analysis.json", "segment-999-frame-9999.jpg", "contact-sheet-1.jpg/../../private"):
            with self.subTest(suffix=suffix), self.assertRaises(HTTPError) as error:
                self.request("/api/video/file/"+result["id"]+"/"+suffix)
            self.assertIn(error.exception.code, {403, 404})
        with self.assertRaises(HTTPError) as error:
            self.request("/api/video/import", {"path": "https://youtube.com/watch?v=anything"})
        self.assertEqual(error.exception.code, 400)

    def test_real_browser_import_prepare_and_annotate_does_not_change_effect(self):
        script = r'''
const assert=require('node:assert/strict');const {loadPlaywright}=require('./tool/fx_render.cjs');
(async()=>{const browser=await loadPlaywright().chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.DATAKY_VIDEO_ORIGIN);await page.waitForFunction(()=>window.DatakyFX);
 const before=await page.evaluate(()=>window.DatakyFX.getProject());
 await page.click('#video-button');await page.fill('#video-path',process.env.DATAKY_VIDEO_FIXTURE);await page.fill('#video-rights','Synthetic integration fixture, not an artistic reference');
 await page.click('#video-import');await page.waitForFunction(()=>document.querySelector('#video-state').textContent.includes('Vidéo importée'));
 await page.fill('#video-interval','0.5');await page.click('#video-analyze');await page.waitForFunction(()=>!document.querySelector('#video-result').hidden);
 await page.waitForFunction(()=>[...document.querySelectorAll('#video-sheets img')].every(image=>image.complete&&image.naturalWidth>100));
assert.ok((await page.locator('#video-metrics').textContent()).includes('Préparation locale'));
assert.equal(await page.locator('#video-vision').count(),0,'local model integration was removed');
 await page.getByText('Segments et timestamps détectés',{exact:true}).click();await page.click('#video-edit-segments');const segments=JSON.parse(await page.inputValue('#video-segments'));assert.ok(segments.length);
 await page.fill('#video-concept','A moving magenta circle in a synthetic fixture');await page.fill('#video-techniques','Unknown implementation; observation only');await page.click('#video-save-notes');
 await page.waitForFunction(()=>document.querySelector('#video-state').textContent.includes('conservées'));
 assert.ok((await page.locator('#video-annotations').textContent()).includes('synthetic fixture'));
 await page.click('#video-close');assert.deepEqual(await page.evaluate(()=>window.DatakyFX.getProject()),before,'reference work must preserve manual VFX');assert.deepEqual(errors,[]);
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exit(1);});
'''
        result = subprocess.run(["node", "-e", script], cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATAKY_VIDEO_ORIGIN": self.origin, "DATAKY_VIDEO_FIXTURE": str(self.fixture)},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == "__main__":
    unittest.main()
