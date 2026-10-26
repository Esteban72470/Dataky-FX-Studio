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
  asset('Static'), asset('Unknown', {kind:'flipbook', grid:0}),
  asset('Preview only', {kind:'flipbook', grid:4, image_path:null}),
  asset('Broken', {kind:'flipbook', grid:2, image_path:'images/broken.svg'}),
  ...Array.from({length:100}, (_, i) => asset('Extra '+i)),
];
const catalog = {textures:records, beams:[asset('Beam', {kind:'beam'})], meshes:[asset('Mesh', {kind:'mesh'})]};
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
    const live = new Set(), interval = window.setInterval.bind(window), clear = window.clearInterval.bind(window);
    window.__flipbookTimers = live;
    window.setInterval = (fn, ms, ...args) => {const id=interval(fn,ms,...args);if(Math.abs(ms-62.5)<0.01)live.add(id);return id;};
    window.clearInterval = id => {live.delete(id);clear(id);};
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()), name = decodeURIComponent(url.pathname);
    const json = value => route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
    if(name === '/api/catalog') return json(catalog);
    if(name === '/api/catalog/summary') return json({revision:'fixture'});
    if(name === '/api/schema') return json({classes:{},limits:{duration:600}});
    if(name.startsWith('/api/')) return json({connected:false,enabled:false,blocks:[]});
    if(name.endsWith('broken.svg')) return route.fulfill({status:404,body:'missing'});
    if(name.endsWith('.svg')) {
      const grid = Number(name.match(/sheet-(\d+)/)?.[1] || 1);
      const rects = Array.from({length:grid*grid}, (_, i) => `<rect x="${i%grid*16}" y="${Math.floor(i/grid)*16}" width="16" height="16" fill="hsl(${i*37},80%,60%)"/>`).join('');
      return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="${grid*16}" height="${grid*16}">${rects}</svg>`});
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

for(const standalone of [false,true]) test((standalone ? 'offline' : 'editor')+' catalogue animates by default, persists opt-out and cleans up', {timeout:60000}, async t => {
  const {page,toggle,card,image,timers,visibility,errors,url} = await harness(t,standalone);
  assert.equal(await toggle.isChecked(),true);
  for(const grid of [2,4,8]) {
    assert.match(await image('Flipbook '+grid).getAttribute('src'),new RegExp('images/sheet-'+grid+'\\.svg$'));
    assert.equal(await image('Flipbook '+grid).evaluate(img => img.style.width),(grid*100)+'%');
  }
  await page.waitForFunction(() => [...document.images].some(img => img.alt==='Flipbook 2' && img.style.transform.includes('-')));
  assert.equal(await timers(),1,'all cards share one clock');
  for(const name of ['Static','Unknown','Preview only']) {
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
