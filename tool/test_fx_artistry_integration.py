"""HTTP/MCP and actual Chromium exercise of the new editor workflow."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import fx_artistry as art
import fx_assets
import fx_mcp
import fx_server
from test_fx_artistry import recipe, brief, observations, png_renderer


class ArtistryIntegration(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for module in (art, fx_assets):
            patch = mock.patch.object(module, 'ROOT', self.root)
            patch.start()
            self.addCleanup(patch.stop)
        original = Path(__file__).resolve().parent.parent
        (self.root / 'editor').mkdir()
        for name in ('index.html', 'app.js', 'curves.js', 'emulator.js', 'styles.css', 'artistry.js', 'artistry.css'):
            shutil.copy2(original / 'editor' / name, self.root / 'editor' / name)
        server = fx_server.create_server(library=self.root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        self.origin = f'http://127.0.0.1:{server.server_port}'

    def request(self, path, data=None):
        req = Request(self.origin + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Content-Type': 'application/json'} if data is not None else {})
        with urlopen(req, timeout=30) as response:
            return response.read(), response.headers.get_content_type()

    def test_http_review_images_errors_and_mcp_image_payloads(self):
        saved = json.loads(self.request('/api/artistry/plan', {'project': recipe(), 'brief': brief()})[0])
        self.assertEqual(saved['id'], 'art-test')
        self.assertEqual(json.loads(self.request('/api/artistry/plan/art-test')[0]), saved)
        reply = fx_mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        names = [tool['name'] for tool in reply['result']['tools']]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn('animate_procedural', names)
        session = json.loads(self.request('/api/artistry/review_create', {'project': recipe(), 'plan': saved, 'vision': True})[0])
        listed = json.loads(self.request('/api/artistry/reviews?project_id=art-test')[0])
        self.assertEqual(listed['reviews'][0]['id'], session['id'])
        self.assertEqual(json.loads(fx_mcp.call('list_visual_reviews', {'project_id':'art-test'})[0]['text'])['reviews'][0]['id'], session['id'])
        self.assertEqual(json.loads(fx_mcp.call('get_visual_review', {'id':session['id']})[0]['text'])['state'], 'ready')
        with mock.patch.object(art.sibling('fx_tools'), 'render_batch', side_effect=png_renderer):
            capture = fx_mcp.call('capture_visual_review', {'id': session['id']})
        self.assertEqual([c['type'] for c in capture], ['text', 'image', 'image'])
        self.assertTrue(base64.b64decode(capture[1]['data']).startswith(b'\x89PNG'))
        state = json.loads(capture[0]['text'])
        image = state['attempts'][0]['images'][0]
        png, mime = self.request('/api/artistry/file/' + session['id'] + '/' + Path(image).name)
        self.assertEqual(mime, 'image/png')
        self.assertTrue(png.startswith(b'\x89PNG'))
        with self.assertRaises(HTTPError) as error:
            self.request('/api/artistry/motion', {'project': recipe(), 'specs': {'node': 'missing', 'type': 'orbit'}})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/artistry/file/' + session['id'] + '/../' + session['id'] + '.json')
        self.assertEqual(error.exception.code, 403)
        bad = fx_mcp.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'animate_procedural','arguments':{'project':recipe(),'specs':{'node':'bad','type':'orbit'}}}})
        self.assertTrue(bad['result']['isError'])
        self.assertNotIn('Erreur interne', bad['result']['content'][0]['text'])

    def test_real_browser_plan_motion_review_and_runtime_edit_preservation(self):
        fixture = recipe()
        fixture['nodes'][0]['properties']['Position'] = [0, 2, 0]
        script = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {loadPlaywright}=require('./tool/fx_render.cjs');
(async()=>{
 const browser=await loadPlaywright().chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.DATAKY_TEST_ORIGIN);
  await page.waitForFunction(()=>window.DatakyFX);
  const fixture=JSON.parse(process.env.DATAKY_TEST_RECIPE);
  await page.evaluate(p=>window.DatakyFX.setProject(p),fixture);
  await page.click('#artistry-button');await page.waitForSelector('#artistry-dialog[open]');
  assert.equal(await page.locator('[data-art-panel=motion]').isVisible(),false);
  const b=JSON.parse(process.env.DATAKY_TEST_BRIEF);
  for(const key of ['theme','character','silhouette','readability'])await page.fill('#art-'+key,b[key]);
  await page.fill('#art-motion-intent',b.motion);
  await page.fill('[data-layer=purpose]',b.layers[0].purpose);
  await page.selectOption('[data-layer=nodes]',['core','accent']);
  await page.selectOption('[data-layer=phase]','release');
  await page.click('#art-save-plan');await page.waitForFunction(()=>document.querySelector('#art-error').textContent.includes('enregistrée'));
  await page.click('[data-art-tab=motion]');await page.selectOption('#art-motion-node','carrier');
  await page.click('#art-apply-motion');await page.waitForFunction(()=>window.DatakyFX.getProject().animations.length===1);
  assert.equal(await page.evaluate(()=>window.DatakyFX.getProject().animations[0].runtime),true);
  await page.click('[data-art-tab=review]');await page.click('#art-capture');
  await page.waitForFunction(()=>document.querySelector('#art-review-state').textContent.includes('Validation humaine'),{timeout:30000});
  const images=page.locator('#art-captures img');assert.equal(await images.count(),2);
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#art-captures img')).every(i=>i.complete&&i.naturalWidth>0));
  assert.equal(await page.locator('#art-capture').isDisabled(),true);
  await page.click('#art-approve');await page.waitForFunction(()=>document.querySelector('#art-error').textContent.includes('observations'));
  const criteria=Object.keys(JSON.parse(process.env.DATAKY_TEST_OBSERVATIONS));
  for(const criterion of criteria)await page.fill('[data-criterion='+criterion+']','Observation humaine de test : '+criterion);
  await page.click('#art-revise');await page.waitForFunction(()=>document.querySelector('#art-review-state').textContent.includes('Correction attendue'));
  await page.click('#art-close');
  // Editing an authored runtime track through the old editor must keep opt-in.
  await page.evaluate(()=>{const p=window.DatakyFX.getProject();p.animations[0].keyframes=p.animations[0].keyframes.filter((k,i,a)=>i===0||i===a.length-1);window.DatakyFX.setProject(p);window.DatakyFX.select('carrier');});
  await page.locator('.timeline-row').filter({hasText:'Position'}).first().locator('.track-label').click();
  await page.click('#animation-apply');
  assert.equal(await page.evaluate(()=>window.DatakyFX.getProject().animations[0].runtime),true);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
'''
        import os
        env = {**os.environ, 'DATAKY_TEST_ORIGIN': self.origin, 'DATAKY_TEST_RECIPE': json.dumps(fixture),
               'DATAKY_TEST_BRIEF': json.dumps(brief()), 'DATAKY_TEST_OBSERVATIONS': json.dumps(observations())}
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parent.parent,
                                env=env, capture_output=True, text=True, timeout=80)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
