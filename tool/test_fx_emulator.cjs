'use strict';

// Simulation and geometry of the browser emulator, without WebGL. The WebGL path is
// exercised by tool/fx_render.cjs in a real Chromium.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const E = require('../editor/emulator.js');

const near = (actual, expected, epsilon = 1e-6, label = '') => {
  const a = [].concat(actual), b = [].concat(expected);
  assert.equal(a.length, b.length, label);
  a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) <= epsilon, `${label} [${i}] ${v} ≠ ${b[i]}`));
};
const column = (m, i) => [m[i], m[3 + i], m[6 + i]];
const sequence = value => [{time: 0, value, envelope: 0}, {time: 1, value, envelope: 0}];

function project(nodes, extra = {}) {
  return {version: 1, name: 'Test', duration: 2, loop: false, nodes, animations: [], camera: {position: [0, 2, 20], target: [0, 2, 0]}, ...extra};
}
const part = (id, properties = {}) => ({id, class: 'Part', name: id, parent: null, properties: {Position: [0, 2, 0], Size: [2, 2, 2], Transparency: 1, ...properties}});
const attachment = (id, parent, properties = {}) => ({id, class: 'Attachment', name: id, parent, properties});
const emitter = (id, parent, properties = {}, timing) => ({id, class: 'ParticleEmitter', name: id, parent,
  properties: {Rate: 0, Speed: [4, 4], Lifetime: [1, 1], Size: sequence(1), Transparency: sequence(0), ...properties}, ...(timing ? {timing} : {})});

test('orientation follows CFrame.fromOrientation (Y, then X, then Z)', () => {
  near(column(E.fromOrientation([0, 90, 0]), 0), [0, 0, -1], 1e-9, 'yaw 90 RightVector');
  near(column(E.fromOrientation([90, 0, 0]), 1), [0, 0, 1], 1e-9, 'pitch 90 UpVector');
  near(column(E.fromOrientation([90, 90, 0]), 1), [1, 0, 0], 1e-9, 'pitch then yaw UpVector');
});

test('attachments inherit their part transform and Axis/SecondaryAxis are honoured', () => {
  const sim = E.createSimulation(project([
    part('p', {Position: [1, 2, 3], Orientation: [0, 90, 0]}),
    attachment('a', 'p', {Position: [2, 0, 0]}),
    attachment('b', 'p', {Axis: [0, 1, 0], SecondaryAxis: [-1, 0, 0]}),
  ]));
  const a = sim.frameOf(sim.byId.get('a'));
  near(a.p, [1, 2, 1], 1e-9, 'offset rotated by the part');
  const b = sim.frameOf(sim.byId.get('b'));
  near(column(b.m, 0), column(E.fromOrientation([0, 90, 0]), 1), 1e-9, 'Axis in part space');
});

test('same seed gives the same frame whatever the seek history; another seed differs', () => {
  const recipe = project([part('p'), emitter('e', 'p', {Rate: 40, Speed: [2, 6], SpreadAngle: [40, 40], Lifetime: [0.5, 1.5]})]);
  const a = E.createSimulation(recipe, {seed: 7}), b = E.createSimulation(recipe, {seed: 7}), c = E.createSimulation(recipe, {seed: 8});
  a.seek(1.2); b.seek(0.4); b.seek(1.6); b.seek(1.2); c.seek(1.2);
  const positions = sim => sim.emitters[0].particles.map(p => p.p.map(v => v.toFixed(6)).join(',')).join(';');
  assert.ok(a.stats().particles > 20);
  assert.equal(positions(a), positions(b));
  assert.notEqual(positions(a), positions(c));
});

test('burst fires once at its start, like Emit(count), and particles expire after Lifetime', () => {
  const sim = E.createSimulation(project([part('p'), emitter('e', 'p', {}, {start: 0.5, duration: 0.1, mode: 'burst', count: 12})]));
  sim.seek(0.48); assert.equal(sim.stats().particles, 0);
  sim.seek(0.5); assert.equal(sim.stats().particles, 12);
  assert.ok(sim.emitters[0].particles.every(p => p.age === 0), 'burst particles start at age 0');
  sim.seek(1.2); assert.equal(sim.stats().particles, 12);
  sim.seek(1.55); assert.equal(sim.stats().particles, 0);
});

test('continuous timing emits at Rate only inside its window', () => {
  const sim = E.createSimulation(project([part('p'), emitter('e', 'p', {Rate: 50, Lifetime: [5, 5]}, {start: 0.5, duration: 1, mode: 'continuous'})], {duration: 3}));
  sim.seek(0.45); assert.equal(sim.stats().particles, 0);
  sim.seek(1.5); const emitted = sim.stats().particles;
  assert.ok(emitted >= 48 && emitted <= 51, `about 50 particles, got ${emitted}`);
  sim.seek(2.5); assert.equal(sim.stats().particles, emitted, 'no emission after the window');
});

test('loop clears particles and restarts bursts; a finished effect lets particles fade out', () => {
  const nodes = [part('p'), emitter('e', 'p', {Lifetime: [3, 3]}, {start: 0, duration: 0.1, mode: 'burst', count: 5})];
  const looping = E.createSimulation(project(nodes, {duration: 1, loop: true}));
  looping.seek(0.99); assert.equal(looping.stats().particles, 5);
  looping.seek(1.2); assert.equal(looping.stats().particles, 5, 'cleared then emitted again');
  assert.ok(looping.emitters[0].particles.every(p => p.age < 0.3));
  const once = E.createSimulation(project(nodes, {duration: 1}));
  once.seek(1.5);
  assert.equal(once.ended, true);
  assert.equal(once.stats().particles, 5, 'existing particles keep living');
  assert.equal(once.time, 1);
});

test('emission direction, speed, acceleration and drag', () => {
  const sim = E.createSimulation(project([part('p', {Size: [0.001, 0.001, 0.001]}),
    emitter('e', 'p', {EmissionDirection: 'Right', Acceleration: [0, -10, 0], Drag: 1, Lifetime: [5, 5]}, {start: 0, duration: 0.1, mode: 'burst', count: 1})]));
  sim.seek(1);
  const particle = sim.emitters[0].particles[0];
  near(particle.v0, [2, 0, 0], 1e-6, 'emission speed halves after 1 s with Drag 1');
  near(particle.va, [0, -10, 0], 1e-6, 'acceleration is not dragged');
  assert.ok(particle.p[0] > 2.5 && particle.p[0] < 3.1, 'travelled along +X');
});

test('sphere shape with ShapePartial 0.5 emits from the upper half only', () => {
  const sim = E.createSimulation(project([part('p', {Size: [4, 4, 4]}),
    emitter('e', 'p', {Shape: 'Sphere', ShapeStyle: 'Surface', ShapePartial: 0.5, Speed: [0, 0]}, {start: 0, duration: 0.1, mode: 'burst', count: 200})]));
  for (const particle of sim.emitters[0].particles) {
    assert.ok(particle.p[1] >= 2 - 1e-6, 'above the equator');
    near(Math.hypot(particle.p[0], particle.p[1] - 2, particle.p[2]), 2, 1e-6, 'on the surface');
  }
});

test('size and transparency envelopes stay within the declared range', () => {
  const sim = E.createSimulation(project([part('p'), emitter('e', 'p', {Size: [{time: 0, value: 2, envelope: 0.5}, {time: 1, value: 2, envelope: 0.5}]},
    {start: 0, duration: 0.1, mode: 'burst', count: 100})]));
  const sizes = sim.emitters[0].particles.map(p => E.sampleNumber([{time: 0, value: 2, envelope: 0.5}, {time: 1, value: 2, envelope: 0.5}], 0.5, p.size));
  assert.ok(sizes.every(v => v >= 1.5 && v <= 2.5));
  assert.ok(Math.max(...sizes) - Math.min(...sizes) > 0.5, 'envelope varies per particle');
});

test('particle quads: one quad per visible particle, LightEmission and transparency in vertices', () => {
  const sim = E.createSimulation(project([part('p'), emitter('e', 'p', {LightEmission: 1, Transparency: sequence(0.25), Speed: [0, 0]},
    {start: 0, duration: 0.1, mode: 'burst', count: 3})]));
  const frame = E.buildFrame(sim, sim.project.camera);
  assert.equal(frame.vertices, 18);
  assert.equal(frame.batches.length, 1);
  for (let i = 0; i < frame.vertices; i++) {
    near(frame.data[i * 13 + 10], 0.75, 1e-6, 'alpha');
    near(frame.data[i * 13 + 12], 1, 1e-6, 'LightEmission');
  }
});

test('flipbook Grid4x4 OneShot starts in the first cell and ends in the last', () => {
  const recipe = project([part('p'), emitter('e', 'p', {FlipbookLayout: 'Grid4x4', FlipbookMode: 'OneShot', Speed: [0, 0], Lifetime: [1, 1]},
    {start: 0, duration: 0.1, mode: 'burst', count: 1})]);
  const sim = E.createSimulation(recipe);
  const uvs = () => { const f = E.buildFrame(sim, recipe.camera); return Array.from({length: 6}, (_, i) => [f.data[i * 13 + 3], f.data[i * 13 + 4]]); };
  assert.ok(uvs().every(([u, v]) => u <= 0.25 + 1e-9 && v <= 0.25 + 1e-9));
  sim.seek(0.99);
  assert.ok(uvs().every(([u, v]) => u >= 0.75 - 1e-9 && v >= 0.75 - 1e-9));
});

test('beam follows its attachments; without FaceCamera its width follows their UpVector', () => {
  const recipe = project([part('p', {Position: [0, 0, 0]}), attachment('a0', 'p', {Position: [-3, 0, 0]}), attachment('a1', 'p', {Position: [3, 0, 0]}),
    {id: 'b', class: 'Beam', name: 'b', parent: 'p', properties: {Attachment0: 'a0', Attachment1: 'a1', Width0: 2, Width1: 2, Segments: 4, Transparency: sequence(0)}}]);
  const sim = E.createSimulation(recipe);
  const frame = E.buildFrame(sim, recipe.camera);
  assert.equal(frame.vertices, 4 * 6);
  const points = Array.from({length: frame.vertices}, (_, i) => [frame.data[i * 13], frame.data[i * 13 + 1], frame.data[i * 13 + 2]]);
  near(Math.min(...points.map(p => p[0])), -3, 1e-9, 'starts at Attachment0');
  near(Math.max(...points.map(p => p[0])), 3, 1e-9, 'ends at Attachment1');
  near(Math.max(...points.map(p => Math.abs(p[1]))), 1, 1e-9, 'half width along Y');
  near(Math.max(...points.map(p => Math.abs(p[2]))), 0, 1e-9, 'flat in the XY plane');
});

test('beam curve control points follow +X of Attachment0 and -X of Attachment1', () => {
  const recipe = project([part('p', {Position: [0, 0, 0]}), attachment('a0', 'p', {Position: [-3, 0, 0], Orientation: [0, 0, 90]}), attachment('a1', 'p', {Position: [3, 0, 0], Orientation: [0, 0, -90]}),
    {id: 'b', class: 'Beam', name: 'b', parent: 'p', properties: {Attachment0: 'a0', Attachment1: 'a1', CurveSize0: 4, CurveSize1: 4, Width0: 0, Width1: 0, Segments: 2, Transparency: sequence(0), FaceCamera: true}}]);
  const sim = E.createSimulation(recipe);
  const frame = E.buildFrame(sim, recipe.camera);
  const ys = Array.from({length: frame.vertices}, (_, i) => frame.data[i * 13 + 1]);
  near(Math.max(...ys), 3, 1e-9, 'Bézier midpoint lifted by 3/4 of CurveSize');
});

test('bundled Arc really bends upward between its attachments', () => {
  const recipe = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../editor/projects/dataky-arc.json'), 'utf8'));
  const sim = E.createSimulation(recipe);
  const ends = ['Attachment0', 'Attachment1'].map(key => sim.frameOf(sim.byId.get(recipe.nodes.find(n => n.class === 'Beam').properties[key])).p[1]);
  const frame = E.buildFrame(sim, recipe.camera);
  const top = Math.max(...Array.from({length: frame.vertices}, (_, i) => frame.data[i * 13 + 1]));
  assert.ok(top > Math.max(...ends) + 1.5, `arc peak ${top} above its ends ${ends}`);
});

test('trail records moving attachments, respects MinLength and expires with Lifetime', () => {
  const recipe = project([part('p', {Position: [0, 0, 0]}), attachment('a0', 'p', {Position: [0, 0.5, 0]}), attachment('a1', 'p', {Position: [0, -0.5, 0]}),
    {id: 't', class: 'Trail', name: 't', parent: 'p', properties: {Attachment0: 'a0', Attachment1: 'a1', Lifetime: 0.5, MinLength: 0.5, Transparency: sequence(0)},
      timing: {start: 0, duration: 1, mode: 'continuous'}}], {duration: 3});
  recipe.animations = [{node: 'p', property: 'Position', keyframes: [{time: 0, value: [0, 0, 0]}, {time: 1, value: [10, 0, 0]}]}];
  const sim = E.createSimulation(recipe);
  sim.seek(0.4);
  const points = sim.trails[0].points;
  assert.ok(points.length >= 6 && points.length <= 9, `points every ~0.5 stud, got ${points.length}`);
  for (let i = 1; i < points.length; i++) assert.ok(points[i - 1].c[0] - points[i].c[0] >= 0.5 - 1e-9);
  assert.ok(E.buildFrame(sim, recipe.camera).batches.some(b => b.kind === 'trail'));
  sim.seek(1.6);
  assert.equal(sim.trails[0].points.length, 0, 'segments older than Lifetime are gone');
});

test('animated properties follow the runtime keyframe sampling', () => {
  const recipe = project([part('p'), emitter('e', 'p', {Rate: 0})]);
  recipe.animations = [{node: 'e', property: 'Rate', keyframes: [{time: 0, value: 0}, {time: 1, value: 100}]},
    {node: 'e', property: 'Enabled', keyframes: [{time: 0, value: true}, {time: 0.5, value: false}]}];
  const sim = E.createSimulation(recipe);
  sim.seek(0.25);
  assert.equal(sim.prop(sim.byId.get('e'), 'Rate'), 25);
  assert.equal(sim.isEnabled('e'), true);
  sim.seek(0.75);
  assert.equal(sim.isEnabled('e'), false, 'booleans hold their keyframe');
});

test('auto camera keeps the view direction and fits every visible corner; the dummy stands beside the effect', () => {
  const recipe = project([part('p'), emitter('e', 'p', {Speed: [6, 6], SpreadAngle: [180, 180], Lifetime: [0.8, 0.8], Size: sequence(0.5)},
    {start: 0, duration: 0.1, mode: 'burst', count: 40})], {duration: 1});
  const bounds = E.effectBounds(recipe);
  assert.ok(bounds && bounds.radius > 1);
  const camera = E.autoCamera(recipe, {bounds, aspect: 16 / 9});
  const dir = (c) => { const d = [0, 1, 2].map(i => c.position[i] - c.target[i]); const l = Math.hypot(...d); return d.map(v => v / l); };
  near(dir(camera), dir(recipe.camera), 1e-3, 'same viewing direction');
  const forward = dir(camera).map(v => -v), right = [-forward[2], 0, forward[0]].map((v, _, a) => v / Math.hypot(...a));
  const up = [right[1] * forward[2] - right[2] * forward[1], right[2] * forward[0] - right[0] * forward[2], right[0] * forward[1] - right[1] * forward[0]];
  const tanV = Math.tan(camera.fov * Math.PI / 360), tanH = tanV * 16 / 9;
  for (let k = 0; k < 8; k++) {
    const corner = [0, 1, 2].map(i => (k >> i) & 1 ? bounds.max[i] : bounds.min[i]);
    const rel = [0, 1, 2].map(i => corner[i] - camera.position[i]);
    const depth = rel.reduce((s, v, i) => s + v * forward[i], 0);
    assert.ok(Math.abs(rel.reduce((s, v, i) => s + v * right[i], 0)) <= depth * tanH + 1e-6, 'corner inside horizontally');
    assert.ok(Math.abs(rel.reduce((s, v, i) => s + v * up[i], 0)) <= depth * tanV + 1e-6, 'corner inside vertically');
  }
  const dummy = E.dummyParts(bounds, recipe.camera);
  assert.equal(dummy.length, 6);
  near(Math.min(...dummy.map(p => p.p[1] - p.size[1] / 2)), 0, 1e-9, 'feet on the ground');
  near(Math.max(...dummy.map(p => p.p[1] + p.size[1] / 2)), 5.2, 1e-9, 'Roblox character height');
  const torso = dummy[1].p;
  assert.ok(Math.hypot(torso[0] - bounds.center[0], torso[2] - bounds.center[2]) > 1.5, 'beside, not inside, the effect');
  assert.equal(E.effectBounds(project([part('p')])), null, 'invisible effect has no extent');
});

test('bundled projects simulate and build frames for their whole duration', () => {
  const folder = path.resolve(__dirname, '../editor/projects');
  for (const file of fs.readdirSync(folder).filter(name => name.endsWith('.json'))) {
    const recipe = JSON.parse(fs.readFileSync(path.join(folder, file), 'utf8'));
    const sim = E.createSimulation(recipe);
    let drawn = 0;
    for (let t = 0; t <= recipe.duration; t += 0.25) {
      sim.seek(t);
      const frame = E.buildFrame(sim, recipe.camera);
      assert.ok(frame.data.every(Number.isFinite), file + ': finite vertices');
      drawn += frame.vertices;
    }
    assert.ok(drawn > 0, file + ' draws something');
  }
});
