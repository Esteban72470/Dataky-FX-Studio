'use strict';

// Exercise both catalogue UIs in Chromium with local spritesheets and no server.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {loadPlaywright} = require('./fx_render.cjs');
const ROOT = path.resolve(__dirname, '..');
const STORE = 'dataky-fx-studio.catalog-flipbooks.v1';
const asset = (name, fields = {}) => ({asset_id:name, name, kind:'static', tags:[], image_path:'images/still.svg', preview_path:'previews/still.svg', ...fields});
const records = [
  ...[2,4,8].map(grid => asset('Flipbook '+grid, {kind:'flipbook', grid, image_path:'images/sheet-'+grid+'.svg'})),
  asset('Custom 6x4', {asset_id:'79593708822934', aliases:['Old custom name'], kind:'flipbook', grid:0, grid_columns:6, grid_rows:4, grid_source:'verified', grid_review_status:'confirmed', grid_review_note:'Six columns and four rows observed.', image_path:'images/sheet-6x4.svg'}),
  asset('Static'), asset('Unknown', {kind:'flipbook', grid:0, grid_review_status:'unresolved', grid_review_note:'Source image unavailable.'}),
  asset('Single image', {kind:'flipbook', grid:0, grid_columns:1, grid_rows:1, grid_review_status:'single_image', grid_review_note:'Scattered bats without repeated cells.'}),
  asset('Preview only', {kind:'flipbook', grid:4, image_path:null}),
  asset('Broken', {kind:'flipbook', grid:2, image_path:'images/broken.svg'}),
  ...Array.from({length:100}, (_, i) => asset('Extra '+i)),
];
const catalog = {textures:records, beams:[asset('Beam', {kind:'beam'})], meshes:[asset('Mesh', {kind:'mesh'})]};
const schema = JSON.parse(execFileSync(process.env.DATAKY_TEST_PYTHON || 'python', ['-c',
  'import json; from fx_schema import SCHEMA; print(json.dumps(SCHEMA))'
], {cwd:__dirname, encoding:'utf8'}));
const gallery = execFileSync(process.env.DATAKY_TEST_PYTHON || 'python', ['-c',
  'import json,sys,tempfile; from pathlib import Path; from gallery import build_gallery; data=json.load(sys.stdin); tmp=tempfile.TemporaryDirectory(); page=build_gallery(data["textures"],Path(tmp.name),{},extra_collections={key:{"records":data[key],"summary":{}} for key in ("beams","meshes")}); sys.stdout.buffer.write(page.read_bytes()); tmp.cleanup()'
], {cwd:__dirname, input:JSON.stringify(catalog), encoding:'utf8'});

async function harness(t, standalone) {
  const browser = await loadPlaywright().chromium.launch({headless:true});
  t.after(() => browser.close());
  const page = await browser.newPage({viewport:{width:1400,height:1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.__hidden = false;
    Object.defineProperty(document, 'visibilityState', {get:() => window.__hidden ? 'hidden' : 'visible'});
    Object.defineProperty(document, 'hidden', {get:() => window.__hidden});
    const live = new Set(), callbacks = new Map(), interval = window.setInterval.bind(window), clear = window.clearInterval.bind(window);
    window.__flipbookTimers = live;
    window.__advanceFlipbooks = () => {for(const next of callbacks.values())next();};
    window.setInterval = (fn, ms, ...args) => {const id=interval(fn,ms,...args);if(Math.abs(ms-62.5)<0.01){live.add(id);callbacks.set(id,()=>fn(...args));}return id;};
    window.clearInterval = id => {live.delete(id);callbacks.delete(id);clear(id);};
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()), name = decodeURIComponent(url.pathname);
    const json = value => route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
    if(name === '/api/catalog') return json(catalog);
    if(name === '/api/catalog/summary') return json({revision:'fixture'});
    if(name === '/api/schema') return json(schema);
    if(name.startsWith('/api/')) return json({connected:false,enabled:false,blocks:[]});
    if(name.endsWith('broken.svg')) return route.fulfill({status:404,body:'missing'});
    if(name.endsWith('.svg')) {
      const layout = name.match(/sheet-(\d+)(?:x(\d+))?/), columns = Number(layout?.[1] || 1), rows = Number(layout?.[2] || columns);
      const rects = Array.from({length:columns*rows}, (_, i) => `<rect x="${i%columns*16}" y="${Math.floor(i/columns)*16}" width="16" height="16" fill="hsl(${i*37},80%,60%)"/>`).join('');
      return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="${columns*16}" height="${rows*16}">${rects}</svg>`});
    }
    if(name === '/library/catalogue.html') return route.fulfill({contentType:'text/html',body:gallery});
    // Unrelated authoring/video extensions are outside these catalogue tests.
    if(['/artistry.js','/video.js'].includes(name)) return route.fulfill({contentType:'text/javascript',body:''});
    const file = path.join(ROOT,'editor',name === '/' ? 'index.html' : name);
    const contentType = name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html';
    if(fs.existsSync(file)) return route.fulfill({contentType,body:fs.readFileSync(file)});
    return route.fulfill({status:404,body:'missing'});
  });
  const url = 'http://dataky.local'+(standalone ? '/library/catalogue.html' : '/');
  await page.goto(url);
  const toggle = page.getByLabel('Animer les flipbooks', {exact:true});
  const card = name => standalone ? page.getByRole('button',{name:'Voir '+name,exact:true}) : page.locator('.catalog-card').filter({has:page.locator('img[alt="'+name+'"]')});
  const image = name => card(name).locator('img');
  await image('Flipbook 2').waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll('img')].some(img => img.alt==='Flipbook 2' && img.complete && img.naturalWidth));
  const timers = () => page.evaluate(() => window.__flipbookTimers.size);
  const visibility = hidden => page.evaluate(value => {window.__hidden=value;document.dispatchEvent(new Event('visibilitychange'));},hidden);
  return {page,toggle,card,image,timers,visibility,errors,url};
}

async function assertCustomFrames(image) {
  await image.evaluate(img => img.complete && img.naturalWidth || new Promise(resolve => img.addEventListener('load',resolve,{once:true})));
  assert.match(await image.getAttribute('src'),/images\/sheet-6x4\.svg$/,'animation uses the full atlas');
  assert.deepEqual(await image.evaluate(img => [img.style.width,img.style.height]),['600%','400%'],'six columns and four rows have separate crop scales');
  const frames = await image.evaluate(img => {
    const current = () => {const values=(img.style.transform||'translate(0%,0%)').match(/-?\d+(?:\.\d+)?/g).map(Number);return Math.round(-values[1]*4/100)*6+Math.round(-values[0]*6/100)+0;};
    const values=[current()];for(let i=0;i<70;i++){window.__advanceFlipbooks();values.push(current());}return values;
  });
  for(let i=1;i<frames.length;i++)assert.equal(frames[i],(frames[0]+i)%24,'custom atlas advances all 24 cells continuously beyond 64 ticks');
}

for(const standalone of [false,true]) test((standalone ? 'offline' : 'editor')+' catalogue animates by default, persists opt-out and cleans up', {timeout:60000}, async t => {
  const {page,toggle,card,image,timers,visibility,errors,url} = await harness(t,standalone);
  assert.equal(await toggle.isChecked(),true);
  for(const grid of [2,4,8]) {
    assert.match(await image('Flipbook '+grid).getAttribute('src'),new RegExp('images/sheet-'+grid+'\\.svg$'));
    assert.equal(await image('Flipbook '+grid).evaluate(img => img.style.width),(grid*100)+'%');
  }
  await page.waitForFunction(() => [...document.images].some(img => img.alt==='Flipbook 2' && img.style.transform.includes('-')));
  assert.equal(await timers(),1,'all cards share one clock');
  await assertCustomFrames(image('Custom 6x4'));
  const search = page.locator(standalone ? '#search' : '#catalog-search');
  await search.fill('Old custom name');
  await image('Custom 6x4').waitFor();
  await page.waitForFunction(() => document.querySelectorAll('.catalog-card,.card').length===1);
  await search.fill('');
  await image('Flipbook 2').waitFor();
  for(const name of ['Static','Unknown','Preview only','Single image']) {
    assert.equal(await image(name).evaluate(img => img.style.transform),'');
    assert.match(await image(name).getAttribute('src'),/previews\/still\.svg$/);
  }
  await visibility(true);
  assert.equal(await timers(),0,'hidden documents release the clock');
  await visibility(false);
  assert.equal(await timers(),1);
  await toggle.uncheck();
  assert.equal(await timers(),0);
  assert.equal(await image('Flipbook 2').evaluate(img => img.style.transform),'');
  assert.match(await image('Flipbook 2').getAttribute('src'),/previews\/still\.svg$/);
  await page.reload();
  await image('Flipbook 2').waitFor();
  assert.equal(await toggle.isChecked(),false,'opt-out survives reload');
  assert.equal(await page.evaluate(key => localStorage.getItem(key),STORE),'false');
  await toggle.check();
  assert.equal(await timers(),1);

  if(standalone) {
    assert.equal(await card('Custom 6x4').locator('.kind').textContent(),'FLIPBOOK 6 × 4');
    await card('Custom 6x4').click();
    await assertCustomFrames(page.locator('#detail-image'));
    assert.match(await page.locator('#detail-meta').textContent(),/6 × 4 \(24 images\).*Disposition vérifiée visuellement/);
    assert.doesNotMatch(await page.locator('#detail-meta').textContent(),/estimé/);
    await page.locator('#close').click();
    await card('Unknown').click();
    assert.equal(await page.locator('#animate').isHidden(),true);
    assert.match(await page.locator('#detail-meta').textContent(),/Disposition inconnue.*Source image unavailable/);
    await page.locator('#close').click();
    await card('Single image').click();
    assert.equal(await page.locator('#animate').isHidden(),true);
    assert.match(await page.locator('#detail-meta').textContent(),/Image unique observée.*Scattered bats/);
    await page.locator('#close').click();
    await card('Flipbook 2').click();
    assert.equal(await page.locator('#preview').evaluate(node => node.classList.contains('animating')),true,'details autoplay');
    assert.equal(await timers(),1,'detail replaces the thumbnail clock');
    await page.locator('#animate').click();
    assert.equal(await timers(),0,'manual pause still works');
    await page.locator('#close').click();
    await page.waitForFunction(() => window.__flipbookTimers.size === 1);
    assert.equal(await timers(),1);
    await page.locator('#kind').selectOption('static');
    assert.equal(await timers(),0);
    await page.locator('#kind').selectOption('');
    await page.locator('#next').click();
    assert.equal(await timers(),0,'no detached cards keep running after pagination');
    await page.locator('#tab-meshes').click();
    assert.equal(await timers(),0);
    await page.locator('#tab-textures').click();
    await page.locator('#prev').click();
  } else {
    await card('Custom 6x4').click();
    await page.locator('#use-resource').click();
    const custom = await page.evaluate(() => window.DatakyFX.getProject().nodes.find(node=>node.class==='ParticleEmitter'));
    assert.equal(custom.properties.FlipbookLayout,'Custom');
    assert.equal(custom.properties.FlipbookSizeX,6);
    assert.equal(custom.properties.FlipbookSizeY,4);
    assert.equal(custom.properties.Texture,'rbxassetid://79593708822934');
    await card('Single image').click();
    await page.locator('#use-resource').click();
    assert.equal(await page.evaluate(() => window.DatakyFX.getProject().nodes.find(node=>node.class==='ParticleEmitter').properties.FlipbookLayout),'None','single images clear the previous atlas layout');
    await card('Flipbook 2').click();
    assert.equal(await timers(),1,'selection recreates only one clock');
    await page.locator('#catalog-search').fill('Static');
    assert.equal(await timers(),0);
    await page.locator('#clear-filters').click();
    await page.locator('#catalog-next').click();
    assert.equal(await timers(),0,'pagination releases old cards');
    await page.locator('[data-collection="meshes"]').click();
    assert.equal(await timers(),0);
    await page.locator('[data-collection="textures"]').click();
    await page.locator('#catalog-prev').click();
  }
  assert.equal(await timers(),1);
  await page.goto(url);
  await image('Flipbook 2').waitFor();
  assert.equal(await toggle.isChecked(),true,'re-enabled preference survives reload');
  assert.deepEqual(errors,[]);
});
