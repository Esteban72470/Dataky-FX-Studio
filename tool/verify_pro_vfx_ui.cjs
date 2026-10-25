/* Read-only integration check through the real local editor and its controls. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {loadPlaywright} = require('./fx_render.cjs');
const ROOT = path.resolve(__dirname, '..');

async function main() {
  const browser = await loadPlaywright().chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
  try {
    const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
    const errors = [], blockedWrites = [];
    page.on('pageerror', e => errors.push(e.message));
    // A preview check must never create objects in a connected Studio, or save
    // changes to the library. UI project selection changes this isolated tab.
    await page.route('**/api/**', route => {
      if (route.request().method() === 'GET') return route.continue();
      blockedWrites.push({url: route.request().url(), method: route.request().method()});
      return route.fulfill({status: 403, contentType: 'application/json', body: JSON.stringify({error: 'Read-only UI verification'})});
    });
    await page.goto(process.env.DATAKY_TEST_URL || 'http://127.0.0.1:48754/');
    await page.waitForFunction(() => window.DatakyFX?.getSchema()?.classes && document.querySelectorAll('.artistry-demo').length === 6);
    for (const [id, label, peak] of [['CelestialRiftSlash','Celestial Rift Slash',.32],['SolarSpear','Solar Spear',.42],['PhantomBloom','Phantom Bloom',.53]]) {
      await page.locator('#artistry-button').click();
      await page.locator('#artistry-dialog[open]').waitFor();
      await page.locator('[data-art-tab="demos"]').click();
      await page.locator('.artistry-demo').filter({hasText: label}).click();
      await page.waitForFunction(id => window.DatakyFX.getProject().id === id && !document.querySelector('#artistry-dialog').open, id);
      await page.locator('#view-emu').click();
      await page.locator('#emu-camera').click();
      await page.evaluate(peak => window.DatakyFX.emulator.seek(peak), peak);
      await page.waitForFunction(() => /particul/i.test(document.querySelector('#emu-status').textContent));
      await page.screenshot({path: path.join(ROOT, 'rendus/pro', id, 'editor-final.png')});
      const source = JSON.parse(fs.readFileSync(path.join(ROOT, 'editor/projects', id + '.json'), 'utf8'));
      assert.equal(await page.evaluate(() => JSON.stringify(window.DatakyFX.getProject())), JSON.stringify(source));
      await page.evaluate(() => window.DatakyFX.emulator.play());
      await page.waitForFunction(() => Number(document.querySelector('#playhead-time').value) > .15, null, {timeout: 5000});
      await page.evaluate(() => window.DatakyFX.emulator.stop());
      console.log(JSON.stringify({id, openedFromDemo: true, unchangedRecipe: true, playbackStarted: true}));
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(blockedWrites, [], 'UI preview attempted a mutation');
    console.log('PRO_UI_OK');
  } finally {await browser.close();}
}
main().catch(e => {console.error(e); process.exitCode = 1;});
