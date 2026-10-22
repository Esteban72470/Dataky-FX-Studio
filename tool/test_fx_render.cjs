'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const R = require('./fx_render.cjs');
const E = require('../editor/emulator.js');
const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=';
const fixture = () => ({version: 1, name: 'Focus', duration: 0.2, camera: {position: [10,6,12], target: [0,1,0]}, nodes: [
  {id: 'near', class: 'Part', properties: {Position: [3,2,0], Size: [2,2,2], Transparency: 0}},
  {id: 'far', class: 'Part', properties: {Position: [200,0,0], Size: [20,20,20], Transparency: 0}},
], animations: []});
const job = (options = {}) => R.prepareJob({projects: [fixture()], ...options});
const cameraDistance = result => Math.hypot(...result.camera.position.map((v, i) => v - result.camera.target[i]));
function removeTemp(folder) {
  const resolved = path.resolve(folder), temporaryRoot = path.resolve(os.tmpdir()) + path.sep;
  assert.ok(resolved.startsWith(temporaryRoot) && path.basename(resolved).startsWith('dataky-render-'));
  fs.rmSync(resolved, {recursive: true, force: true});
}

async function inBrowser(emulator, callback) {
  const previous = global.window;
  global.window = {DatakyEmulator: emulator};
  try { return await callback(); }
  finally { if (previous === undefined) delete global.window; else global.window = previous; }
}

const captureEmulator = {...E,
  renderSheet: async (_, config) => ({image: PNG, camera: config.camera, warnings: [], autoCamera: config.autoCamera}),
  renderComparison: async (_, config) => ({image: PNG, camera: config.camera, warnings: [], autoCamera: config.autoCamera}),
};

test('renderer CLI preserves old inputs and accepts batch/focus flags', () => {
  assert.deepEqual(R.parse(['a.json', '--times', '0,0.2', '--dummy']).sources, ['a.json']);
  const parsed = R.parse(['--batch', 'jobs.json', '--size', '80x60']);
  assert.equal(parsed.options.batch, 'jobs.json');
  assert.throws(() => R.parse(['a.json', '--batch', 'jobs.json']), /ne se combine/);
  assert.deepEqual(job({focus: '3,2,1', radius: '2'}).settings.focus, [3,2,1]);
  const fitted = R.parse(['a.json', '--fit', 'near', '--fit-percentile', '95', '--fit-all']);
  assert.equal(fitted.options.fitAll, true);
  assert.equal(job(fitted.options).settings.fitPercentile, 95);
  for (const options of [{focus: '1,2,3'}, {radius: 2}, {focus: [1,2,3], radius: 0}, {fit: 'near', focus: [1,2,3], radius: 1}, {camera: '1,2,3'}, {size: '80x60x2'}, {frames: 0}, {fov: 0}, {fitPercentile: 0}, {fitPercentile: 101}, {fitPercentile: 'NaN'}]) {
    assert.throws(() => job(options));
  }
  assert.throws(() => job({fit: 'missing'}), /introuvable missing/);
});

test('explicit camera overrides inherited automatic framing; fit/focus retain its direction', async () => {
  const requested = {position: [3,2,4], target: [0,.3,0], fov: 50};
  const explicit = job({camera: [3,2,4,0,.3,0], autoCamera: true});
  assert.equal(explicit.settings.autoCamera, false);
  const rendered = await inBrowser(captureEmulator, () => R.renderInPage(explicit));
  assert.deepEqual(rendered.camera, requested);
  for (const framing of [{fit: 'near'}, {focus: [1,2,3], radius: 2}]) {
    const framed = job({camera: [3,2,4,0,.3,0], autoCamera: true, ...framing});
    const result = await inBrowser(captureEmulator, () => R.renderInPage(framed));
    assert.equal(result.autoCamera, false);
    assert.notDeepEqual(result.camera, requested);
    const direction = camera => camera.position.map((v, i) => v-camera.target[i]);
    const actual = direction(result.camera), expected = direction(requested);
    for (let i=0; i<3; i++) assert.ok(Math.abs(actual[i]/Math.hypot(...actual)-expected[i]/Math.hypot(...expected)) < .001);
  }
});

test('background comparison options accept lists or comma strings and reject ambiguity', () => {
  const parsed = R.parse(['a.json', '--backgrounds', 'roblox,dark']);
  assert.deepEqual(job(parsed.options).settings.backgrounds, ['roblox', 'dark']);
  assert.deepEqual(job({backgrounds: ['roblox', 'dark']}).settings.backgrounds, ['roblox', 'dark']);
  assert.equal(job({background: 'dark'}).settings.background, 'dark');
  for (const backgrounds of [[], '', 'dark,', ['dark', 'bad'], 12, Array(9).fill('dark')]) {
    assert.throws(() => job({backgrounds}), /backgrounds/);
  }
  assert.throws(() => job({background: 'dark', backgrounds: ['roblox']}), /exclusifs/);
});

test('real Chromium dark preset and rows use the requested sky, ground, times and camera', {timeout: 90000}, async t => {
  let playwright;
  try { playwright = R.loadPlaywright(); }
  catch (error) {
    if (/Playwright est introuvable|inaccessible dans le bac à sable/.test(error.message)) return t.skip(error.message);
    throw error;
  }
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-backgrounds-'));
  const colors = [];
  const chromium = {launch: async options => {
    const browser = await playwright.chromium.launch(options);
    return {close: () => browser.close(), newPage: async () => {
      const page = await browser.newPage(), evaluate = page.evaluate.bind(page);
      page.evaluate = async (callback, payload) => {
        const result = await evaluate(callback, payload);
        colors.push(await evaluate(async frames => Promise.all(frames.map(async frame => {
          const image = new Image(); image.src = frame.image; await image.decode();
          const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
          const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
          const pixel = (x,y) => Array.from(ctx.getImageData(x,y,1,1).data).slice(0,3);
          return {row: frame.row, project: frame.project, background: frame.background, sky: pixel(2,2), ground: pixel(123,145)};
        })), result.frames));
        return result;
      };
      return page;
    }};
  }};
  try {
    const empty = fixture(); empty.nodes = [];
    const options = {projects: [empty], times: [0,.1], size: '240x160', camera: [0,5,10,0,1,0], framesDir: folder};
    const [single, comparison] = await R.runJobs([
      R.prepareJob({...options, background: 'dark', out: path.join(folder, 'dark.png')}),
      R.prepareJob({...options, projects: [empty, {...empty, name: 'Second'}], backgrounds: 'roblox,dark', out: path.join(folder, 'both.png')}),
    ], chromium);
    assert.deepEqual(single.camera, comparison.camera);
    assert.deepEqual(comparison.times, [0,.1]);
    assert.deepEqual(comparison.rows.map(row => [row.project, row.background]), [[0,'roblox'],[0,'dark'],[1,'roblox'],[1,'dark']]);
    assert.deepEqual(comparison.sheet, {width: 480, height: 728, rows: 4, columns: 2});
    assert.equal(comparison.files.length, 9, 'sheet + eight uniquely named frames');
    assert.equal(new Set(comparison.files).size, 9);
    const close = (actual, expected) => expected.forEach((value,i) => assert.ok(Math.abs(actual[i] - value) <= 2, `${actual} ~= ${expected}`));
    close(colors[0][0].sky, [9,11,20]);
    for (const frame of colors[1]) {
      if (frame.background === 'dark') {
        close(frame.sky, [9,11,20]);
        assert.ok(frame.ground.every(v => v >= 40 && v <= 75), `dark grey ground ${frame.ground}`);
      } else {
        close(frame.sky, [163,207,240]);
        assert.ok(frame.ground.every(v => v >= 160), `day grey ground ${frame.ground}`);
      }
    }
  } finally { removeTemp(folder); }
});

test('batch manifest supports inline and file recipes and rejects output collisions', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-manifest-'));
  try {
    const recipe = path.join(folder, 'recipe.json'), manifest = path.join(folder, 'jobs.json');
    fs.writeFileSync(recipe, '\uFEFF' + JSON.stringify(fixture()));
    fs.writeFileSync(manifest, JSON.stringify({jobs: [
      {projects: [fixture()], out: path.join(folder, 'first.png'), times: [0,0.1], camera: [10,6,12,0,1,0]},
      {projects: [recipe], out: path.join(folder, 'second.png'), fit: 'near'},
    ]}));
    const {sources, options} = R.parse(['--batch', manifest]);
    const jobs = R.readJobs(sources, options);
    assert.equal(jobs.length, 2); assert.equal(jobs[1].settings.fit, 'near');
    fs.writeFileSync(manifest, JSON.stringify({jobs: [
      {projects: [fixture()], out: 'same.png'}, {projects: [fixture()], out: 'same.png'},
    ]}));
    assert.throws(() => R.readJobs(sources, options), /même fichier/);
    fs.writeFileSync(manifest, JSON.stringify({jobs: []}));
    assert.throws(() => R.readJobs(sources, options), /au moins un job/);
  } finally { removeTemp(folder); }
});

test('fit uses selected geometry instead of distant effect and keeps viewing direction', async () => {
  const selected = job({fit: 'near', autoCamera: true, dummy: true});
  const rendered = await inBrowser(captureEmulator, () => R.renderInPage(selected));
  assert.deepEqual(rendered.camera.target, [3,2,0]);
  assert.equal(rendered.autoCamera, false);
  const extent = rendered.framing.bounds;
  assert.ok(extent.max[0] < 6 && extent.min[0] > 0);
  assert.match(rendered.warnings[0], /aucune particule vivante.*repli sur la Part et ses Attachments/);
  const originalDirection = selected.projects[0].camera.position.map((v,i) => v-selected.projects[0].camera.target[i]);
  const renderedDirection = rendered.camera.position.map((v,i) => v-rendered.camera.target[i]);
  const magnitude = values => Math.hypot(...values);
  for (let i=0; i<3; i++) assert.ok(Math.abs(originalDirection[i]/magnitude(originalDirection)-renderedDirection[i]/magnitude(renderedDirection))<0.001);
});

test('Bulbito Muzzle fits live render times and keeps its Flash comparable to emitter framing', async () => {
  const recipe = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/bulbito/A1_Muzzle.json'), 'utf8'));
  const fit = async options => inBrowser(captureEmulator, () => R.renderInPage(R.prepareJob({projects: [recipe], times: [0.02,0.06], ...options})));
  const muzzle = await fit({fit: 'Muzzle'}), flash = await fit({fit: 'Flash'}), all = await fit({fit: 'Muzzle', fitAll: true});
  assert.ok(muzzle.framing.bounds.radius < flash.framing.bounds.radius * 1.2);
  assert.ok(all.framing.bounds.radius > muzzle.framing.bounds.radius * 1.5);
  assert.equal(muzzle.framing.samples[0].particles, 21);
  assert.equal(muzzle.framing.samples[0].retained, 19);
  const sim = E.createSimulation(recipe);
  for (const time of [0.02,0.06]) {
    sim.seek(time);
    const frame = E.buildFrame(sim, muzzle.camera), batch = frame.batches.find(b => b.node === 'Flash');
    const ys = [];
    for (let i = batch.first; i < batch.first + batch.count; i++) {
      const relative = [0,1,2].map(axis => frame.data[i * 13 + axis] - frame.camera.position[axis]);
      const dot = vector => relative.reduce((sum, value, axis) => sum + value * vector[axis], 0);
      ys.push(dot(frame.camera.up) / (dot(frame.camera.forward) * Math.tan(frame.camera.fov * Math.PI / 360)));
    }
    assert.ok((Math.max(...ys) - Math.min(...ys)) / 2 >= 0.3, 'Flash quad occupies at least 30% of 270px height');
  }
});

test('focus and radius crop around world coordinates and comparison fits their union', async () => {
  const focused = job({focus: [100,4,-7], radius: 3, autoCamera: true});
  const rendered = await inBrowser(captureEmulator, () => R.renderInPage(focused));
  assert.deepEqual(rendered.camera.target, [100,4,-7]);
  assert.deepEqual(rendered.framing.bounds.min, [97,1,-10]);
  const first = fixture(), second = fixture(); second.nodes[0].properties.Position = [7,2,0];
  const comparison = R.prepareJob({projects: [first, second], fit: 'near'});
  const compared = await inBrowser(captureEmulator, () => R.renderInPage(comparison));
  assert.deepEqual(compared.camera.target, [5,2,0]);
});

test('fit rebuilds camera-dependent billboard footprints after recentering', async () => {
  const sequence = value => [{time: 0, value}, {time: 1, value}];
  for (const orientation of ['FacingCameraWorldUp', 'VelocityParallel']) {
    const recipe = {version: 1, name: orientation, duration: 1, camera: {position: [0,0,20], target: [0,0,0], fov: 50}, nodes: [
      {id: 'carrier', class: 'Part', properties: {Position: [1000,0,0], Size: [1,1,1], Transparency: 1}},
      {id: 'tip', class: 'Attachment', parent: 'carrier', properties: {}},
      {id: 'emitter', class: 'ParticleEmitter', parent: 'tip', properties: {
        Rate: 0, Speed: [1,1], Lifetime: [1,1], Size: sequence(4), Transparency: sequence(0),
        Squash: sequence(orientation === 'VelocityParallel' ? 3 : -3), Orientation: orientation,
      }, timing: {start: 0, duration: .1, mode: 'burst', count: 1}},
    ]};
    const settings = R.prepareJob({projects: [recipe], fit: 'carrier', times: [.02], size: '480x270'});
    const rendered = await inBrowser(captureEmulator, () => R.renderInPage(settings));
    const sim = E.createSimulation(recipe); sim.seek(.02);
    const frame = E.buildFrame(sim, rendered.camera), batch = frame.batches.find(b => b.node === 'emitter');
    for (let i = batch.first; i < batch.first + batch.count; i++) {
      const relative = [0,1,2].map(axis => frame.data[i * 13 + axis] - frame.camera.position[axis]);
      const dot = vector => relative.reduce((sum, value, axis) => sum + value * vector[axis], 0);
      const vertical = dot(frame.camera.forward) * Math.tan(frame.camera.fov * Math.PI / 360);
      assert.ok(Math.abs(dot(frame.camera.right) / (vertical * 480 / 270)) <= .8751, orientation + ' fits horizontally after the billboard turns');
      assert.ok(Math.abs(dot(frame.camera.up) / vertical) <= .8751, orientation + ' fits vertically after the billboard turns');
    }
  }
});

test('comparison camera includes an empty row carrier and Attachments alongside live particle footprints', async () => {
  const sequence = value => [{time: 0, value}, {time: 1, value}];
  const live = {version: 1, name: 'Live', duration: 1, camera: {position: [0,0,20], target: [0,0,0]}, nodes: [
    {id: 'carrier', class: 'Part', properties: {Position: [0,0,0], Size: [2,2,2], Transparency: 1}},
    {id: 'tip', class: 'Attachment', parent: 'carrier', properties: {}},
    {id: 'emitter', class: 'ParticleEmitter', parent: 'tip', properties: {Rate: 0, Speed: [0,0], Lifetime: [1,1], Size: sequence(2), Transparency: sequence(0)},
      timing: {start: 0, duration: .1, mode: 'burst', count: 1}},
  ]};
  const empty = structuredClone(live); empty.name = 'Empty'; empty.nodes.pop();
  empty.nodes[0].properties.Position = [100,0,0]; empty.nodes[1].properties.Position = [8,0,0];
  const options = R.prepareJob({projects: [live, empty], fit: 'carrier', times: [.02], size: '480x270'});
  const rendered = await inBrowser(captureEmulator, () => R.renderInPage(options));
  assert.deepEqual(rendered.framing.samples.map(sample => sample.fallback), [false, true]);
  assert.equal(rendered.warnings.length, 1);
  assert.match(rendered.warnings[0], /Empty.*repli sur la Part et ses Attachments/);
  assert.ok(rendered.camera.target[0] > 40, 'shared camera includes the distant empty row');
  const basis = E.buildFrame(E.createSimulation(empty), rendered.camera).camera;
  const fallback = E.sampledParticleBounds(empty, {ids: ['carrier'], times: [.02]});
  for (let k = 0; k < 8; k++) {
    const point = [0,1,2].map(i => ((k >> i) & 1 ? fallback.max[i] : fallback.min[i]) - basis.position[i]);
    const dot = vector => point.reduce((sum, value, i) => sum + value * vector[i], 0);
    const vertical = dot(basis.forward) * Math.tan(basis.fov * Math.PI / 360);
    assert.ok(Math.abs(dot(basis.right) / (vertical * 480 / 270)) <= .8751, 'fallback geometry fits horizontally');
    assert.ok(Math.abs(dot(basis.up) / vertical) <= .8751, 'fallback geometry fits vertically');
  }
});

function fakeChromium(failAt = -1) {
  const stats = {launches: 0, pages: 0, closedPages: 0, closedBrowsers: 0};
  const chromium = {launch: async () => {
    stats.launches++;
    return {newPage: async () => {
      const index = stats.pages++;
      return {on() {}, route: async () => {}, goto: async () => {}, waitForFunction: async () => {},
        evaluate: async (fn, payload) => {
          if (index === failAt) throw new Error('render failure');
          return inBrowser(captureEmulator, () => fn(payload));
        }, close: async () => { stats.closedPages++; }};
    }, close: async () => { stats.closedBrowsers++; }};
  }};
  return {chromium, stats};
}

test('a batch launches Chromium once and closes page resources after every job', async () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-batch-'));
  try {
    const {chromium, stats} = fakeChromium();
    const results = await R.runJobs([job({out: path.join(folder, 'a.png')}), job({out: path.join(folder, 'b.png')})], chromium);
    assert.deepEqual(stats, {launches: 1, pages: 2, closedPages: 2, closedBrowsers: 1});
    assert.equal(results.length, 2);
    for (const result of results) assert.ok(fs.readFileSync(result.files[0]).subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
  } finally { removeTemp(folder); }
});

test('failed batch closes the active page and browser', async () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-error-'));
  try {
    const {chromium, stats} = fakeChromium(1);
    await assert.rejects(R.runJobs([job({out: path.join(folder, 'a.png')}), job({out: path.join(folder, 'b.png')})], chromium), /render failure/);
    assert.deepEqual(stats, {launches: 1, pages: 2, closedPages: 2, closedBrowsers: 1});
  } finally { removeTemp(folder); }
});

test('texture sheet marks used assets while retaining flipbook grid', async () => {
  const previous = global.document, labels = [];
  let lines = 0;
  const context = {fillRect() {}, drawImage() {}, fillText(text) { labels.push(text); },
    beginPath() {}, moveTo() {}, lineTo() { lines++; }, stroke() {}};
  global.document = {createElement: () => ({getContext: () => context, toDataURL: () => PNG})};
  try {
    await E.renderTextureSheet([{id: '123', label: 'Used texture', used: true, grid: 4}, {id: '456', label: 'Available'}]);
    assert.equal(labels.filter(text => text === 'USED').length, 1);
    assert.equal(lines, 6, '4x4 grid contains three lines per axis');
    assert.ok(labels.includes('123') && labels.includes('456'));
  } finally { if (previous === undefined) delete global.document; else global.document = previous; }
});

test('real Chromium CLI renders focus, fallback and Bulbito Part/emitter/legacy fits in one launch', {timeout: 90000}, async t => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-real-'));
  try {
    const manifest = path.join(folder, 'batch.json');
    const muzzle = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/bulbito/A1_Muzzle.json'), 'utf8'));
    fs.writeFileSync(manifest, JSON.stringify({jobs: [
      {projects: [fixture()], out: path.join(folder, 'fit.png'), fit: 'near', times: [0.05], size: '80x60'},
      {projects: [fixture()], out: path.join(folder, 'focus.png'), focus: [10,4,0], radius: 2, times: [0.05], size: '80x60'},
      {projects: [muzzle], out: path.join(folder, 'muzzle.png'), fit: 'Muzzle', times: [0.02,0.06]},
      {projects: [muzzle], out: path.join(folder, 'flash.png'), fit: 'Flash', times: [0.02,0.06]},
      {projects: [muzzle], out: path.join(folder, 'all.png'), fit: 'Muzzle', fitAll: true, times: [0.02,0.06]},
    ]}));
    let result;
    try { result = await promisify(execFile)(process.execPath, [path.join(__dirname, 'fx_render.cjs'), '--batch', manifest], {timeout: 80000}); }
    catch (error) {
      if ((error.stderr || '').includes('Playwright est introuvable')) return t.skip('Playwright absent');
      if ((error.stderr || '').includes('inaccessible dans le bac à sable')) return t.skip('Playwright installé ; accès refusé par le bac à sable');
      throw error;
    }
    const output = JSON.parse(result.stdout);
    assert.equal(output.browser_launches, 1); assert.equal(output.jobs.length, 5);
    assert.deepEqual(output.jobs[0].camera.target, [3,2,0]);
    assert.deepEqual(output.jobs[1].camera.target, [10,4,0]);
    assert.match(output.jobs[0].warnings[0], /aucune particule vivante/);
    // Visible quad points determine the camera; a 3D box diagonal also counts
    // depth behind the Flash and is no longer a measure of its screen framing.
    assert.ok(cameraDistance(output.jobs[2]) < cameraDistance(output.jobs[3]) * 1.2);
    assert.ok(output.jobs[4].framing.bounds.radius > output.jobs[2].framing.bounds.radius * 1.5);
    for (const file of output.files) assert.ok(fs.statSync(file).size > 100);
  } finally { removeTemp(folder); }
});

test('real Chromium pixel regression: radius 3 fills 480x270 and Bulbito fit stays comparable', {timeout: 90000}, async t => {
  let playwright;
  try { playwright = R.loadPlaywright(); }
  catch (error) {
    if (/Playwright est introuvable/.test(error.message)) return t.skip('Playwright absent');
    if (/inaccessible dans le bac à sable/.test(error.message)) return t.skip('Playwright installé ; accès refusé par le bac à sable');
    throw error;
  }
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'dataky-render-pixels-'));
  const pixelHeights = [];
  const chromium = {launch: async options => {
    const browser = await playwright.chromium.launch(options);
    return {close: () => browser.close(), newPage: async () => {
      const page = await browser.newPage(), evaluate = page.evaluate.bind(page);
      page.evaluate = async (callback, payload) => {
        const result = await evaluate(callback, payload);
        pixelHeights.push(await evaluate(async frames => {
          return Promise.all(frames.map(async frame => {
            const image = new Image(); image.src = frame.image; await image.decode();
            const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
            const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
            const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
            let min = canvas.height, max = -1;
            for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
              const offset = (y * canvas.width + x) * 4;
              if (Math.max(pixels[offset], pixels[offset + 1], pixels[offset + 2]) > 12) { min = Math.min(min, y); max = Math.max(max, y); }
            }
            return max < min ? 0 : (max - min + 1) / canvas.height;
          }));
        }, result.frames));
        return result;
      };
      return page;
    }};
  }};
  try {
    const sphere = fixture();
    sphere.nodes = [{id: 'sphere', class: 'Part', properties: {Position: [0,0,0], Size: [6,6,6], Shape: 'Ball', Color: [1,1,1], Material: 'Neon'}}];
    const muzzle = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/bulbito/A1_Muzzle.json'), 'utf8'));
    const options = {background: 'noir', ground: false, size: '480x270', framesDir: folder};
    await R.runJobs([
      R.prepareJob({...options, projects: [sphere], out: path.join(folder, 'sphere.png'), times: [0], camera: [0,0,20,0,0,0], focus: [0,0,0], radius: 3}),
      R.prepareJob({...options, projects: [muzzle], out: path.join(folder, 'muzzle.png'), times: [0.02,0.06], fit: 'Muzzle'}),
      R.prepareJob({...options, projects: [muzzle], out: path.join(folder, 'flash.png'), times: [0.02,0.06], fit: 'Flash'}),
    ], chromium);
    assert.ok(pixelHeights[0][0] >= 0.75 && pixelHeights[0][0] <= 0.9, `sphere height ${pixelHeights[0][0]}`);
    for (let i = 0; i < 2; i++) {
      assert.ok(pixelHeights[1][i] >= 0.3, `Bulbito rendered effect height ${pixelHeights[1][i]}`);
      assert.ok(pixelHeights[1][i] >= pixelHeights[2][i] * 0.7, 'Muzzle remains comparable to Flash framing');
    }
  } finally { removeTemp(folder); }
});
