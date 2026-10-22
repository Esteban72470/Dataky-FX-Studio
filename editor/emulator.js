/* Dataky FX Studio · émulateur des effets Roblox dans le navigateur.
   La simulation est déterministe (graine fixe, pas de 1/60 s) et suit les règles de
   timing de tool/fx_runtime.lua : un même projet donne la même image au même instant.
   Le rendu WebGL2 approche ParticleEmitter, Beam, Trail, lumières et Parts d’après la
   documentation Roblox ; Roblox Studio reste la référence finale. Aucun texte de projet
   n’est exécuté. */
(function (global) {
  'use strict';
  const STEP = 1 / 60;
  const MAX_PARTICLES = 20000;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const lerp = (a, b, t) => a + (b - a) * t;
  const num = (value, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const vec = (value, fallback = [0, 0, 0]) => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value : fallback;
  const range = (value, fallback) => Array.isArray(value) && value.length === 2 && value.every(Number.isFinite) ? value : fallback;
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
  const madd = (a, b, s) => [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const length = a => Math.hypot(a[0], a[1], a[2]);
  const normalize = (a, fallback = [0, 1, 0]) => { const l = length(a); return l > 1e-9 ? scale(a, 1 / l) : fallback.slice(); };
  const mix = (a, b, t) => typeof a === 'number' && typeof b === 'number' ? lerp(a, b, t)
    : Array.isArray(a) && Array.isArray(b) && a.length === b.length ? a.map((v, i) => lerp(v, b[i], t)) : a;

  // Rotations 3×3 en lignes. Les colonnes sont RightVector, UpVector et -LookVector.
  const IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1];
  function matMul(a, b) {
    const out = new Array(9);
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) out[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
    return out;
  }
  const apply = (m, v) => [m[0] * v[0] + m[1] * v[1] + m[2] * v[2], m[3] * v[0] + m[4] * v[1] + m[5] * v[2], m[6] * v[0] + m[7] * v[1] + m[8] * v[2]];
  const applyInverse = (m, v) => [m[0] * v[0] + m[3] * v[1] + m[6] * v[2], m[1] * v[0] + m[4] * v[1] + m[7] * v[2], m[2] * v[0] + m[5] * v[1] + m[8] * v[2]];
  const column = (m, i) => [m[i], m[3 + i], m[6 + i]];
  function rotation(axis, degrees) {
    const a = degrees * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    if (axis === 0) return [1, 0, 0, 0, c, -s, 0, s, c];
    if (axis === 1) return [c, 0, s, 0, 1, 0, -s, 0, c];
    return [c, -s, 0, s, c, 0, 0, 0, 1];
  }
  // CFrame.fromOrientation applique Z, puis X, puis Y : R = Ry · Rx · Rz.
  const fromOrientation = o => matMul(rotation(1, o[1]), matMul(rotation(0, o[0]), rotation(2, o[2])));
  function fromAxes(axis, secondary) {
    const x = normalize(axis, [1, 0, 0]);
    let z = cross(x, secondary);
    if (length(z) < 1e-6) z = cross(x, Math.abs(x[1]) < 0.9 ? [0, 1, 0] : [0, 0, 1]);
    z = normalize(z);
    const y = cross(z, x);
    return [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]];
  }
  function rotateAround(v, axis, degrees) {
    const a = degrees * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    return add(add(scale(v, c), scale(cross(axis, v), s)), scale(axis, dot(axis, v) * (1 - c)));
  }

  const NORMALS = {Top: [0, 1, 0], Bottom: [0, -1, 0], Right: [1, 0, 0], Left: [-1, 0, 0], Front: [0, 0, -1], Back: [0, 0, 1]};
  const SWITCHES = new Set(['ParticleEmitter', 'Beam', 'Trail', 'PointLight', 'SpotLight', 'SurfaceLight']);
  const constant = value => [{time: 0, value, envelope: 0}, {time: 1, value, envelope: 0}];
  const WHITE = [{time: 0, value: [1, 1, 1]}, {time: 1, value: [1, 1, 1]}];
  const PART = {Position: [0, 0, 0], Orientation: [0, 0, 0], Size: [4, 1, 2], Color: [0.639, 0.635, 0.647], Transparency: 0, Material: 'Plastic', Shape: 'Block'};
  const LIGHT = {Brightness: 1, Color: [1, 1, 1], Enabled: true, Range: 8, Angle: 90, Face: 'Front'};
  // Valeurs par défaut natives (Instance.new) pour les propriétés absentes d’une recette.
  const NATIVE = {
    Part: PART, MeshPart: {...PART, Size: [1, 1, 1]},
    Attachment: {Position: [0, 0, 0], Orientation: [0, 0, 0]},
    SpecialMesh: {MeshType: 'Head', Scale: [1, 1, 1], Offset: [0, 0, 0]},
    PointLight: LIGHT, SpotLight: LIGHT, SurfaceLight: LIGHT,
    ParticleEmitter: {
      Acceleration: [0, 0, 0], Brightness: 1, Color: WHITE, Drag: 0, EmissionDirection: 'Top', Enabled: true,
      FlipbookBlendFrames: true, FlipbookFramerate: [1, 1], FlipbookLayout: 'None', FlipbookMode: 'Loop',
      FlipbookSizeX: 1, FlipbookSizeY: 1, FlipbookStartRandom: false, Lifetime: [5, 10], LightEmission: 0,
      LightInfluence: 0, LockedToPart: false, Orientation: 'FacingCamera', Rate: 20, Rotation: [0, 0],
      RotSpeed: [0, 0], Shape: 'Box', ShapeInOut: 'Outward', ShapePartial: 1, ShapeStyle: 'Volume',
      Size: constant(1), Speed: [5, 5], SpreadAngle: [0, 0], Squash: constant(0),
      Texture: 'rbxasset://textures/particles/sparkles_main.dds', TimeScale: 1, Transparency: constant(0), ZOffset: 0,
    },
    Beam: {
      Brightness: 1, Color: WHITE, CurveSize0: 0, CurveSize1: 0, Enabled: true, FaceCamera: false, LightEmission: 0,
      LightInfluence: 0, Segments: 10, Texture: '', TextureLength: 1, TextureMode: 'Stretch', TextureSpeed: 1,
      Transparency: constant(0.5), Width0: 1, Width1: 1, ZOffset: 0,
    },
    Trail: {
      Brightness: 1, Color: WHITE, Enabled: true, FaceCamera: false, Lifetime: 2, LightEmission: 0, LightInfluence: 0,
      MaxLength: 0, MinLength: 0.1, Texture: '', TextureLength: 1, TextureMode: 'Stretch', Transparency: constant(0.5),
      WidthScale: constant(1),
    },
  };

  function hash(text) {
    let h = 2166136261;
    for (const ch of String(text)) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function random(seed) {
    let s = seed >>> 0;
    return () => {
      s = (s + 0x6D2B79F5) >>> 0;
      let t = Math.imul(s ^ (s >>> 15), s | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function numberSequence(value, fallback) {
    if (typeof value === 'number' && Number.isFinite(value)) return constant(value);
    if (!Array.isArray(value) || value.length < 2) return fallback;
    return value.map(p => Array.isArray(p) ? {time: num(p[0]), value: num(p[1]), envelope: num(p[2])}
      : {time: num(p?.time), value: num(p?.value), envelope: num(p?.envelope)});
  }
  function colorSequence(value) {
    if (Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)) return [{time: 0, value}, {time: 1, value}];
    if (!Array.isArray(value) || value.length < 2) return WHITE;
    return value.map(p => Array.isArray(p) ? {time: num(p[0]), value: vec(p[1], [1, 1, 1])} : {time: num(p?.time), value: vec(p?.value, [1, 1, 1])});
  }
  // jitter : une valeur dans [-1, 1] par point clé, tirée à l’émission de chaque particule.
  function sampleNumber(sequence, t, jitter) {
    const at = i => sequence[i].value + (jitter ? num(jitter[i]) * sequence[i].envelope : 0);
    if (t <= sequence[0].time) return at(0);
    for (let i = 1; i < sequence.length; i++) {
      if (t <= sequence[i].time) {
        const span = sequence[i].time - sequence[i - 1].time;
        return lerp(at(i - 1), at(i), span > 0 ? (t - sequence[i - 1].time) / span : 1);
      }
    }
    return at(sequence.length - 1);
  }
  function sampleColor(sequence, t) {
    if (t <= sequence[0].time) return sequence[0].value;
    for (let i = 1; i < sequence.length; i++) {
      if (t <= sequence[i].time) {
        const a = sequence[i - 1], b = sequence[i], span = b.time - a.time;
        return mix(a.value, b.value, span > 0 ? (t - a.time) / span : 1);
      }
    }
    return sequence[sequence.length - 1].value;
  }

  function createSimulation(input, options = {}) {
    const project = JSON.parse(JSON.stringify(input || {}));
    const nodes = Array.isArray(project.nodes) ? project.nodes : [];
    const byId = new Map(nodes.map(node => [node.id, node]));
    let duration = Math.max(0.01, num(project.duration, 3));
    let durationTicks = Math.max(1, Math.round(duration / STEP));
    let loop = !!project.loop;
    let mode = options.mode === 'free' ? 'free' : 'timeline';
    const seed = num(options.seed, 1) >>> 0;
    const tracks = new Map();
    for (const animation of project.animations || []) {
      if (byId.has(animation?.node) && Array.isArray(animation.keyframes) && animation.keyframes.length) tracks.set(animation.node + '\u0000' + animation.property, animation.keyframes);
    }
    const emitters = nodes.filter(n => n.class === 'ParticleEmitter').map(node => ({node, rng: null, particles: [], carry: 0}));
    const trails = nodes.filter(n => n.class === 'Trail').map(node => ({node, points: [], head: null, odometer: 0}));
    const enabled = new Map();
    const previewEnabled = new Map();
    const frames = new Map();
    const fired = new Set();
    let ticks = 0, clockTicks = 0, ended = false;

    const time = () => ticks * STEP;
    const raw = (node, key) => node.properties?.[key] !== undefined ? node.properties[key] : NATIVE[node.class]?.[key];
    function prop(node, key) {
      const keys = mode === 'free' ? undefined : tracks.get(node.id + '\u0000' + key);
      if (!keys) return raw(node, key);
      const t = time();
      if (t <= keys[0].time) return keys[0].value;
      for (let i = 1; i < keys.length; i++) {
        if (t < keys[i].time) return mix(keys[i - 1].value, keys[i].value, (t - keys[i - 1].time) / (keys[i].time - keys[i - 1].time));
      }
      return keys[keys.length - 1].value;
    }
    const isPart = node => node && (node.class === 'Part' || node.class === 'MeshPart');
    function frameOf(node, depth = 0) {
      if (!node || depth > 8) return {p: [0, 0, 0], m: IDENTITY, size: [0, 0, 0], part: null};
      if (frames.has(node.id)) return frames.get(node.id);
      let frame;
      if (isPart(node)) {
        frame = {p: vec(prop(node, 'Position')), m: fromOrientation(vec(prop(node, 'Orientation'))), size: vec(prop(node, 'Size'), [4, 1, 2]), part: node};
      } else if (node.class === 'Attachment') {
        const parent = frameOf(byId.get(node.parent), depth + 1);
        const axes = ['Axis', 'SecondaryAxis'].some(k => node.properties?.[k] !== undefined || (mode !== 'free' && tracks.has(node.id + '\u0000' + k)));
        const local = axes ? fromAxes(vec(prop(node, 'Axis'), [1, 0, 0]), vec(prop(node, 'SecondaryAxis'), [0, 1, 0])) : fromOrientation(vec(prop(node, 'Orientation')));
        frame = {p: add(parent.p, apply(parent.m, vec(prop(node, 'Position')))), m: matMul(parent.m, local), size: [0, 0, 0], part: parent.part, attachment: true};
      } else if (node.class === 'Folder' || node.class === 'Model') {
        frame = {p: [0, 0, 0], m: IDENTITY, size: [0, 0, 0], part: null};
      } else {
        frame = frameOf(byId.get(node.parent), depth + 1);
      }
      frames.set(node.id, frame);
      return frame;
    }

    // Même logique que update() dans fx_runtime.lua.
    function refreshSwitches() {
      frames.clear();
      const t = time();
      for (const node of nodes) {
        if (!SWITCHES.has(node.class)) continue;
        if (mode === 'free') {
          enabled.set(node.id, previewEnabled.has(node.id) ? previewEnabled.get(node.id) : raw(node, 'Enabled') !== false);
          continue;
        }
        const animated = tracks.has(node.id + '\u0000Enabled') ? prop(node, 'Enabled') !== false : undefined;
        const own = raw(node, 'Enabled') !== false;
        const timing = node.timing;
        let on;
        if (ended || timing?.mode === 'burst') on = false;
        else if (timing) {
          const start = num(timing.start);
          on = own && animated !== false && t >= start - 1e-9 && t < start + num(timing.duration, duration - start) - 1e-9;
        } else on = animated !== undefined ? animated : own;
        enabled.set(node.id, on);
      }
    }
    function fireBursts() {
      if (ended || mode === 'free') return;
      for (const emitter of emitters) {
        const timing = emitter.node.timing;
        if (timing?.mode === 'burst' && !fired.has(emitter.node.id) && time() >= num(timing.start) - 1e-9) {
          fired.add(emitter.node.id);
          if (prop(emitter.node, 'Enabled') !== false) emit(emitter, clamp(Math.round(num(timing.count, 20)), 0, 10000), 0);
        }
      }
    }

    function shapeSample(node, frame, rng) {
      const normal = NORMALS[prop(node, 'EmissionDirection')] || NORMALS.Top;
      const k = normal.findIndex(v => v !== 0), others = [0, 1, 2].filter(i => i !== k);
      const ei = [0, 0, 0], ej = [0, 0, 0];
      ei[others[0]] = 1; ej[others[1]] = 1;
      const half = scale(frame.attachment || !frame.part ? [0, 0, 0] : frame.size, 0.5);
      const shape = prop(node, 'Shape'), surface = prop(node, 'ShapeStyle') === 'Surface';
      const partial = clamp(num(prop(node, 'ShapePartial'), 1), 0, 1);
      const phi = rng() * Math.PI * 2, cos = Math.cos(phi), sin = Math.sin(phi);
      const ring = (r, f = 1) => add(scale(ei, cos * half[others[0]] * r * f), scale(ej, sin * half[others[1]] * r * f));
      if (shape === 'Sphere') {
        const cosMax = Math.cos(partial * Math.PI), c = 1 - rng() * (1 - cosMax), s = Math.sqrt(Math.max(0, 1 - c * c));
        const u = add(scale(normal, c), add(scale(ei, cos * s), scale(ej, sin * s)));
        const r = surface ? 1 : Math.cbrt(rng());
        return {local: [u[0] * half[0] * r, u[1] * half[1] * r, u[2] * half[2] * r], dir: u, normal, ei, ej, radial: true};
      }
      if (shape === 'Cylinder') {
        const along = rng() * 2 - 1, f = lerp(1, partial, (along + 1) / 2);
        const local = add(scale(normal, along * half[k]), ring(surface ? 1 : Math.sqrt(rng()), f));
        return {local, dir: add(scale(ei, cos), scale(ej, sin)), normal, ei, ej, radial: true};
      }
      if (shape === 'Disc') {
        const r = surface ? 1 : Math.sqrt(lerp(partial * partial, 1, rng()));
        return {local: ring(r), dir: normal, normal, ei, ej};
      }
      let local;
      if (surface) {
        const areas = [half[1] * half[2], half[0] * half[2], half[0] * half[1]];
        const total = areas[0] + areas[1] + areas[2];
        let pick = rng() * total * 2, axis = 0;
        while (axis < 2 && pick > areas[axis] * 2) { pick -= areas[axis] * 2; axis++; }
        local = half.map(h => (rng() * 2 - 1) * h);
        local[axis] = (rng() < 0.5 ? -1 : 1) * half[axis];
      } else local = half.map(h => (rng() * 2 - 1) * h);
      return {local, dir: normal, normal, ei, ej};
    }

    function spawn(emitter) {
      const {node, rng} = emitter;
      const frame = frameOf(node);
      const sample = shapeSample(node, frame, rng);
      const mode = prop(node, 'ShapeInOut');
      let dir = scale(sample.dir, mode === 'Inward' ? -1 : mode === 'InAndOut' && rng() < 0.5 ? -1 : 1);
      // SpreadAngle : rotation aléatoire autour des deux axes perpendiculaires à l’émission.
      const spread = range(prop(node, 'SpreadAngle'), [0, 0]);
      let a1 = sample.ei, a2 = sample.ej;
      if (sample.radial) { a1 = normalize(cross(dir, Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]), [1, 0, 0]); a2 = cross(dir, a1); }
      if (spread[0]) dir = rotateAround(dir, a1, (rng() * 2 - 1) * spread[0]);
      if (spread[1]) dir = rotateAround(dir, a2, (rng() * 2 - 1) * spread[1]);
      const speed = range(prop(node, 'Speed'), [5, 5]), life = range(prop(node, 'Lifetime'), [5, 10]);
      const rot = range(prop(node, 'Rotation'), [0, 0]), spin = range(prop(node, 'RotSpeed'), [0, 0]);
      const flip = range(prop(node, 'FlipbookFramerate'), [1, 1]);
      const localVelocity = scale(dir, lerp(speed[0], speed[1], rng()));
      const locked = prop(node, 'LockedToPart') === true;
      const jitter = sequence => Array.isArray(sequence) ? sequence.map(() => rng() * 2 - 1) : null;
      return {
        locked,
        p: locked ? sample.local : add(frame.p, apply(frame.m, sample.local)),
        v0: locked ? localVelocity : apply(frame.m, localVelocity), va: [0, 0, 0],
        age: 0, life: Math.max(1e-3, lerp(life[0], life[1], rng())),
        rot: lerp(rot[0], rot[1], rng()), spin: lerp(spin[0], spin[1], rng()),
        size: jitter(prop(node, 'Size')), transparency: jitter(prop(node, 'Transparency')), squash: jitter(prop(node, 'Squash')),
        flipRate: Math.min(30, lerp(flip[0], flip[1], rng())), flipStart: prop(node, 'FlipbookStartRandom') === true ? rng() : 0,
        flipSeed: Math.floor(rng() * 4294967296),
      };
    }
    function integrate(emitter, particle, dt) {
      const node = emitter.node;
      const drag = num(prop(node, 'Drag'));
      let acceleration = vec(prop(node, 'Acceleration'));
      if (particle.locked) acceleration = applyInverse(frameOf(node).m, acceleration);
      // Drag réduit de moitié la vitesse d’émission toutes les 1/Drag secondes ; l’accélération n’est pas freinée.
      if (drag) particle.v0 = scale(particle.v0, Math.pow(2, -drag * dt));
      particle.va = madd(particle.va, acceleration, dt);
      particle.p = madd(particle.p, add(particle.v0, particle.va), dt);
      particle.age += dt;
      particle.rot += particle.spin * dt;
    }
    function emit(emitter, count, preAge) {
      for (let i = 0; i < count && emitter.particles.length < MAX_PARTICLES; i++) {
        const particle = spawn(emitter);
        if (preAge) integrate(emitter, particle, emitter.rng() * preAge);
        if (particle.age < particle.life) emitter.particles.push(particle);
      }
    }
    const timeScale = node => clamp(num(prop(node, 'TimeScale'), 1), 0, 1);

    function sampleTrail(trail) {
      const node = trail.node;
      const a0 = byId.get(prop(node, 'Attachment0')), a1 = byId.get(prop(node, 'Attachment1'));
      if (!enabled.get(node.id) || a0?.class !== 'Attachment' || a1?.class !== 'Attachment') { trail.head = null; return; }
      const p0 = frameOf(a0).p, p1 = frameOf(a1).p, c = scale(add(p0, p1), 0.5);
      if (!trail.head || !trail.points.length) {
        trail.points.unshift({p0, p1, c, age: 0, odo: trail.odometer, start: true});
      } else {
        const moved = length(sub(c, trail.points[0].c));
        if (moved >= Math.max(1e-4, num(prop(node, 'MinLength'), 0.1))) {
          trail.odometer += moved;
          trail.points.unshift({p0, p1, c, age: 0, odo: trail.odometer, start: false});
        }
      }
      trail.head = {p0, p1, c, age: 0, odo: trail.odometer + length(sub(c, trail.points[0].c))};
      const maxLength = num(prop(node, 'MaxLength'));
      if (maxLength > 0) {
        let total = length(sub(trail.head.c, trail.points[0].c));
        for (let i = 1; i < trail.points.length; i++) {
          total += length(sub(trail.points[i - 1].c, trail.points[i].c));
          if (total > maxLength) { trail.points.length = i; break; }
        }
      }
    }
    function ageTrail(trail, dt) {
      const life = Math.max(1e-3, num(prop(trail.node, 'Lifetime'), 2));
      for (const point of trail.points) point.age += dt;
      while (trail.points.length && trail.points[trail.points.length - 1].age > life) trail.points.pop();
    }

    function clearVisuals() {
      for (const emitter of emitters) { emitter.particles = []; emitter.carry = 0; }
      for (const trail of trails) { trail.points = []; trail.head = null; }
    }
    function reset() {
      ticks = 0; clockTicks = 0; ended = false; pending = 0;
      fired.clear(); clearVisuals();
      for (const emitter of emitters) emitter.rng = random(seed ^ hash(emitter.node.id));
      refreshSwitches(); fireBursts();
      for (const trail of trails) sampleTrail(trail);
    }
    function step() {
      frames.clear();
      for (const emitter of emitters) {
        const dt = STEP * timeScale(emitter.node);
        if (!dt) continue;
        for (const particle of emitter.particles) integrate(emitter, particle, dt);
        emitter.particles = emitter.particles.filter(p => p.age < p.life);
      }
      for (const trail of trails) ageTrail(trail, STEP);
      clockTicks++;
      if (mode === 'free') {
        ticks++;
        refreshSwitches();
      } else if (!ended) {
        ticks++;
        if (ticks >= durationTicks) {
          ticks = durationTicks; refreshSwitches(); fireBursts();
          if (loop) { clearVisuals(); ticks = 0; fired.clear(); }
          else ended = true;
        }
        refreshSwitches(); fireBursts();
      }
      for (const emitter of emitters) {
        if (!enabled.get(emitter.node.id)) continue;
        if (mode === 'free' && emitter.node.timing?.mode === 'burst') continue;
        const dt = STEP * timeScale(emitter.node);
        emitter.carry += Math.max(0, num(prop(emitter.node, 'Rate'), 20)) * dt;
        const count = Math.floor(emitter.carry);
        emitter.carry -= count;
        if (count) emit(emitter, count, dt);
      }
      for (const trail of trails) sampleTrail(trail);
    }
    function seek(seconds) {
      const target = Math.max(0, Math.round(num(seconds) / STEP));
      if (target < clockTicks) reset();
      const limit = Math.min(target, Math.round(600 / STEP));
      while (clockTicks < limit) step();
    }
    let pending = 0;
    function advance(seconds) {
      pending = Math.min(pending + Math.max(0, num(seconds)), 0.25);
      while (pending >= STEP) { pending -= STEP; step(); }
    }

    function manualEmit(ids, count) {
      const selected = ids == null ? null : new Set(typeof ids === 'string' ? [ids] : ids);
      let emitted = 0;
      frames.clear();
      for (const emitter of emitters) {
        if (selected ? !selected.has(emitter.node.id) : emitter.node.timing?.mode !== 'burst') continue;
        const amount = clamp(Math.round(num(count, num(emitter.node.timing?.count, 30))), 0, 10000);
        const before = emitter.particles.length;
        emit(emitter, amount, 0);
        emitted += emitter.particles.length - before;
      }
      return emitted;
    }
    function setEnabled(id, value) {
      const node = byId.get(id);
      if (!node || !SWITCHES.has(node.class)) return false;
      if (mode === 'free') previewEnabled.set(id, !!value);
      else { node.properties ||= {}; node.properties.Enabled = !!value; }
      refreshSwitches();
      return true;
    }
    // Reconcile live properties and the node tree without discarding free-mode
    // particles, random streams, preview switches or elapsed time.
    function updateProject(input) {
      const next = JSON.parse(JSON.stringify(input || {}));
      const oldEmitters = new Map(emitters.map(e => [e.node.id, e]));
      const oldTrails = new Map(trails.map(t => [t.node.id, t]));
      for (const key of Object.keys(project)) delete project[key];
      Object.assign(project, next);
      nodes.splice(0, nodes.length, ...(Array.isArray(next.nodes) ? next.nodes : []));
      project.nodes = nodes;
      byId.clear();
      for (const node of nodes) byId.set(node.id, node);
      tracks.clear();
      for (const animation of project.animations || []) {
        if (byId.has(animation?.node) && Array.isArray(animation.keyframes) && animation.keyframes.length) tracks.set(animation.node + '\u0000' + animation.property, animation.keyframes);
      }
      emitters.splice(0, emitters.length, ...nodes.filter(n => n.class === 'ParticleEmitter').map(node => {
        const emitter = oldEmitters.get(node.id) || {rng: random(seed ^ hash(node.id)), particles: [], carry: 0};
        emitter.node = node;
        return emitter;
      }));
      trails.splice(0, trails.length, ...nodes.filter(n => n.class === 'Trail').map(node => {
        const trail = oldTrails.get(node.id) || {points: [], head: null, odometer: 0};
        trail.node = node;
        return trail;
      }));
      for (const id of previewEnabled.keys()) if (!byId.has(id)) previewEnabled.delete(id);
      duration = Math.max(0.01, num(project.duration, 3));
      durationTicks = Math.max(1, Math.round(duration / STEP));
      loop = !!project.loop;
      refreshSwitches();
    }

    reset();
    const api = {
      project, step: STEP, nodes, byId, emitters, trails,
      prop, frameOf, isEnabled: id => !!enabled.get(id), reset, seek, advance, stepOnce: step,
      emit: manualEmit, setEnabled, clearParticles: clearVisuals, updateProject,
      resetPreviewState() { previewEnabled.clear(); reset(); clearVisuals(); },
      setMode(next) { const value = next === 'free' ? 'free' : 'timeline'; if (value !== mode) { mode = value; reset(); } return mode; },
      stop() { reset(); clearVisuals(); },
      get mode() { return mode; }, get duration() { return duration; }, get loop() { return loop; },
      get time() { return time(); }, get clock() { return clockTicks * STEP; }, get ended() { return ended; },
      get alive() { return emitters.some(e => e.particles.length) || trails.some(t => t.points.length); },
      stats() { return {time: time(), particles: emitters.reduce((n, e) => n + e.particles.length, 0), trailPoints: trails.reduce((n, t) => n + t.points.length, 0)}; },
    };
    return api;
  }

  // ---- Géométrie : listes de sommets indépendantes de WebGL (testables sans navigateur) ----
  const STRIDE = 13; // position 3, uv 2, uv flipbook 2, couleur 4, fondu flipbook + LightEmission 2
  const GRIDS = {Grid2x2: [2, 2], Grid4x4: [4, 4], Grid8x8: [8, 8]};

  function cameraBasis(camera) {
    const position = vec(camera?.position, [10, 6, 12]), target = vec(camera?.target, [0, 1, 0]);
    const forward = normalize(sub(target, position), [0, 0, -1]);
    let right = cross(forward, [0, 1, 0]);
    right = length(right) < 1e-6 ? [1, 0, 0] : normalize(right);
    return {position, target, forward, right, up: cross(right, forward), fov: clamp(num(camera?.fov, 50), 1, 120)};
  }

  function buildFrame(sim, cameraInput, options = {}) {
    const camera = cameraBasis(cameraInput);
    let data = new Float32Array(STRIDE * 6 * 1024), count = 0;
    const batches = [], parts = [], lights = [], placeholders = [], points = [];
    const push = (p, u, v, u2, v2, color, alpha, blend, emission) => {
      if ((count + 1) * STRIDE > data.length) { const next = new Float32Array(data.length * 2); next.set(data); data = next; }
      const o = count * STRIDE;
      data[o] = p[0]; data[o + 1] = p[1]; data[o + 2] = p[2]; data[o + 3] = u; data[o + 4] = v; data[o + 5] = u2; data[o + 6] = v2;
      data[o + 7] = color[0]; data[o + 8] = color[1]; data[o + 9] = color[2]; data[o + 10] = alpha; data[o + 11] = blend; data[o + 12] = emission;
      count++;
    };
    // Coins dans l’ordre haut-gauche, haut-droite, bas-gauche, bas-droite.
    const quad = (corners, uv, colors, alphas, emission, uv2 = uv, blend = 0) => {
      for (const i of [0, 2, 3, 0, 3, 1]) push(corners[i], uv[i][0], uv[i][1], uv2[i][0], uv2[i][1], colors[i], alphas[i], blend, emission);
    };
    // Ruban entre deux bords successifs (beam ou trail) : couleur et transparence propres à chaque bord.
    // L’axe vertical de l’image suit la longueur du ruban et l’axe horizontal sa largeur : les textures
    // de la collection Beams sont dessinées ainsi (motifs majoritairement verticaux).
    const ribbon = (a, b, emission) => quad([a.top, b.top, a.bottom, b.bottom], [[0, a.u], [0, b.u], [1, a.u], [1, b.u]],
      [a.color, b.color, a.color, b.color], [a.alpha, b.alpha, a.alpha, b.alpha], emission);
    const depthOf = p => dot(sub(p, camera.position), camera.forward);
    const intensity = node => lerp(Math.max(0, num(sim.prop(node, 'Brightness'), 1)), 1, clamp(num(sim.prop(node, 'LightInfluence')), 0, 1));

    for (const emitter of sim.emitters) {
      const node = emitter.node;
      if (!emitter.particles.length) continue;
      const frame = sim.frameOf(node);
      const sizeSeq = numberSequence(sim.prop(node, 'Size'), NATIVE.ParticleEmitter.Size);
      const transparencySeq = numberSequence(sim.prop(node, 'Transparency'), NATIVE.ParticleEmitter.Transparency);
      const squashSeq = numberSequence(sim.prop(node, 'Squash'), NATIVE.ParticleEmitter.Squash);
      const colorSeq = colorSequence(sim.prop(node, 'Color'));
      const orientation = sim.prop(node, 'Orientation');
      const zOffset = num(sim.prop(node, 'ZOffset'));
      const emission = clamp(num(sim.prop(node, 'LightEmission')), 0, 1);
      const light = intensity(node);
      const layout = sim.prop(node, 'FlipbookLayout');
      const grid = layout === 'Custom' ? [clamp(Math.round(num(sim.prop(node, 'FlipbookSizeX'), 1)), 1, 64), clamp(Math.round(num(sim.prop(node, 'FlipbookSizeY'), 1)), 1, 64)] : GRIDS[layout] || null;
      const frameCount = grid ? grid[0] * grid[1] : 1;
      const flipMode = sim.prop(node, 'FlipbookMode');
      const blendFrames = sim.prop(node, 'FlipbookBlendFrames') !== false;
      const items = emitter.particles.map(particle => {
        const world = particle.locked ? add(frame.p, apply(frame.m, particle.p)) : particle.p;
        return {particle, world, depth: depthOf(world)};
      }).sort((a, b) => b.depth - a.depth);
      const first = count;
      let depthSum = 0, drawn = 0;
      for (const {particle, world, depth} of items) {
        const t = clamp(particle.age / particle.life, 0, 1);
        const size = Math.max(0, sampleNumber(sizeSeq, t, particle.size));
        const alpha = 1 - clamp(sampleNumber(transparencySeq, t, particle.transparency), 0, 1);
        if (size <= 1e-5 || alpha <= 1e-4 || (!options.boundsOnly && depth <= 0.05)) continue;
        const squash = clamp(sampleNumber(squashSeq, t, particle.squash), -3, 3);
        // Mesuré dans Roblox : en VelocityParallel, un Squash négatif étire le long
        // de la vitesse. Les autres orientations gardent leur approximation existante.
        const quadSquash = orientation === 'VelocityParallel' ? -squash : squash;
        const width = size * (quadSquash > 0 ? 1 / (1 + quadSquash) : 1 - quadSquash), height = size * (quadSquash > 0 ? 1 + quadSquash : 1 / (1 - quadSquash));
        const velocity = particle.locked ? apply(frame.m, add(particle.v0, particle.va)) : add(particle.v0, particle.va);
        const toCamera = normalize(sub(camera.position, world), scale(camera.forward, -1));
        let right = camera.right, up = camera.up;
        if (orientation === 'FacingCameraWorldUp') {
          up = [0, 1, 0]; right = normalize(cross([0, 1, 0], toCamera), camera.right);
        } else if (orientation === 'VelocityParallel' && length(velocity) > 1e-5) {
          up = normalize(velocity); right = normalize(cross(up, toCamera), camera.right);
        } else if (orientation === 'VelocityPerpendicular' && length(velocity) > 1e-5) {
          const n = normalize(velocity);
          right = normalize(cross(Math.abs(n[1]) < 0.99 ? [0, 1, 0] : [1, 0, 0], n)); up = cross(n, right);
        }
        const r = particle.rot * Math.PI / 180, cr = Math.cos(r), sr = Math.sin(r);
        const rx = add(scale(right, cr), scale(up, sr)), ry = add(scale(up, cr), scale(right, -sr));
        // ZOffset avance vers la caméra sans changer la taille apparente.
        let center = world, k = 1;
        if (zOffset && !options.boundsOnly) { const distance = length(sub(camera.position, world)); const moved = clamp(zOffset, -1e4, distance - 0.05); center = madd(world, toCamera, moved); k = (distance - moved) / distance; }
        const hx = scale(rx, width * k / 2), hy = scale(ry, height * k / 2);
        const corners = [add(sub(center, hx), hy), add(add(center, hx), hy), sub(sub(center, hx), hy), sub(add(center, hx), hy)];
        let uv = [[0, 0], [1, 0], [0, 1], [1, 1]], uv2 = uv, blend = 0;
        if (grid) {
          let position;
          if (flipMode === 'OneShot') position = t * frameCount;
          else if (flipMode === 'PingPong') { const cycle = Math.max(1, 2 * frameCount - 2); const raw = (particle.flipStart * cycle + particle.age * particle.flipRate) % cycle; position = raw < frameCount ? raw : cycle - raw; }
          else if (flipMode === 'Random') { const tick = Math.floor(particle.age * particle.flipRate); position = (hash(particle.flipSeed + ':' + tick) % frameCount) + ((particle.age * particle.flipRate) % 1); }
          else position = (particle.flipStart * frameCount + particle.age * particle.flipRate) % frameCount;
          const index = clamp(Math.floor(position), 0, frameCount - 1);
          const next = flipMode === 'Random' ? hash(particle.flipSeed + ':' + (Math.floor(particle.age * particle.flipRate) + 1)) % frameCount
            : flipMode === 'OneShot' ? Math.min(index + 1, frameCount - 1) : (index + 1) % frameCount;
          const cell = i => uv.map(([u, v]) => [((i % grid[0]) + u) / grid[0], (Math.floor(i / grid[0]) + v) / grid[1]]);
          uv2 = cell(next); uv = cell(index); blend = blendFrames ? position - Math.floor(position) : 0;
        }
        const color = scale(sampleColor(colorSeq, t), light);
        quad(corners, uv, [color, color, color, color], [alpha, alpha, alpha, alpha], emission, uv2, blend);
        points.push({node: node.id, p: world, size: Math.max(width, height), alpha,
          ...(options.boundsOnly ? {corners, uv, uv2, blend, texture: sim.prop(node, 'Texture') ?? ''} : {})});
        depthSum += depth; drawn++;
      }
      if (drawn) batches.push({kind: 'particles', node: node.id, texture: sim.prop(node, 'Texture') ?? '', first, count: count - first, depth: depthSum / drawn - zOffset});
    }

    for (const node of sim.nodes) {
      if (node.class !== 'Beam' || !sim.isEnabled(node.id)) continue;
      const a0 = sim.byId.get(sim.prop(node, 'Attachment0')), a1 = sim.byId.get(sim.prop(node, 'Attachment1'));
      if (a0?.class !== 'Attachment' || a1?.class !== 'Attachment') continue;
      const f0 = sim.frameOf(a0), f1 = sim.frameOf(a1);
      // Bézier cubique : P1 suit +X d’Attachment0, P2 suit -X d’Attachment1 (documentation Beam).
      const p0 = f0.p, p3 = f1.p;
      const p1 = madd(p0, column(f0.m, 0), num(sim.prop(node, 'CurveSize0')));
      const p2 = madd(p3, column(f1.m, 0), -num(sim.prop(node, 'CurveSize1')));
      const segments = clamp(Math.round(num(sim.prop(node, 'Segments'), 10)), 1, 100);
      const points = [];
      for (let i = 0; i <= segments; i++) {
        const t = i / segments, s = 1 - t;
        const p = add(add(scale(p0, s * s * s), scale(p1, 3 * s * s * t)), add(scale(p2, 3 * s * t * t), scale(p3, t * t * t)));
        const d = add(add(scale(sub(p1, p0), 3 * s * s), scale(sub(p2, p1), 6 * s * t)), scale(sub(p3, p2), 3 * t * t));
        points.push({t, p, d});
      }
      let total = 0;
      for (let i = 0; i < points.length; i++) { if (i) total += length(sub(points[i].p, points[i - 1].p)); points[i].distance = total; }
      for (const point of points) {
        point.tangent = normalize(length(point.d) > 1e-6 ? point.d : sub(p3, p0), [1, 0, 0]);
        // Sans FaceCamera, la largeur suit l’axe Y (UpVector) des attachments.
        let side = sim.prop(node, 'FaceCamera') === true
          ? cross(point.tangent, normalize(sub(camera.position, point.p)))
          : mix(column(f0.m, 1), column(f1.m, 1), point.t);
        side = sub(side, scale(point.tangent, dot(side, point.tangent)));
        point.side = normalize(side, camera.up);
      }
      const mode = sim.prop(node, 'TextureMode'), textureLength = Math.max(1e-3, num(sim.prop(node, 'TextureLength'), 1));
      const scroll = sim.clock * num(sim.prop(node, 'TextureSpeed'), 1);
      const uOf = point => (mode === 'Wrap' || mode === 'Static' ? point.distance / textureLength : (total > 0 ? point.distance / total : point.t) * textureLength) - scroll;
      const width0 = Math.max(0, num(sim.prop(node, 'Width0'), 1)), width1 = Math.max(0, num(sim.prop(node, 'Width1'), 1));
      const colorSeq = colorSequence(sim.prop(node, 'Color'));
      const transparencySeq = numberSequence(sim.prop(node, 'Transparency'), NATIVE.Beam.Transparency);
      const light = intensity(node), emission = clamp(num(sim.prop(node, 'LightEmission')), 0, 1);
      const zOffset = num(sim.prop(node, 'ZOffset'));
      const first = count;
      const edge = point => {
        const half = lerp(width0, width1, point.t) / 2;
        let center = point.p;
        if (zOffset) center = madd(center, normalize(sub(camera.position, center)), zOffset);
        return {top: madd(center, point.side, half), bottom: madd(center, point.side, -half), u: uOf(point),
          color: scale(sampleColor(colorSeq, point.t), light), alpha: 1 - clamp(sampleNumber(transparencySeq, point.t), 0, 1)};
      };
      let previous = edge(points[0]);
      for (let i = 1; i < points.length; i++) {
        const current = edge(points[i]);
        if (previous.alpha > 1e-4 || current.alpha > 1e-4) ribbon(previous, current, emission);
        previous = current;
      }
      if (count > first) batches.push({kind: 'beam', node: node.id, texture: sim.prop(node, 'Texture') ?? '', first, count: count - first, depth: depthOf(scale(add(p0, p3), 0.5)) - zOffset});
    }

    for (const trail of sim.trails) {
      const node = trail.node;
      const chain = (trail.head ? [trail.head] : []).concat(trail.points);
      if (chain.length < 2) continue;
      const life = Math.max(1e-3, num(sim.prop(node, 'Lifetime'), 2));
      const colorSeq = colorSequence(sim.prop(node, 'Color'));
      const transparencySeq = numberSequence(sim.prop(node, 'Transparency'), NATIVE.Trail.Transparency);
      const widthSeq = numberSequence(sim.prop(node, 'WidthScale'), NATIVE.Trail.WidthScale);
      const faceCamera = sim.prop(node, 'FaceCamera') === true;
      const mode = sim.prop(node, 'TextureMode'), textureLength = Math.max(1e-3, num(sim.prop(node, 'TextureLength'), 1));
      const light = intensity(node), emission = clamp(num(sim.prop(node, 'LightEmission')), 0, 1);
      let total = 0;
      const distances = [0];
      for (let i = 1; i < chain.length; i++) { total += length(sub(chain[i - 1].c, chain[i].c)); distances.push(total); }
      const edge = i => {
        const point = chain[i], t = clamp(point.age / life, 0, 1);
        const scaleWidth = Math.max(0, sampleNumber(widthSeq, t));
        let half = scale(sub(point.p1, point.p0), 0.5 * scaleWidth);
        if (faceCamera) {
          const tangent = normalize(sub(chain[Math.max(0, i - 1)].c, chain[Math.min(chain.length - 1, i + 1)].c), [1, 0, 0]);
          half = scale(normalize(cross(tangent, normalize(sub(camera.position, point.c)))), length(sub(point.p1, point.p0)) * 0.5 * scaleWidth);
        }
        // Static : texture « tamponnée » dans le monde ; Wrap : fixe par rapport aux attachments ; Stretch : étirée sur la longueur.
        const u = mode === 'Static' ? point.odo / textureLength : mode === 'Wrap' ? distances[i] / textureLength : (total > 0 ? distances[i] / total : 0) * textureLength;
        return {top: add(point.c, half), bottom: sub(point.c, half), u,
          color: scale(sampleColor(colorSeq, t), light), alpha: 1 - clamp(sampleNumber(transparencySeq, t), 0, 1)};
      };
      const first = count;
      let previous = edge(0);
      for (let i = 1; i < chain.length; i++) {
        const current = edge(i);
        // Un point « start » ouvre une nouvelle traînée : pas de ruban vers la traînée précédente.
        if (!chain[i - 1].start && (previous.alpha > 1e-4 || current.alpha > 1e-4)) ribbon(previous, current, emission);
        previous = current;
      }
      if (count > first) batches.push({kind: 'trail', node: node.id, texture: sim.prop(node, 'Texture') ?? '', first, count: count - first, depth: depthOf(chain[0].c)});
    }

    for (const node of sim.nodes) {
      if (node.class === 'Part' || node.class === 'MeshPart') {
        const frame = sim.frameOf(node);
        const transparency = clamp(num(sim.prop(node, 'Transparency')), 0, 1);
        const mesh = sim.nodes.find(n => n.parent === node.id && n.class === 'SpecialMesh');
        if (node.class === 'MeshPart' || (mesh && !['Sphere', 'Cylinder', 'Brick'].includes(sim.prop(mesh, 'MeshType')))) {
          if (transparency < 1) placeholders.push({node: node.id, frame, size: mesh ? vec(sim.prop(mesh, 'Scale'), [1, 1, 1]).map((v, i) => v * frame.size[i]) : frame.size});
          continue;
        }
        if (transparency >= 1) continue;
        const shape = mesh ? {Sphere: 'MeshSphere', Cylinder: 'MeshCylinder', Brick: 'Block'}[sim.prop(mesh, 'MeshType')] : sim.prop(node, 'Shape');
        const size = mesh ? vec(sim.prop(mesh, 'Scale'), [1, 1, 1]).map((v, i) => v * frame.size[i]) : frame.size;
        const position = mesh ? add(frame.p, apply(frame.m, vec(sim.prop(mesh, 'Offset')))) : frame.p;
        parts.push({node: node.id, shape: shape || 'Block', p: position, m: frame.m, size, color: vec(sim.prop(node, 'Color'), PART.Color),
          alpha: 1 - transparency, neon: sim.prop(node, 'Material') === 'Neon', depth: depthOf(position)});
      } else if (/Light$/.test(node.class) && sim.isEnabled(node.id)) {
        const frame = sim.frameOf(node);
        const face = NORMALS[sim.prop(node, 'Face')] || NORMALS.Front;
        lights.push({node: node.id, kind: node.class, p: frame.p, direction: apply(frame.m, face), color: vec(sim.prop(node, 'Color'), [1, 1, 1]),
          brightness: Math.max(0, num(sim.prop(node, 'Brightness'), 1)), range: clamp(num(sim.prop(node, 'Range'), 8), 0, 60), angle: clamp(num(sim.prop(node, 'Angle'), 90), 0, 180)});
      }
    }
    return {camera, data: data.subarray(0, count * STRIDE), vertices: count, batches: batches.sort((a, b) => b.depth - a.depth), parts, lights, placeholders, points};
  }

  // ---- Étendue de l’effet, cadrage automatique et mannequin d’échelle ----
  // L’étendue couvre ce qui est visible sur toute la durée : particules assez opaques, beams, trails et Parts.
  function effectBounds(input, options = {}) {
    const sim = createSimulation(input, {seed: options.seed});
    const selected = options.ids == null ? null : new Set(typeof options.ids === 'string' ? [options.ids] : options.ids);
    if (selected) {
      let changed = true;
      while (changed) {
        changed = false;
        for (const node of sim.nodes) if (selected.has(node.parent) && !selected.has(node.id)) { selected.add(node.id); changed = true; }
      }
    }
    const includes = id => !selected || selected.has(id);
    const samples = Math.max(2, options.samples || 24);
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    const grow = (p, r = 0) => { for (let i = 0; i < 3; i++) { min[i] = Math.min(min[i], p[i] - r); max[i] = Math.max(max[i], p[i] + r); } };
    for (let i = 0; i <= samples; i++) {
      sim.seek(sim.duration * i / samples);
      const frame = buildFrame(sim, input?.camera);
      // Particules : le contenu d’une texture est surtout près du centre ; les particules presque transparentes sont ignorées.
      for (const point of frame.points) if (includes(point.node) && point.alpha >= 0.2) grow(point.p, point.size * 0.3);
      for (const batch of frame.batches) {
        if (batch.kind === 'particles' || !includes(batch.node)) continue;
        for (let v = batch.first; v < batch.first + batch.count; v++) grow([frame.data[v * STRIDE], frame.data[v * STRIDE + 1], frame.data[v * STRIDE + 2]]);
      }
      for (const part of frame.parts) if (includes(part.node)) grow(part.p, length(part.size) / 2);
      for (const box of frame.placeholders) if (includes(box.node)) grow(box.frame.p, length(box.size) / 2);
    }
    if (!Number.isFinite(min[0]) && selected) for (const id of selected) {
      const node = sim.byId.get(id);
      if (node) { const frame = sim.frameOf(node); grow(frame.p, Math.max(0.5, length(frame.size) / 2)); }
    }
    if (!Number.isFinite(min[0])) return null;
    return boundsOf(min, max);
  }
  const boundsOf = (min, max) => ({min, max, center: scale(add(min, max), 0.5), radius: Math.max(0.5, length(sub(max, min)) / 2)});
  const unionBounds = (a, b) => !a ? b : !b ? a : boundsOf(a.min.map((v, i) => Math.min(v, b.min[i])), a.max.map((v, i) => Math.max(v, b.max[i])));

  // Rendu ciblé : union des particules encore vivantes aux seuls instants demandés.
  // Le centile porte sur leurs centres, puis leur demi-taille (Squash compris) est ajoutée.
  // Les particules derrière la caméra initiale restent prises en compte ;
  // l'emprise des billboards suit la caméra candidate, sans rejet au plan proche.
  function sampledParticleBounds(input, options = {}) {
    const sim = createSimulation(input, {seed: options.seed});
    const selected = new Set(typeof options.ids === 'string' ? [options.ids] : options.ids || sim.nodes.map(node => node.id));
    for (let changed = true; changed;) {
      changed = false;
      for (const node of sim.nodes) if (selected.has(node.parent) && !selected.has(node.id)) { selected.add(node.id); changed = true; }
    }
    const times = [...new Set((options.times || [0]).map(t => Math.max(0, Math.round(t / STEP)) * STEP))].sort((a, b) => a - b);
    const particles = [];
    for (const time of times) {
      sim.seek(time);
      if (options.textureBounds) {
        const scene = buildFrame(sim, options.camera || input?.camera, {boundsOnly: true});
        for (const point of scene.points) {
          if (!selected.has(point.node)) continue;
          const rect = options.textureBounds(point.texture, point.uv, point.uv2, point.blend);
          if (!rect) continue;
          // The half-size is encoded in the actual rotated/squashed quad. Map
          // only the nontransparent portion of its current flipbook cell.
          const horizontal = sub(point.corners[1], point.corners[0]);
          const vertical = sub(point.corners[2], point.corners[0]);
          const coordinates = options.textureBounds.points?.(point.texture, point.uv, point.uv2, point.blend)
            || [[rect.min[0], rect.min[1]], [rect.min[0], rect.max[1]], [rect.max[0], rect.min[1]], [rect.max[0], rect.max[1]]];
          const corners = coordinates.map(([u, v]) => add(point.corners[0], add(scale(horizontal, u), scale(vertical, v))));
          particles.push({p: point.p, corners});
        }
        continue;
      }
      for (const emitter of sim.emitters) {
        const node = emitter.node;
        if (!selected.has(node.id)) continue;
        const frame = sim.frameOf(node);
        const sizeSeq = numberSequence(sim.prop(node, 'Size'), NATIVE.ParticleEmitter.Size);
        const squashSeq = numberSequence(sim.prop(node, 'Squash'), NATIVE.ParticleEmitter.Squash);
        for (const particle of emitter.particles) {
          const age = clamp(particle.age / particle.life, 0, 1);
          const size = Math.max(0, sampleNumber(sizeSeq, age, particle.size));
          const squash = clamp(sampleNumber(squashSeq, age, particle.squash), -3, 3);
          particles.push({p: particle.locked ? add(frame.p, apply(frame.m, particle.p)) : particle.p.slice(), halfSize: size * (1 + Math.abs(squash)) / 2});
        }
      }
    }
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    const grow = (p, r = 0) => { for (let i = 0; i < 3; i++) { min[i] = Math.min(min[i], p[i] - r); max[i] = Math.max(max[i], p[i] + r); } };
    const percentile = clamp(num(options.percentile, 90), Number.EPSILON, 100);
    const fitPoints = [];
    let retained = 0;
    if (particles.length) {
      const centroid = scale(particles.reduce((sum, particle) => add(sum, particle.p), [0, 0, 0]), 1 / particles.length);
      const distances = particles.map(particle => length(sub(particle.p, centroid)));
      const sorted = distances.slice().sort((a, b) => a - b);
      // Rang supérieur : les très petits ensembles ne perdent pas arbitrairement un objet.
      const cutoff = sorted[Math.max(0, Math.ceil(sorted.length * percentile / 100) - 1)];
      particles.forEach((particle, index) => { if (distances[index] <= cutoff + 1e-9) {
        if (particle.corners) for (const corner of particle.corners) { grow(corner); fitPoints.push(corner); }
        else grow(particle.p, particle.halfSize);
        retained++;
      } });
    } else {
      // Une sélection d'émetteur sans particules reprend sa Part porteuse et ses Attachments.
      const anchors = new Set([...selected].filter(id => ['Part', 'MeshPart', 'Attachment'].includes(sim.byId.get(id)?.class)));
      if (![...anchors].some(id => ['Part', 'MeshPart'].includes(sim.byId.get(id)?.class))) {
        for (const id of selected) {
          let node = sim.byId.get(id);
          for (let depth = 0; node && depth <= sim.nodes.length; depth++, node = sim.byId.get(node.parent)) {
            if (['Part', 'MeshPart'].includes(node.class)) { anchors.add(node.id); break; }
          }
        }
      }
      for (const node of sim.nodes) if (node.class === 'Attachment') {
        let parent = sim.byId.get(node.parent);
        for (let depth = 0; parent && depth <= sim.nodes.length; depth++, parent = sim.byId.get(parent.parent)) {
          if (anchors.has(parent.id)) { anchors.add(node.id); break; }
        }
      }
      for (const time of times) {
        sim.seek(time);
        for (const id of anchors) {
          const node = sim.byId.get(id), frame = sim.frameOf(node);
          if (node.class === 'Attachment') grow(frame.p);
          else for (let k = 0; k < 8; k++) grow(add(frame.p, apply(frame.m, frame.size.map((v, i) => ((k >> i) & 1 ? 1 : -1) * v / 2))));
        }
      }
    }
    if (!Number.isFinite(min[0])) return null;
    return {...boundsOf(min, max), particles: particles.length, retained, percentile, fallback: particles.length === 0,
      ...(fitPoints.length ? {fitPoints} : {})};
  }

  // Fit the sampled quad corners in camera coordinates. An axis-aligned cube
  // invents depth around a billboard and makes its visible footprint too small.
  function particleCamera(input, options = {}) {
    const points = options.points || [];
    if (!points.length) return autoCamera(input, options);
    const basis = cameraBasis(options.camera || input?.camera);
    const coordinates = points.map(p => [dot(p, basis.right), dot(p, basis.up), dot(p, basis.forward)]);
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (const p of coordinates) for (let i = 0; i < 3; i++) { min[i] = Math.min(min[i], p[i]); max[i] = Math.max(max[i], p[i]); }
    const midpoint = scale(add(min, max), .5);
    const center = add(add(scale(basis.right, midpoint[0]), scale(basis.up, midpoint[1])), scale(basis.forward, midpoint[2]));
    const tanV = Math.tan(basis.fov * Math.PI / 360), tanH = tanV * (options.aspect || 16 / 9);
    const fill = .875;
    let distance = .2;
    for (const p of coordinates) {
      const rel = sub(p, midpoint);
      distance = Math.max(distance, Math.abs(rel[0]) / (tanH * fill) - rel[2], Math.abs(rel[1]) / (tanV * fill) - rel[2], .1 - rel[2]);
    }
    return {position: add(center, scale(basis.forward, -distance)), target: center, fov: basis.fov};
  }

  // Une sphère remplit 87,5 % du plus petit champ : tan(alpha) = 0,875 * tan(demi-champ).
  // sin(alpha) = rayon / distance évite de cadrer les huit coins d'un cube englobant.
  function sphereCamera(input, options = {}) {
    const basis = cameraBasis(options.camera || input?.camera);
    const center = vec(options.center), radius = Math.max(1e-6, num(options.radius, 1));
    const tangent = Math.tan(basis.fov * Math.PI / 360) * Math.min(1, options.aspect || 16 / 9) * 0.875;
    const distance = Math.max(radius + 0.051, radius * Math.sqrt(1 + tangent * tangent) / tangent);
    return {position: add(center, scale(basis.forward, -distance)), target: center.slice(), fov: basis.fov};
  }

  // Mannequin R15 simplifié (≈ 5,2 studs, pieds au sol), à gauche de l’effet vu depuis la caméra, tourné vers elle.
  const DUMMY = [[[0, 4.6, 0], [1.2, 1.2, 1.2]], [[0, 3, 0], [2, 2, 1]], [[-1.5, 3, 0], [1, 2, 1]], [[1.5, 3, 0], [1, 2, 1]], [[-0.5, 1, 0], [1, 2, 1]], [[0.5, 1, 0], [1, 2, 1]]];
  function dummyParts(bounds, cameraInput) {
    const camera = cameraBasis(cameraInput);
    const flat = normalize([camera.right[0], 0, camera.right[2]], [1, 0, 0]);
    const center = bounds ? bounds.center : [0, 0, 0];
    const corners = bounds ? [0, 1, 2, 3, 4, 5, 6, 7].map(k => [0, 1, 2].map(i => (k >> i) & 1 ? bounds.max[i] : bounds.min[i])) : [];
    const reach = bounds ? Math.max(...corners.map(c => Math.abs(dot(sub(c, center), flat)))) : 2;
    const base = add([center[0], 0, center[2]], scale(flat, -(reach + 1.8)));
    const toCamera = sub(camera.position, base);
    const m = rotation(1, Math.atan2(toCamera[0], toCamera[2]) * 180 / Math.PI);
    return DUMMY.map(([offset, size]) => ({node: 'dummy', shape: 'Block', p: add(base, apply(m, offset)), m, size, color: [0.5, 0.52, 0.58], alpha: 1, neon: false, depth: 0}));
  }
  const dummyBounds = parts => parts.reduce((acc, part) => unionBounds(acc, boundsOf(sub(part.p, scale(part.size, 0.75)), add(part.p, scale(part.size, 0.75)))), null);

  // Garde la direction de la caméra donnée et recule jusqu’à voir toute l’étendue (et le mannequin).
  function autoCamera(input, options = {}) {
    let bounds = options.bounds !== undefined ? options.bounds : effectBounds(input, options);
    const reference = options.camera || input?.camera;
    if (options.dummy) bounds = unionBounds(bounds, dummyBounds(dummyParts(bounds, reference)));
    const basis = cameraBasis(reference);
    if (!bounds) return {position: basis.position, target: basis.target, fov: basis.fov};
    // Distance minimale pour que les 8 coins de la boîte tiennent dans le champ horizontal et vertical.
    const tanV = Math.tan(basis.fov * Math.PI / 360), tanH = tanV * (options.aspect || 16 / 9);
    let distance = 2;
    for (let k = 0; k < 8; k++) {
      const corner = [0, 1, 2].map(i => (k >> i) & 1 ? bounds.max[i] : bounds.min[i]);
      const rel = sub(corner, bounds.center), along = dot(rel, basis.forward);
      distance = Math.max(distance, Math.abs(dot(rel, basis.right)) / tanH - along, Math.abs(dot(rel, basis.up)) / tanV - along, 0.5 - along);
    }
    distance = clamp(distance * (options.margin || 1.06), 2, 1500);
    const round = v => v.map(x => Math.round(x * 1000) / 1000);
    return {position: round(add(bounds.center, scale(basis.forward, -distance))), target: round(bounds.center), fov: basis.fov};
  }

  // ---- Rendu WebGL2 ----
  const FX_VERTEX = `#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUv; layout(location=2) in vec2 aUv2; layout(location=3) in vec4 aColor; layout(location=4) in vec2 aMisc;
uniform mat4 uViewProj; out vec2 vUv; out vec2 vUv2; out vec4 vColor; out vec2 vMisc;
void main(){vUv=aUv;vUv2=aUv2;vColor=aColor;vMisc=aMisc;gl_Position=uViewProj*vec4(aPos,1.0);}`;
  // LightEmission 0 = mélange normal, 1 = mélange additif (alpha prémultiplié, blendFunc ONE / ONE_MINUS_SRC_ALPHA).
  const FX_FRAGMENT = `#version 300 es
precision mediump float; uniform sampler2D uTex; in vec2 vUv; in vec2 vUv2; in vec4 vColor; in vec2 vMisc; out vec4 outColor;
void main(){vec4 t=texture(uTex,vUv);if(vMisc.x>0.0)t=mix(t,texture(uTex,vUv2),vMisc.x);float a=t.a*vColor.a;outColor=vec4(t.rgb*vColor.rgb*a,a*(1.0-vMisc.y));}`;
  const SOLID_VERTEX = `#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNormal;
uniform mat4 uViewProj; uniform mat4 uModel; uniform mat3 uNormal; out vec3 vWorld; out vec3 vNormal;
void main(){vec4 w=uModel*vec4(aPos,1.0);vWorld=w.xyz;vNormal=normalize(uNormal*aNormal);gl_Position=uViewProj*w;}`;
  const SOLID_FRAGMENT = `#version 300 es
precision highp float; in vec3 vWorld; in vec3 vNormal; out vec4 outColor;
uniform vec3 uColor; uniform float uAlpha; uniform int uMode; uniform vec3 uGround;
uniform int uLightCount; uniform vec3 uLightPos[8]; uniform vec3 uLightColor[8]; uniform float uLightRange[8]; uniform vec4 uLightCone[8];
vec3 lightAt(vec3 p,vec3 n){vec3 sum=vec3(0.0);for(int i=0;i<8;i++){if(i>=uLightCount)break;vec3 d=uLightPos[i]-p;float dist=length(d);if(dist>uLightRange[i]||uLightRange[i]<=0.0)continue;vec3 l=d/max(dist,1e-4);float fall=1.0-dist/uLightRange[i];float cone=1.0;if(uLightCone[i].w>0.0){float c=dot(-l,uLightCone[i].xyz);cone=smoothstep(cos(radians(uLightCone[i].w*0.5)),cos(radians(uLightCone[i].w*0.5))+0.05,c);}sum+=uLightColor[i]*fall*fall*max(dot(n,l),0.0)*cone;}return sum;}
void main(){vec3 n=normalize(vNormal);
if(uMode==1){outColor=vec4(uColor*uAlpha,uAlpha);return;}
if(uMode==2){vec2 g=abs(fract(vWorld.xz-0.5)-0.5)/fwidth(vWorld.xz);float line=1.0-min(min(g.x,g.y),1.0);vec2 m=abs(fract(vWorld.xz/10.0-0.5)-0.5)/fwidth(vWorld.xz/10.0);float major=1.0-min(min(m.x,m.y),1.0);float fade=clamp(1.0-length(vWorld.xz)/90.0,0.0,1.0);vec3 base=uGround+uGround*lightAt(vWorld,vec3(0.0,1.0,0.0))*3.0+lightAt(vWorld,vec3(0.0,1.0,0.0))*0.25;outColor=vec4(base+vec3(0.09,0.08,0.11)*(line*0.35+major*0.5)*fade,1.0);return;}
vec3 sun=normalize(vec3(0.45,1.0,0.3));float diffuse=max(dot(n,sun),0.0);vec3 c=uColor*(0.42+0.58*diffuse)+uColor*lightAt(vWorld,n);outColor=vec4(c*uAlpha,uAlpha);}`;
  const SKIES = {sombre: [0.098, 0.082, 0.133], gris: [0.42, 0.42, 0.45], ciel: [0.53, 0.71, 0.92], noir: [0, 0, 0], roblox: [0.64, 0.81, 0.94], dark: [0.035, 0.045, 0.08]};
  // An explicit preview preset wins; otherwise use each recipe's own background.
  function environmentColors(project, background) {
    const value = background || project?.environment?.background;
    const sky = typeof value === 'string' && /^#[\da-f]{6}$/i.test(value)
      ? [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16) / 255)
      : (SKIES[value] || SKIES.sombre).slice();
    return {sky, ground: value === 'roblox' ? [0.64, 0.64, 0.64] : value === 'dark' ? [0.16, 0.16, 0.17] : sky.map(v => v * 0.82 + 0.012)};
  }

  function perspective(fovY, aspect, near, far) {
    const f = 1 / Math.tan(fovY / 2), nf = 1 / (near - far);
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
  }
  function lookAt(camera) {
    const {position: e, right: x, up: y, forward} = camera, z = scale(forward, -1);
    return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, e), -dot(y, e), -dot(z, e), 1];
  }
  function mat4Mul(a, b) {
    const out = new Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) out[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    return out;
  }
  function model(m, p, s) {
    return [m[0] * s[0], m[3] * s[0], m[6] * s[0], 0, m[1] * s[1], m[4] * s[1], m[7] * s[1], 0, m[2] * s[2], m[5] * s[2], m[8] * s[2], 0, p[0], p[1], p[2], 1];
  }
  const normalMatrix = (m, s) => [m[0] / s[0], m[3] / s[0], m[6] / s[0], m[1] / s[1], m[4] / s[1], m[7] / s[1], m[2] / s[2], m[5] / s[2], m[8] / s[2]];

  function meshes() {
    const box = [], wire = [], sphere = [], cylinder = [];
    const faces = [[[1, 0, 0], [0, 1, 0], [0, 0, 1]], [[-1, 0, 0], [0, 1, 0], [0, 0, -1]], [[0, 1, 0], [0, 0, 1], [1, 0, 0]], [[0, -1, 0], [0, 0, -1], [1, 0, 0]], [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]];
    for (const [n, u, v] of faces) {
      const corner = (a, b) => add(scale(n, 0.5), add(scale(u, a * 0.5), scale(v, b * 0.5)));
      for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]]) box.push(...corner(a, b), ...n);
    }
    for (const a of [-0.5, 0.5]) for (const b of [-0.5, 0.5]) wire.push(-0.5, a, b, 0, 1, 0, 0.5, a, b, 0, 1, 0, a, -0.5, b, 0, 1, 0, a, 0.5, b, 0, 1, 0, a, b, -0.5, 0, 1, 0, a, b, 0.5, 0, 1, 0);
    const rows = 14, cols = 24;
    const sp = (i, j) => { const th = i / rows * Math.PI, ph = j / cols * Math.PI * 2; const n = [Math.sin(th) * Math.cos(ph), Math.cos(th), Math.sin(th) * Math.sin(ph)]; return [...scale(n, 0.5), ...n]; };
    for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) sphere.push(...sp(i, j), ...sp(i + 1, j), ...sp(i + 1, j + 1), ...sp(i, j), ...sp(i + 1, j + 1), ...sp(i, j + 1));
    // Cylindre Roblox : axe X.
    for (let j = 0; j < cols; j++) {
      const a = j / cols * Math.PI * 2, b = (j + 1) / cols * Math.PI * 2;
      const ring = (ang, x) => [x, Math.cos(ang) * 0.5, Math.sin(ang) * 0.5];
      const n = ang => [0, Math.cos(ang), Math.sin(ang)];
      cylinder.push(...ring(a, -0.5), ...n(a), ...ring(b, -0.5), ...n(b), ...ring(b, 0.5), ...n(b), ...ring(a, -0.5), ...n(a), ...ring(b, 0.5), ...n(b), ...ring(a, 0.5), ...n(a));
      for (const x of [-0.5, 0.5]) cylinder.push(x, 0, 0, Math.sign(x), 0, 0, ...ring(a, x), Math.sign(x), 0, 0, ...ring(b, x), Math.sign(x), 0, 0);
    }
    const ground = [];
    for (const [x, z] of [[-1, -1], [1, 1], [1, -1], [-1, -1], [-1, 1], [1, 1]]) ground.push(x * 120, 0, z * 120, 0, 1, 0);
    return {box, wire, sphere, cylinder, ground};
  }

  function proceduralTexture(kind) {
    const canvas = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(128, 128) : document.createElement('canvas');
    canvas.width = canvas.height = 128;
    const ctx = canvas.getContext('2d');
    const glow = (r, a) => { const g = ctx.createRadialGradient(64, 64, 0, 64, 64, r); g.addColorStop(0, `rgba(255,255,255,${a})`); g.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128); };
    if (kind === 'white') { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 128, 128); }
    else if (kind === 'sparkle') {
      glow(30, 0.9);
      ctx.globalCompositeOperation = 'lighter';
      for (const [w, h] of [[60, 3], [3, 60]]) { const g = ctx.createRadialGradient(64, 64, 0, 64, 64, Math.max(w, h)); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = g; ctx.fillRect(64 - w, 64 - h, w * 2, h * 2); }
      glow(10, 1);
    } else if (kind === 'smoke') {
      const rng = random(7);
      for (let i = 0; i < 26; i++) { const x = 34 + rng() * 60, y = 34 + rng() * 60, r = 14 + rng() * 22; const g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, 'rgba(235,235,235,0.28)'); g.addColorStop(1, 'rgba(235,235,235,0)'); ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128); }
    } else glow(62, 1);
    return canvas;
  }
  function builtinKind(uri) {
    if (!uri) return 'white';
    const s = String(uri).toLowerCase();
    if (!s.startsWith('rbxasset://')) return null;
    return s.includes('sparkle') ? 'sparkle' : s.includes('smoke') ? 'smoke' : 'soft';
  }
  function assetId(uri) {
    const s = String(uri || '').trim();
    const m = s.match(/^(?:rbxassetid:\/\/)?(\d+)$/) || s.match(/[?&]id=(\d+)$/);
    return m ? m[1] : null;
  }

  function createRenderer(canvas, options = {}) {
    const gl = canvas.getContext('webgl2', {premultipliedAlpha: true, alpha: false, antialias: true, preserveDrawingBuffer: !!options.preserveDrawingBuffer});
    if (!gl) throw new Error('WebGL2 indisponible dans ce navigateur : l’émulation ne peut pas s’afficher.');
    const base = options.assetBase ?? '';
    const warnings = new Set();
    function compile(vs, fs) {
      const program = gl.createProgram();
      for (const [type, source] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
        const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error('Shader : ' + gl.getShaderInfoLog(shader));
        gl.attachShader(program, shader);
      }
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('Programme : ' + gl.getProgramInfoLog(program));
      const uniforms = {};
      for (let i = 0; i < gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS); i++) { const info = gl.getActiveUniform(program, i); uniforms[info.name.replace('[0]', '')] = gl.getUniformLocation(program, info.name); }
      return {program, uniforms};
    }
    const fx = compile(FX_VERTEX, FX_FRAGMENT), solid = compile(SOLID_VERTEX, SOLID_FRAGMENT);
    const fxVao = gl.createVertexArray(), fxBuffer = gl.createBuffer();
    gl.bindVertexArray(fxVao); gl.bindBuffer(gl.ARRAY_BUFFER, fxBuffer);
    for (const [index, size, offset] of [[0, 3, 0], [1, 2, 3], [2, 2, 5], [3, 4, 7], [4, 2, 11]]) { gl.enableVertexAttribArray(index); gl.vertexAttribPointer(index, size, gl.FLOAT, false, STRIDE * 4, offset * 4); }
    const geometry = {};
    for (const [name, values] of Object.entries(meshes())) {
      const vao = gl.createVertexArray(), buffer = gl.createBuffer();
      gl.bindVertexArray(vao); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
      gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
      geometry[name] = {vao, count: values.length / 6};
    }
    gl.bindVertexArray(null);

    const textures = new Map();
    function upload(source) {
      const texture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
      return texture;
    }
    const builtins = {};
    const builtin = kind => builtins[kind] || (builtins[kind] = upload(proceduralTexture(kind)));
    function texture(uri) {
      const kind = builtinKind(uri);
      if (kind) return builtin(kind);
      const key = String(uri);
      let entry = textures.get(key);
      if (!entry) {
        entry = {state: 'loading', texture: null, promise: null};
        textures.set(key, entry);
        const id = assetId(uri);
        // resolveTexture(id) peut donner l’adresse exacte connue du catalogue ; sinon les trois collections sont essayées.
        const candidates = !id ? [] : options.resolveTexture?.(id) || ['images', 'beams/images', 'meshes/images'].map(folder => `${base}/library/${folder}/${id}.png`);
        entry.promise = (async () => {
          for (const url of candidates) {
            try {
              const image = new Image();
              image.decoding = 'async';
              await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
              entry.texture = upload(image); entry.state = 'ready';
              options.onTexture?.(uri);
              return;
            } catch (_) {}
          }
          entry.state = 'failed';
          warnings.add(`Texture ${uri} absente de la bibliothèque locale : aperçu remplacé par un halo doux.`);
          options.onTexture?.(uri);
        })();
      }
      return entry.texture || builtin('soft');
    }
    function preload(project) {
      const pending = [];
      for (const node of project?.nodes || []) {
        const uri = node.properties?.Texture ?? (['ParticleEmitter'].includes(node.class) ? NATIVE.ParticleEmitter.Texture : undefined);
        if (uri === undefined || builtinKind(uri)) continue;
        texture(uri);
        const promise = textures.get(String(uri))?.promise;
        if (promise) pending.push(promise);
      }
      return Promise.all(pending);
    }

    function render(sim, cameraInput, view = {}) {
      const width = canvas.width, height = canvas.height;
      gl.viewport(0, 0, width, height);
      const {sky, ground} = environmentColors(sim.project, view.background);
      gl.clearColor(sky[0], sky[1], sky[2], 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const scene = buildFrame(sim, cameraInput);
      const viewProj = mat4Mul(perspective(scene.camera.fov * Math.PI / 180, width / Math.max(1, height), 0.1, 2000), lookAt(scene.camera));
      gl.useProgram(solid.program);
      gl.uniformMatrix4fv(solid.uniforms.uViewProj, false, viewProj);
      const lights = scene.lights.slice(0, 8);
      gl.uniform1i(solid.uniforms.uLightCount, lights.length);
      if (lights.length) {
        gl.uniform3fv(solid.uniforms.uLightPos, lights.flatMap(l => l.p));
        gl.uniform3fv(solid.uniforms.uLightColor, lights.flatMap(l => scale(l.color, l.brightness)));
        gl.uniform1fv(solid.uniforms.uLightRange, lights.map(l => l.range));
        gl.uniform4fv(solid.uniforms.uLightCone, lights.flatMap(l => l.kind === 'PointLight' ? [0, 0, 0, 0] : [...l.direction, Math.max(1, l.angle)]));
      }
      const drawSolid = (name, m, p, s, color, alpha, mode, primitive = gl.TRIANGLES) => {
        const safe = s.map(v => Math.max(1e-4, Math.abs(v)));
        gl.uniformMatrix4fv(solid.uniforms.uModel, false, model(m, p, safe));
        gl.uniformMatrix3fv(solid.uniforms.uNormal, false, normalMatrix(m, safe));
        gl.uniform3fv(solid.uniforms.uColor, color); gl.uniform1f(solid.uniforms.uAlpha, alpha); gl.uniform1i(solid.uniforms.uMode, mode);
        gl.bindVertexArray(geometry[name].vao); gl.drawArrays(primitive, 0, geometry[name].count);
      };
      gl.enable(gl.DEPTH_TEST); gl.depthMask(true); gl.disable(gl.BLEND); gl.disable(gl.CULL_FACE);
      if (view.ground !== false) {
        gl.uniform3fv(solid.uniforms.uGround, ground);
        drawSolid('ground', IDENTITY, [0, 0, 0], [1, 1, 1], [0, 0, 0], 1, 2);
      }
      // Part Ball : sphère du plus petit côté ; Part Cylinder : axe X ; SpecialMesh Sphere/Cylinder : ellipsoïde, axe Y.
      const meshFor = part => {
        if (part.shape === 'MeshCylinder') return {name: 'cylinder', m: matMul(part.m, rotation(2, 90)), size: [part.size[1], part.size[0], part.size[2]]};
        if (part.shape === 'MeshSphere') return {name: 'sphere', m: part.m, size: part.size};
        if (part.shape === 'Ball') { const d = Math.min(...part.size); return {name: 'sphere', m: part.m, size: [d, d, d]}; }
        return {name: part.shape === 'Cylinder' ? 'cylinder' : 'box', m: part.m, size: part.size};
      };
      const solids = view.extraParts ? scene.parts.concat(view.extraParts) : scene.parts;
      for (const part of solids.filter(p => p.alpha >= 0.999)) { const g = meshFor(part); drawSolid(g.name, g.m, part.p, g.size, part.color, 1, part.neon ? 1 : 0); }
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false);
      for (const box of scene.placeholders) drawSolid('wire', box.frame.m, box.frame.p, box.size, [0.66, 0.56, 0.88], 0.8, 1, gl.LINES);
      for (const part of scene.parts.filter(p => p.alpha < 0.999).sort((a, b) => b.depth - a.depth)) { const g = meshFor(part); drawSolid(g.name, g.m, part.p, g.size, part.color, part.alpha, part.neon ? 1 : 0); }
      if (scene.vertices) {
        gl.useProgram(fx.program);
        gl.uniformMatrix4fv(fx.uniforms.uViewProj, false, viewProj);
        gl.uniform1i(fx.uniforms.uTex, 0); gl.activeTexture(gl.TEXTURE0);
        gl.bindVertexArray(fxVao); gl.bindBuffer(gl.ARRAY_BUFFER, fxBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, scene.data, gl.STREAM_DRAW);
        for (const batch of scene.batches) { gl.bindTexture(gl.TEXTURE_2D, texture(batch.texture)); gl.drawArrays(gl.TRIANGLES, batch.first, batch.count); }
      }
      gl.depthMask(true); gl.bindVertexArray(null);
      if (scene.placeholders.length) warnings.add('Les MeshPart et maillages FileMesh sont affichés comme boîtes : leur géométrie n’est disponible que dans Roblox.');
      return scene;
    }
    return {gl, render, preload, warnings, texture};
  }

  // ---- Vue interactive : lecture, timeline, caméra orbitale ----
  function createView(canvas, options = {}) {
    const renderer = createRenderer(canvas, {assetBase: options.assetBase, resolveTexture: options.resolveTexture, preserveDrawingBuffer: true, onTexture: () => draw()});
    let sim = null, signature = '', playing = false, frameRequest = 0, last = 0;
    let mode = options.mode === 'free' ? 'free' : 'timeline';
    let camera = {position: [10, 6, 12], target: [0, 1, 0], fov: 50};
    const view = {background: options.background, ground: options.ground !== false, dummy: !!options.dummy, extraParts: null};
    let bounds;
    const currentBounds = () => bounds !== undefined ? bounds : (bounds = sim ? effectBounds(sim.project, {seed: options.seed}) : null);
    const placeDummy = () => { view.extraParts = view.dummy && sim ? dummyParts(currentBounds(), camera) : null; };
    const projectCamera = project => ({position: vec(project?.camera?.position, [10, 6, 12]).slice(), target: vec(project?.camera?.target, [0, 1, 0]).slice(), fov: num(project?.camera?.fov, 50)});
    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(global.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round(rect.width * dpr)), h = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    }
    // fromPlayback : l’image vient de la lecture (la timeline doit suivre), pas d’un seek ou d’un redimensionnement.
    const notify = fromPlayback => options.onFrame?.({time: sim.time, playing, mode, ended: sim.ended, fromPlayback, ...sim.stats(), warnings: [...renderer.warnings]});
    function draw(fromPlayback = false) {
      if (!sim || !canvas.isConnected) return null;
      resize();
      const scene = renderer.render(sim, camera, view);
      notify(fromPlayback);
      return scene;
    }
    function tick(now) {
      frameRequest = 0;
      if (!playing || !sim) return;
      sim.advance(last ? (now - last) / 1000 : 0);
      last = now;
      draw(true);
      if (sim.ended && !sim.alive) { playing = false; notify(true); return; }
      frameRequest = requestAnimationFrame(tick);
    }
    function halt() { playing = false; if (frameRequest) cancelAnimationFrame(frameRequest); frameRequest = 0; }
    const api = {
      renderer, view,
      setProject(project, {keepCamera = true} = {}) {
        const next = JSON.stringify(project);
        if (next === signature) return false;
        const first = !sim;
        const time = sim ? sim.time : 0;
        signature = next;
        if (sim && mode === 'free') sim.updateProject(project);
        else sim = createSimulation(project, {seed: options.seed, mode});
        bounds = undefined;
        if (first || !keepCamera) camera = projectCamera(project);
        placeDummy();
        renderer.preload(project).then(() => draw());
        if (!playing && mode !== 'free') sim.seek(time);
        draw();
        return true;
      },
      updateProject(project, options) { return api.setProject(project, options); },
      resetPreviewState() { signature = ''; bounds = undefined; last = 0; sim?.resetPreviewState(); },
      play() { if (!sim) return; if (mode !== 'free') sim.reset(); playing = true; last = 0; if (!frameRequest) frameRequest = requestAnimationFrame(tick); draw(); },
      pause() { halt(); draw(); },
      resume() { if (!sim || playing) return; playing = true; last = 0; if (!frameRequest) frameRequest = requestAnimationFrame(tick); },
      stop() { halt(); if (sim) sim.stop(); draw(); },
      seek(time) { halt(); if (sim) sim.seek(time); draw(); },
      setMode(next) { mode = next === 'free' ? 'free' : 'timeline'; if (sim) sim.setMode(mode); last = 0; draw(); return mode; },
      emit(ids, count) { const emitted = sim ? sim.emit(ids, count) : 0; draw(); return emitted; },
      setEnabled(id, value) { const changed = sim ? sim.setEnabled(id, value) : false; draw(); return changed; },
      isEnabled(id) { return sim ? sim.isEnabled(id) : false; },
      clearParticles() { if (sim) sim.clearParticles(); draw(); },
      draw, resize,
      get playing() { return playing; }, get time() { return sim ? sim.time : 0; }, get mode() { return mode; },
      get camera() { return JSON.parse(JSON.stringify(camera)); },
      setCamera(next) { camera = {...camera, ...next}; draw(); },
      resetCamera(project) { camera = projectCamera(project || sim?.project); placeDummy(); draw(); },
      setView(next) { Object.assign(view, next); if ('dummy' in next) placeDummy(); draw(); },
      // Cadre toute l’étendue de l’effet depuis l’angle de vue actuel.
      frameEffect(ids) {
        if (!sim) return null;
        const selectedBounds = ids == null ? currentBounds() : effectBounds(sim.project, {seed: options.seed, ids});
        camera = autoCamera(sim.project, {bounds: selectedBounds, camera, dummy: ids == null && view.dummy, aspect: canvas.width / Math.max(1, canvas.height)});
        placeDummy(); draw(); options.onCamera?.(api.camera);
        return api.camera;
      },
      snapshot(type = 'image/png') { draw(); return canvas.toDataURL(type); },
      destroy() { halt(); },
    };
    // Glisser : orbite ; Maj ou clic droit : déplacement ; molette : zoom.
    let drag = null;
    canvas.addEventListener('contextmenu', e => e.preventDefault());
    canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2 || e.button === 1}; canvas.setPointerCapture?.(e.pointerId); });
    canvas.addEventListener('pointermove', e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      drag.x = e.clientX; drag.y = e.clientY;
      const offset = sub(camera.position, camera.target), distance = length(offset);
      if (drag.pan) {
        const basis = cameraBasis(camera), k = distance * 0.0016;
        const move = add(scale(basis.right, -dx * k), scale(basis.up, dy * k));
        camera.position = add(camera.position, move); camera.target = add(camera.target, move);
      } else {
        const yaw = -dx * 0.008, pitch = clamp(Math.asin(clamp(offset[1] / distance, -1, 1)) + dy * 0.008, -1.45, 1.45);
        const flat = Math.atan2(offset[2], offset[0]) + yaw;
        camera.position = add(camera.target, [Math.cos(flat) * Math.cos(pitch) * distance, Math.sin(pitch) * distance, Math.sin(flat) * Math.cos(pitch) * distance]);
      }
      if (!playing) draw();
    });
    const release = () => { if (drag) { drag = null; placeDummy(); if (!playing) draw(); options.onCamera?.(api.camera); } };
    canvas.addEventListener('pointerup', release); canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('wheel', e => {
      e.preventDefault();
      const offset = sub(camera.position, camera.target);
      const distance = clamp(length(offset) * Math.exp(e.deltaY * 0.0012), 1, 500);
      camera.position = add(camera.target, scale(normalize(offset), distance));
      if (!playing) draw();
      options.onCamera?.(api.camera);
    }, {passive: false});
    return api;
  }

  // Planche d’images à des instants précis : la même recette donne toujours la même planche.
  // Une ligne par projet pour comparer des variantes avec la même caméra et les mêmes instants.
  async function renderRows(projects, options = {}) {
    const times = renderTimes(projects, options);
    const width = options.width || 480, height = options.height || 270, label = 22;
    const backgrounds = options.backgrounds || [options.background];
    const comparisons = projects.flatMap((project, projectIndex) => backgrounds.map(background => ({project, projectIndex, background})));
    const compare = comparisons.length > 1;
    const columns = compare ? times.length : Math.max(1, Math.min(options.columns || 4, times.length));
    const cells = comparisons.flatMap((entry, row) => times.map(time => ({...entry, row, time})));
    const rows = Math.ceil(cells.length / columns);
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const renderer = createRenderer(canvas, {assetBase: options.assetBase, resolveTexture: options.resolveTexture, preserveDrawingBuffer: true});
    await Promise.all(projects.map(p => renderer.preload(p)));
    const reference = options.camera || projects[0]?.camera;
    let bounds = null;
    if (options.autoCamera || options.dummy) for (const p of projects) bounds = unionBounds(bounds, effectBounds(p, {seed: options.seed}));
    const camera = options.autoCamera ? autoCamera(projects[0], {bounds, camera: reference, dummy: options.dummy, aspect: width / height}) : reference;
    const extraParts = options.dummy ? dummyParts(bounds, camera) : null;
    const sheet = document.createElement('canvas');
    sheet.width = columns * width; sheet.height = rows * (height + label);
    const ctx = sheet.getContext('2d');
    ctx.fillStyle = '#0d0b12'; ctx.fillRect(0, 0, sheet.width, sheet.height);
    const frames = [], sims = projects.map(p => createSimulation(p, {seed: options.seed}));
    for (const [i, cell] of cells.entries()) {
      const sim = sims[cell.projectIndex];
      sim.seek(cell.time);
      renderer.render(sim, camera, {background: cell.background, ground: options.ground, extraParts});
      const x = (i % columns) * width, y = Math.floor(i / columns) * (height + label);
      ctx.drawImage(canvas, x, y + label);
      ctx.fillStyle = '#e8e0f0'; ctx.font = '13px monospace';
      const particles = sim.stats().particles;
      const timing = `t = ${sim.time.toFixed(2)} s · ${particles} particule${particles > 1 ? 's' : ''}`;
      const prefix = compare ? `${String.fromCharCode(65 + cell.row % 26)}${options.backgrounds ? ' [' + cell.background + ']' : ''} ` : '';
      let name = compare ? cell.project?.name || '' : '';
      const fullName = name;
      while (name && ctx.measureText(prefix + name + (name === fullName ? '' : '…') + ' · ' + timing).width > width - 16) name = name.slice(0, -1);
      const caption = prefix + (name ? name + (name === fullName ? '' : '…') + ' · ' : '') + timing;
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, width, label); ctx.clip();
      ctx.fillText(caption, x + 8, y + 15); ctx.restore();
      if (options.individual) frames.push({row: cell.row, project: cell.projectIndex, background: cell.background, time: sim.time, image: canvas.toDataURL('image/png')});
    }
    return {image: sheet.toDataURL('image/png'), frames, times: times.map(t => Math.round(t / STEP) * STEP), camera, bounds,
      rows: comparisons.map((entry, row) => ({row, project: entry.projectIndex, name: entry.project?.name, background: entry.background || entry.project?.environment?.background || 'sombre'})),
      sheet: {width: sheet.width, height: sheet.height, rows, columns}, warnings: [...renderer.warnings]};
  }
  const renderSheet = (project, options = {}) => renderRows([project], options);
  const renderComparison = (projects, options = {}) => renderRows(projects, options);

  function renderTimes(projects, options = {}) {
    const longest = Math.max(...projects.map(p => num(p?.duration, 3)));
    const count = options.frames || 8;
    return Array.isArray(options.times) && options.times.length ? options.times : Array.from({length: count}, (_, i) => longest * (i + 0.5) / count);
  }

  // Emprise alpha des miniatures réellement chargées par le rendu. Les coordonnées renvoyées
  // sont locales au quad (0..1), y compris quand ses UV désignent une case de flipbook.
  // Une image inaccessible garde le quad entier ; une case vide ne contribue pas au cadrage.
  async function textureAlphaBounds(projects, options = {}) {
    const full = () => ({min: [0, 0], max: [1, 1]});
    const fullPoints = () => [[0,0],[1,0],[1,1],[0,1]];
    const alphaPercentile = clamp(num(options.alphaPercentile, 100), Number.EPSILON, 100);
    const alphaPower = Math.max(Number.EPSILON, num(options.alphaPower, 1));
    const textures = new Map(), cache = new Map(), pointCache = new Map(), base = options.assetBase ?? '';
    const hull = points => {
      if (!points?.length) return null;
      const sorted = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
      const lower = [], upper = [];
      for (const p of sorted) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop(); lower.push(p); }
      for (let i = sorted.length - 1; i >= 0; i--) { const p = sorted[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop(); upper.push(p); }
      lower.pop(); upper.pop(); return lower.concat(upper);
    };
    const uris = new Set(projects.flatMap(project => (project.nodes || [])
      .filter(node => node.class === 'ParticleEmitter').map(node => node.properties?.Texture ?? NATIVE.ParticleEmitter.Texture)));
    if (typeof Image !== 'undefined') await Promise.all([...uris].map(async uri => {
      try {
        const kind = builtinKind(uri);
        let source;
        if (kind) source = proceduralTexture(kind);
        else {
          const id = assetId(uri), resolved = id && options.resolveTexture?.(id);
          const candidates = resolved == null
            ? (id ? ['images', 'beams/images', 'meshes/images'].map(folder => `${base}/library/${folder}/${id}.png`) : [])
            : (Array.isArray(resolved) ? resolved : [resolved]);
          for (const url of candidates) {
            try {
              const image = new Image(); image.decoding = 'async';
              await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
              source = image; break;
            } catch (_) {}
          }
        }
        if (!source) return;
        const width = source.naturalWidth || source.width, height = source.naturalHeight || source.height;
        const canvas = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(width, height) : document.createElement('canvas');
        canvas.width = width; canvas.height = height;
        const context = canvas.getContext('2d'); context.drawImage(source, 0, 0);
        const pixels = context.getImageData(0, 0, width, height).data, alpha = new Uint8Array(width * height);
        for (let i = 0; i < alpha.length; i++) alpha[i] = pixels[i * 4 + 3];
        textures.set(String(uri), {width, height, alpha});
      } catch (_) { /* Sans accès aux pixels, conserver prudemment la demi-taille complète. */ }
    }));
    const rect = (uri, uv) => {
      const texture = textures.get(String(uri));
      if (!texture) return full();
      const key = JSON.stringify([uri, uv]);
      if (cache.has(key)) return cache.get(key);
      const {width, height, alpha} = texture;
      const u0 = Math.min(...uv.map(p => p[0])), u1 = Math.max(...uv.map(p => p[0]));
      const v0 = Math.min(...uv.map(p => p[1])), v1 = Math.max(...uv.map(p => p[1]));
      if (!(u1 > u0 && v1 > v0)) return full();
      const left = clamp(Math.floor(u0 * width), 0, width), right = clamp(Math.ceil(u1 * width), 0, width);
      const top = clamp(Math.floor(v0 * height), 0, height), bottom = clamp(Math.ceil(v1 * height), 0, height);
      let minX = right, minY = bottom, maxX = left - 1, maxY = top - 1;
      // Le centile est normalisé par la masse de la case : une texture entièrement
      // pâle garde la même emprise. La puissance 2 mesure l'énergie du contraste.
      let alphaCenter = [0,0], distanceCutoff = Infinity;
      if (alphaPercentile < 100) {
        const occupied = []; let mass = 0;
        for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
          const a = alpha[y * width + x];
          if (a > 0) {
            const weight = Math.pow(a / 255, alphaPower);
            occupied.push({x, y, weight}); mass += weight; alphaCenter[0] += (x + .5) * weight; alphaCenter[1] += (y + .5) * weight;
          }
        }
        if (mass) {
          alphaCenter = alphaCenter.map(v => v / mass);
          for (const pixel of occupied) pixel.distance = Math.hypot(pixel.x + .5 - alphaCenter[0], pixel.y + .5 - alphaCenter[1]);
          occupied.sort((a, b) => a.distance - b.distance);
          let retainedMass = 0;
          for (const pixel of occupied) { retainedMass += pixel.weight; if (retainedMass >= mass * alphaPercentile / 100) { distanceCutoff = pixel.distance; break; } }
        }
      }
      const support = [], local = (x, y) => [clamp((x / width - u0) / (u1 - u0), 0, 1), clamp((y / height - v0) / (v1 - v0), 0, 1)];
      for (let y = top; y < bottom; y++) {
        let rowMin = right, rowMax = left - 1;
        for (let x = left; x < right; x++) if (alpha[y * width + x] > 0
          && Math.hypot(x + .5 - alphaCenter[0], y + .5 - alphaCenter[1]) <= distanceCutoff + 1e-9) {
          rowMin = Math.min(rowMin, x); rowMax = Math.max(rowMax, x);
          minX = Math.min(minX, x); maxX = Math.max(maxX, x);
          minY = Math.min(minY, y); maxY = Math.max(maxY, y);
        }
        if (rowMax >= rowMin) for (const x of [rowMin - 1, rowMax + 2]) for (const v of [y - 1, y + 2]) support.push(local(x, v));
      }
      // Un texel de marge garde le bord filtré, sans étendre le contenu aux autres cases.
      const bounds = maxX < minX ? null : {
        min: [clamp(((minX - 1) / width - u0) / (u1 - u0), 0, 1), clamp(((minY - 1) / height - v0) / (v1 - v0), 0, 1)],
        max: [clamp(((maxX + 2) / width - u0) / (u1 - u0), 0, 1), clamp(((maxY + 2) / height - v0) / (v1 - v0), 0, 1)],
      };
      cache.set(key, bounds); pointCache.set(key, hull(support)); return bounds;
    };
    const bounds = (uri, uv, uv2 = uv, blend = 0) => {
      const first = blend < 1 ? rect(uri, uv) : null, second = blend > 0 ? rect(uri, uv2) : null;
      if (!first) return second;
      if (!second) return first;
      return {min: first.min.map((v, i) => Math.min(v, second.min[i])), max: first.max.map((v, i) => Math.max(v, second.max[i]))};
    };
    // Le contour évite d'inventer les coins vides de la boîte d'un motif diagonal,
    // surtout après la rotation du quad, sans seuil de luminosité absolue qui
    // ferait disparaître les textures pâles.
    bounds.points = (uri, uv, uv2 = uv, blend = 0) => {
      if (!textures.has(String(uri))) return fullPoints();
      const points = [];
      for (const active of [blend < 1 ? uv : null, blend > 0 ? uv2 : null]) if (active) {
        rect(uri, active); const support = pointCache.get(JSON.stringify([uri, active]));
        if (support) points.push(...support);
      }
      return hull(points);
    };
    return bounds;
  }

  // Planche de textures du catalogue : chaque case montre l’image, son ID et la grille du flipbook.
  async function renderTextureSheet(items, options = {}) {
    const cell = options.cell || 176, label = 34, columns = Math.max(1, Math.min(options.columns || 6, items.length || 1));
    const rows = Math.max(1, Math.ceil(items.length / columns));
    const sheet = document.createElement('canvas');
    sheet.width = columns * cell; sheet.height = rows * (cell + label);
    const ctx = sheet.getContext('2d');
    ctx.fillStyle = '#0d0b12'; ctx.fillRect(0, 0, sheet.width, sheet.height);
    const load = url => new Promise(resolve => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => resolve(null); image.src = url; });
    const images = await Promise.all(items.map(item => item.url ? load(item.url) : null));
    for (const [i, item] of items.entries()) {
      const x = (i % columns) * cell, y = Math.floor(i / columns) * (cell + label);
      ctx.fillStyle = '#1d1826'; ctx.fillRect(x + 3, y + 3, cell - 6, cell - 6);
      const image = images[i], pad = 8;
      if (image) ctx.drawImage(image, x + pad, y + pad, cell - pad * 2, cell - pad * 2);
      else { ctx.fillStyle = '#6b5b77'; ctx.font = '12px sans-serif'; ctx.fillText('aperçu absent', x + 14, y + cell / 2); }
      if (item.grid > 1) {
        ctx.strokeStyle = '#8ce9e255'; ctx.lineWidth = 1;
        for (let g = 1; g < item.grid; g++) {
          const o = pad + (cell - pad * 2) * g / item.grid;
          ctx.beginPath(); ctx.moveTo(x + o, y + pad); ctx.lineTo(x + o, y + cell - pad); ctx.moveTo(x + pad, y + o); ctx.lineTo(x + cell - pad, y + o); ctx.stroke();
        }
      }
      if (item.used) {
        ctx.fillStyle = '#5c2439'; ctx.fillRect(x + cell - 55, y + 7, 48, 20);
        ctx.fillStyle = '#ffd6de'; ctx.font = 'bold 12px monospace';
        ctx.fillText('USED', x + cell - 49, y + 21);
      }
      ctx.fillStyle = '#e8e0f0'; ctx.font = 'bold 12px monospace';
      ctx.fillText(String(item.id), x + 6, y + cell + 13);
      ctx.fillStyle = '#a99bb8'; ctx.font = '11px sans-serif';
      ctx.fillText(String(item.label || '').slice(0, 26), x + 6, y + cell + 28);
    }
    return {image: sheet.toDataURL('image/png'), count: items.length};
  }

  const api = Object.freeze({STEP, createSimulation, buildFrame, effectBounds, sampledParticleBounds, autoCamera, particleCamera, sphereCamera, dummyParts, createRenderer, createView,
    renderSheet, renderComparison, renderTimes, renderTextureSheet, textureAlphaBounds, environmentColors, fromOrientation, sampleNumber, sampleColor});
  if (typeof module === 'object' && module.exports) module.exports = api;
  global.DatakyEmulator = api;
})(typeof window !== 'undefined' ? window : globalThis);
