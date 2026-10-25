"""Local model endpoints and UI remain unavailable after explicit uninstall."""
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import fx_server


class LocalAIRemoved(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.server=fx_server.create_server(cls.root,port=0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.origin=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.thread.join(2);cls.server.server_close()

    def request(self,path,data=None):
        with urlopen(Request(self.origin+path,data=None if data is None else json.dumps(data).encode(),
            headers={}if data is None else{'Content-Type':'application/json'}))as reply:
            return reply.read()

    def test_inference_and_history_endpoints_are_gone(self):
        for suffix in ('status','generate','resume','critique','refine','knowledge','history','config','catalog','attempts'):
            for data in (None,{}):
                with self.subTest(suffix=suffix,post=data is not None),self.assertRaises(HTTPError)as error:
                    self.request('/api/local-ai/'+suffix,data)
                self.assertEqual(error.exception.code,404)

    def test_static_ui_has_no_local_model_dependencies(self):
        index=self.request('/').decode()
        self.assertNotIn('local-ai.js',index);self.assertNotIn('local-ai.css',index)
        video=self.request('/video.js').decode()
        self.assertNotIn('video-vision',video)
        self.assertNotIn('visionResults',video)
        for path in ('/local-ai.js','/local-ai.css'):
            with self.subTest(path=path),self.assertRaises(HTTPError)as error:self.request(path)
            self.assertEqual(error.exception.code,404)

    def test_video_extraction_and_asset_catalogue_are_retained(self):
        self.assertIn('references',json.loads(self.request('/api/video/references')))
        self.assertIn('textures',json.loads(self.request('/api/catalog/summary'))['counts'])
        self.assertTrue((self.root/'tool/fx_ai_catalog.py').is_file())
        self.assertTrue((self.root/'tool/fx_ai_assets.py').is_file())
        with self.assertRaises(HTTPError)as error:self.request('/api/video/vision',{})
        self.assertEqual(error.exception.code,404)

    def test_only_narrow_authored_texture_paths_are_public(self):
        allow=fx_server.Handler.library_allowed
        self.assertTrue(allow('source/vfx/enuma-elish/textures/rupture-core_01.png'))
        for path in ('source/vfx/enuma-elish/main.py','source/vfx/enuma-elish/textures/a.json',
            'source/vfx/enuma-elish/textures/../main.png','source/vfx/enuma-elish/textures/.private.png',
            'source/vfx/enuma-elish/textures/subdir/a.png','source/vfx/../textures/a.png','source/secret.png'):
            with self.subTest(path=path):self.assertFalse(allow(path))


if __name__=='__main__':unittest.main()
