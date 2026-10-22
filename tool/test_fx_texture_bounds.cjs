'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const R = require('./fx_render.cjs');
const E = require('../editor/emulator.js');

const whole = [[0,0],[1,0],[0,1],[1,1]];

test('particle texture bounds preserve full half-size when browser pixels are unavailable', async () => {
  const bounds = await E.textureAlphaBounds([{nodes: [{class: 'ParticleEmitter', properties: {Texture: 'rbxassetid://123'}}]}]);
  assert.deepEqual(bounds('rbxassetid://123', whole), {min: [0,0], max: [1,1]});
  assert.deepEqual(bounds.points('rbxassetid://123', whole), [[0,0],[1,0],[1,1],[0,1]]);
});

test('real Chromium texture bounds follow active flipbook alpha and keep faint opaque support', {timeout: 30000}, async t => {
  let playwright;
  try { playwright = R.loadPlaywright(); }
  catch (error) {
    if (/Playwright est introuvable/.test(error.message)) return t.skip('Playwright absent');
    if (/inaccessible dans le bac à sable/.test(error.message)) return t.skip('Playwright installé ; accès refusé par le bac à sable');
    throw error;
  }
  const browser = await playwright.chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => {
      const file = R.routeFile(route.request().url());
      if (!file || !fs.existsSync(file)) return route.fulfill({status: 404, body: ''});
      return route.fulfill({status: 200, contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'image/png', body: fs.readFileSync(file)});
    });
    await page.goto('http://dataky.local/render.html');
    await page.waitForFunction(() => window.DatakyEmulator);
    const result = await page.evaluate(async () => {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 16;
      const context = canvas.getContext('2d'); context.fillStyle = '#fff';
      context.fillRect(2,2,2,2); context.fillRect(13,5,1,1);
      context.fillStyle = 'rgba(255,255,255,0.00392156862745098)'; context.fillRect(12,12,1,1);
      const uri = 'rbxassetid://123', project = {nodes: [{class: 'ParticleEmitter', properties: {Texture: uri}}]};
      const bounds = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png')});
      const cell = index => [[0,0],[1,0],[0,1],[1,1]].map(([u,v]) => [(index % 2 + u) / 2, (Math.floor(index / 2) + v) / 2]);
      const fixture = await window.DatakyEmulator.textureAlphaBounds([{nodes: [{class: 'ParticleEmitter', properties: {Texture: 'rbxassetid://75545411897437'}}]}]);
      context.clearRect(0,0,16,16); context.fillStyle = '#fff';
      for (let i = 1; i < 15; i++) context.fillRect(i,i,1,1);
      const diagonal = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png')});
      context.clearRect(0,0,16,16); context.fillStyle = '#fff'; context.fillRect(3,3,2,2);
      context.fillStyle = 'rgba(255,255,255,0.00392156862745098)'; context.fillRect(14,14,1,1);
      const mass90 = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png'), alphaPercentile: 90});
      const mass100 = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png'), alphaPercentile: 100});
      context.clearRect(0,0,16,16); context.fillStyle = '#fff'; context.fillRect(3,3,2,2);
      context.fillStyle = 'rgba(255,255,255,0.25098039215686274)'; context.fillRect(13,13,2,2);
      const linear = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png'), alphaPercentile: 90});
      const energy = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png'), alphaPercentile: 90, alphaPower: 2});
      context.clearRect(0,0,16,16); context.fillStyle = 'rgba(255,255,255,0.01568627450980392)'; context.fillRect(3,3,2,2);
      context.fillStyle = 'rgba(255,255,255,0.00392156862745098)'; context.fillRect(13,13,2,2);
      const faintEnergy = await window.DatakyEmulator.textureAlphaBounds([project], {resolveTexture: () => canvas.toDataURL('image/png'), alphaPercentile: 90, alphaPower: 2});
      const full = [[0,0],[1,0],[0,1],[1,1]];
      return {
        first: bounds(uri, cell(0), cell(1), 0), blended: bounds(uri, cell(0), cell(1), 0.5),
        next: bounds(uri, cell(0), cell(1), 1), empty: bounds(uri, cell(2)), faint: bounds(uri, cell(3)),
        missing: bounds('rbxassetid://999', cell(0)),
        emptyPoints: bounds.points(uri, cell(2)), faintPoints: bounds.points(uri, cell(3)),
        diagonalPoints: diagonal.points(uri, [[0,0],[1,0],[0,1],[1,1]]),
        mass90: mass90(uri, full), mass100: mass100(uri, full),
        linear: linear(uri, full), energy: energy(uri, full), faintEnergy: faintEnergy(uri, full),
        fixture: fixture('rbxassetid://75545411897437', [[0.75,0],[1,0],[0.75,0.25],[1,0.25]]),
      };
    });
    assert.deepEqual(result.first, {min: [0.125,0.125], max: [0.625,0.625]});
    assert.deepEqual(result.blended, {min: [0.125,0.125], max: [0.875,0.875]});
    assert.deepEqual(result.next, {min: [0.5,0.5], max: [0.875,0.875]});
    assert.equal(result.empty, null);
    assert.deepEqual(result.faint, {min: [0.375,0.375], max: [0.75,0.75]});
    assert.deepEqual(result.missing, {min: [0,0], max: [1,1]});
    assert.equal(result.emptyPoints, null);
    assert.equal(result.faintPoints.length, 4);
    assert.ok(result.diagonalPoints.length >= 4);
    assert.ok(result.diagonalPoints.every(([u,v]) => Math.abs(u-v) <= 3/16), 'diagonal contour excludes the empty corners of its enclosing square');
    assert.deepEqual(result.mass90, {min: [0.125,0.125], max: [0.375,0.375]}, 'alpha mass percentile rejects a distant negligible texel');
    assert.deepEqual(result.mass100, {min: [0.125,0.125], max: [1,1]}, '100 percent retains the distant texel');
    assert.deepEqual(result.linear.max, [1,1]);
    assert.deepEqual(result.energy, {min: [0.125,0.125], max: [0.375,0.375]}, 'contrast energy suppresses a weak detached halo');
    assert.deepEqual(result.faintEnergy, result.energy, 'normalizing contrast energy preserves the same geometry for faint assets');
    assert.ok(result.fixture.max[0] - result.fixture.min[0] < 0.25, 'Bulbito first flash frames retain their actual narrow alpha support');
  } finally { await browser.close(); }
});
