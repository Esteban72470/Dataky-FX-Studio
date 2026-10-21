'use strict';

// Evaluate the real editor definitions in isolation, never a copied template.
// Startup is intercepted before DOM handlers, network, timers, or persistence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');

function readSchema(args) {
  const schemaIndex = args.indexOf('--schema');
  if (schemaIndex >= 0) {
    assert.ok(args[schemaIndex + 1], '--schema requires a JSON file');
    return JSON.parse(fs.readFileSync(args[schemaIndex + 1], 'utf8'));
  }
  const python = process.env.DATAKY_TEST_PYTHON || 'python';
  return JSON.parse(execFileSync(python, ['-c', 'import json; from fx_schema import SCHEMA; print(json.dumps(SCHEMA))'], {cwd: __dirname, encoding: 'utf8'}));
}

function loadEditor(schema) {
  const filename = path.resolve(__dirname, '../editor/app.js');
  const source = fs.readFileSync(filename, 'utf8');
  const marker = '  if(!Array.isArray(project.animations))project.animations=[];';
  assert.equal(source.split(marker).length, 2, 'Editor startup interception point must be unique');
  const intercepted = source.replace(marker, `
  globalThis.__DatakyTest = {template, defaults, validateProject, pointsOf, sequenceArray, getSchema:()=>schema};
  return;
${marker}`);
  const cache = new Map([['dataky-fx-studio.schema.v1', JSON.stringify(schema)]]);
  let unsafeCalls = 0;
  function forbidden() { unsafeCalls++; throw new Error('Pure editor test attempted UI, network, or timer work'); }
  const sandbox = {
    crypto, console: {log() {}, warn() {}, error() {}}, window: {},
    document: {querySelector: forbidden, querySelectorAll: forbidden, createElement: forbidden, addEventListener: forbidden},
    localStorage: {getItem: key => cache.get(key) || null, setItem: forbidden, removeItem: forbidden},
    fetch: forbidden, setTimeout: forbidden, setInterval: forbidden,
  };
  vm.createContext(sandbox);
  vm.runInContext(intercepted, sandbox, {filename, timeout: 3000});
  assert.equal(unsafeCalls, 0, 'Pure bootstrap must not enter app initialization');
  assert.ok(sandbox.__DatakyTest, 'Editor pure functions were exposed');
  return sandbox.__DatakyTest;
}

const plain = value => JSON.parse(JSON.stringify(value));
function run(schema) {
  const editor = loadEditor(schema);
  const fixtures = {};
  for (const kind of ['empty', 'impact', 'smoke', 'beam', 'trail']) {
    const effect = plain(editor.template(kind));
    assert.equal(effect.version, 1);
    assert.equal(typeof effect.name, 'string');
    assert.ok(effect.duration > 0);
    assert.equal(new Set(effect.nodes.map(node => node.id)).size, effect.nodes.length, kind + ': unique IDs');
    assert.deepEqual(plain(editor.validateProject(effect)), effect, kind + ': frontend validation keeps recipe');
    const nodes = new Map(effect.nodes.map(node => [node.id, node]));
    for (const node of effect.nodes) {
      assert.ok(schema.classes[node.class], kind + ': supported class');
      if (node.parent) assert.ok(nodes.has(node.parent), kind + ': internal parent');
      for (const key of Object.keys(node.properties)) assert.ok(schema.classes[node.class].properties[key], kind + ': known property ' + key);
      if (node.class === 'Attachment') {
        assert.ok(!(Object.hasOwn(node.properties, 'Orientation') && (Object.hasOwn(node.properties, 'Axis') || Object.hasOwn(node.properties, 'SecondaryAxis'))), kind + ': axis/orientation conflict');
      }
      if (node.class === 'Beam' || node.class === 'Trail') {
        for (const key of ['Attachment0', 'Attachment1']) assert.equal(nodes.get(node.properties[key])?.class, 'Attachment', kind + ': endpoint reference');
        assert.notEqual(node.properties.Attachment0, node.properties.Attachment1);
      }
      if (node.class === 'ParticleEmitter') assert.equal(nodes.get(node.parent)?.class, 'Attachment', kind + ': point emission');
    }
    fixtures[kind] = effect;
  }
  assert.equal(fixtures.empty.nodes.length, 0);
  const impact = fixtures.impact;
  const impactSource = impact.nodes.find(node => node.class === 'Part');
  assert.deepEqual(impactSource.properties.Position, [0, 1, 0]);
  assert.equal(impact.nodes.find(node => node.class === 'ParticleEmitter').timing.mode, 'burst');
  assert.equal(impact.nodes.find(node => node.class === 'PointLight').parent, impact.nodes.find(node => node.class === 'Attachment').id);
  assert.equal(fixtures.smoke.nodes.find(node => node.class === 'ParticleEmitter').timing.mode, 'continuous');
  const beam = fixtures.beam.nodes.find(node => node.class === 'Beam');
  const beamNodes = new Map(fixtures.beam.nodes.map(node => [node.id, node]));
  assert.deepEqual(beamNodes.get(beam.properties.Attachment0).properties.Position, [-3, 0, 0]);
  assert.deepEqual(beamNodes.get(beam.properties.Attachment1).properties.Position, [3, 0, 0]);
  // CurveSize moves the Bézier control points along +X of Attachment0 and -X of Attachment1: the Arc must bend.
  const emulator = require('../editor/emulator.js');
  const arc = emulator.buildFrame(emulator.createSimulation(plain(fixtures.beam)), fixtures.beam.camera);
  const arcTop = Math.max(...Array.from({length: arc.vertices}, (_, i) => arc.data[i * 13 + 1]));
  assert.ok(arcTop > 2.5, 'beam template arcs above its attachments, peak ' + arcTop);
  const movement = fixtures.trail.animations[0];
  assert.equal(movement.node, fixtures.trail.nodes.find(node => node.class === 'Part').id);
  assert.equal(movement.property, 'Position');
  assert.deepEqual(movement.keyframes.map(frame => frame.time), [0, 1, 2]);
  assert.notDeepEqual(movement.keyframes[0].value, movement.keyframes[2].value);

  const attachmentDefaults = plain(editor.defaults('Attachment'));
  assert.ok(Object.hasOwn(attachmentDefaults, 'Orientation'));
  assert.ok(!Object.hasOwn(attachmentDefaults, 'Axis'));
  assert.ok(!Object.hasOwn(attachmentDefaults, 'SecondaryAxis'));
  for (const [cls, spec] of Object.entries(schema.classes)) {
    const defaults = plain(editor.defaults(cls));
    for (const [key, prop] of Object.entries(spec.properties)) {
      if (prop.omitOnCreate) assert.ok(!Object.hasOwn(defaults, key));
      else if (Object.hasOwn(prop, 'default')) assert.deepEqual(defaults[key], prop.default);
    }
  }

  const numberPoints = plain(editor.pointsOf([[1, 0, 0.2], [0, 2, 0.1]], 'NumberSequence'));
  assert.deepEqual(numberPoints.map(point => point.time), [0, 1]);
  assert.deepEqual(plain(editor.sequenceArray(numberPoints, 'NumberSequence')), [{time: 0, value: 2, envelope: 0.1}, {time: 1, value: 0, envelope: 0.2}]);
  const colorPoints = [{time: 0, value: [1, 0, 0]}, {time: 1, value: [0, 0, 1]}];
  assert.deepEqual(plain(editor.sequenceArray(editor.pointsOf(colorPoints, 'ColorSequence'), 'ColorSequence')), colorPoints);

  for (const mutate of [
    value => { value.nodes[1].id = value.nodes[0].id; },
    value => { value.nodes[1].parent = 'missing'; },
    value => { value.nodes[0].parent = value.nodes[1].id; },
    value => { value.duration = 0; },
    value => { value.nodes[0].class = 'Script'; },
  ]) {
    const invalid = structuredClone(impact);
    mutate(invalid);
    assert.throws(() => editor.validateProject(invalid), 'Editor must refuse invalid recipe structure');
  }
  // Unsupported explicit values reach authoritative backend validation; they
  // must not silently vanish in the browser before an error can be reported.
  const advanced = structuredClone(impact);
  advanced.nodes[0].properties.FutureUnknownProperty = 123;
  assert.equal(editor.validateProject(advanced).nodes[0].properties.FutureUnknownProperty, 123);
  return fixtures;
}

const args = process.argv.slice(2);
const fixtures = run(readSchema(args));
if (args.includes('--fixtures')) process.stdout.write(JSON.stringify(fixtures));
else process.stdout.write('PASS: five real editor templates, native schema defaults, references, motion, sequence codecs, frontend invalid-input checks.\n');
