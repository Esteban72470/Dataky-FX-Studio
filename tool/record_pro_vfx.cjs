/* Actual timed WebGL playback, captured from Dataky's canvas. No Studio. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {loadPlaywright, routeFile} = require('./fx_render.cjs');
const ROOT = path.resolve(__dirname, '..');
const NAMES = ['CelestialRiftSlash', 'SolarSpear', 'PhantomBloom'];

async function main() {
  const browser = await loadPlaywright().chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
  try {
    const selected = process.argv.slice(2);
    if (selected.some(name => !NAMES.includes(name))) throw new Error('Unknown effect');
    for (const name of selected.length ? selected : NAMES) {
      const recipe = JSON.parse(fs.readFileSync(path.join(ROOT, 'editor/projects', name + '.json'), 'utf8'));
      const page = await browser.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/*', route => {
        const file = routeFile(route.request().url());
        if (!file || !fs.existsSync(file)) return route.fulfill({status: 404, body: ''});
        return route.fulfill({status: 200, contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'image/png', body: fs.readFileSync(file)});
      });
      await page.goto('http://dataky.local/render.html');
      const result = await page.evaluate(async recipe => {
        const E = window.DatakyEmulator;
        const canvas = document.createElement('canvas');
        canvas.width = 960; canvas.height = 720;
        document.body.replaceChildren(canvas);
        const renderer = E.createRenderer(canvas, {preserveDrawingBuffer: true});
        await renderer.preload(recipe);
        const sim = E.createSimulation(recipe, {seed: 17});
        const view = {background: 'dark', ground: true};
        renderer.render(sim, recipe.camera, view);
        const chunks = [];
        const stream = canvas.captureStream(30);
        const recorder = new MediaRecorder(stream, {mimeType: 'video/webm;codecs=vp9', videoBitsPerSecond: 4000000});
        const stopped = new Promise(resolve => recorder.onstop = resolve);
        recorder.ondataavailable = e => {if (e.data.size) chunks.push(e.data);};
        recorder.start();
        let frames = 0;
        // Three loops at real speed with a short empty pause between casts.
        for (let cast = 0; cast < 3; cast++) {
          sim.reset();
          const began = performance.now();
          let previous = began;
          await new Promise(resolve => {
            function tick(now) {
              sim.advance(Math.max(0, now - previous) / 1000);
              previous = now;
              renderer.render(sim, recipe.camera, view);
              frames++;
              if ((now - began) / 1000 >= recipe.duration + .32) resolve();
              else requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
          });
        }
        recorder.stop(); await stopped;
        stream.getTracks().forEach(track => track.stop());
        const blob = new Blob(chunks, {type: 'video/webm'});
        const data = await new Promise(resolve => {const r = new FileReader(); r.onload = () => resolve(r.result); r.readAsDataURL(blob);});
        return {data, frames, warnings: [...renderer.warnings]};
      }, recipe);
      if (errors.length || result.warnings.length) throw new Error(JSON.stringify({errors, warnings: result.warnings}));
      const out = path.join(ROOT, 'rendus/pro', name, 'preview.webm');
      fs.writeFileSync(out, Buffer.from(result.data.split(',')[1], 'base64'));
      console.log(JSON.stringify({name, out, frames: result.frames, bytes: fs.statSync(out).size}));
      await page.close();
    }
  } finally {await browser.close();}
}
main().catch(e => {console.error(e); process.exitCode = 1;});
