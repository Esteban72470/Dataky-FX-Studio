#!/usr/bin/env node
'use strict';

// Dataky FX Studio · rendu sans fenêtre d’une recette, pour une IA ou un script.
// Produit une planche PNG à des instants précis avec l’émulateur du navigateur
// (Chromium via Playwright). Aucun serveur ni Roblox Studio n’est nécessaire.
//
//   node tool/fx_render.cjs editor/projects/dataky-impact.json --out rendu.png
//   node tool/fx_render.cjs dataky-impact --times 0,0.1,0.25,0.5 --size 640x360 --auto-camera --dummy
//   node tool/fx_render.cjs variante-a.json variante-b.json --times 0.1,0.3   (une ligne par variante)
//   node tool/fx_render.cjs --textures items.json --out textures.png         (planche de textures)
const fs = require('node:fs');
const path = require('node:path');
const {execSync} = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const ORIGIN = 'http://dataky.local';
const USAGE = `Utilisation : node tool/fx_render.cjs <projet.json | ID> [autres projets…] [options]
  Plusieurs projets : une ligne par projet, même caméra et mêmes instants (comparaison).
  --out FICHIER.png        planche produite (défaut : rendu-<id>.png)
  --auto-camera            cadre toute l’étendue de l’effet (direction de la caméra du projet)
  --dummy                  ajoute un mannequin Roblox de 5 studs comme repère d’échelle
  --textures ITEMS.json    planche de textures : [{"id","label","path","grid"}], path relatif à la racine
  --times 0,0.2,0.5        instants en secondes (défaut : --frames instants répartis)
  --frames 8               nombre d’instants si --times est absent
  --columns 4              colonnes de la planche
  --size 480x270           taille de chaque image
  --camera px,py,pz,tx,ty,tz   caméra (défaut : caméra du projet)
  --fit NODE_ID            particules vivantes de cet objet et de ses descendants aux instants rendus
  --fit-percentile 90      centile des distances au centroïde à garder (0 < valeur <= 100)
  --fit-all                ancien cadrage sur toute la durée et toute l'étendue de l'objet
  --focus x,y,z --radius r cadre une sphère de rayon r, dans la direction de la caméra
  --batch JOBS.json        {"jobs":[{"projects":[recette ou chemin/ID],"out":"...png",...options}]}
                           tous les jobs utilisent un seul lancement de Chromium
  --fov 50                 champ de vision vertical
  --background sombre|gris|ciel|noir|roblox|dark|#RRGGBB
                           défaut : environment.background de chaque recette
  --backgrounds roblox,dark une ligne par recette et par fond, même caméra
  --no-ground              sans sol ni grille
  --seed 1                 graine de l’aléatoire (même graine = mêmes images)
  --frames-dir DOSSIER     enregistre aussi chaque image séparément`;

const DEFAULTS = {frames: 8, columns: 4, size: '480x270', seed: 1, ground: true, autoCamera: false, dummy: false};

function parse(argv) {
  const options = {...DEFAULTS};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') { console.log(USAGE); process.exit(0); }
    if (arg === '--no-ground') { options.ground = false; continue; }
    if (arg === '--auto-camera') { options.autoCamera = true; continue; }
    if (arg === '--dummy') { options.dummy = true; continue; }
    if (arg === '--fit-all') { options.fitAll = true; continue; }
    if (!arg.startsWith('--')) { positional.push(arg); continue; }
    const key = arg.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (i + 1 >= argv.length) throw new Error(`${arg} attend une valeur`);
    options[key] = argv[++i];
  }
  if (!positional.length && !options.textures && !options.batch) throw new Error(USAGE);
  if (options.batch && (positional.length || options.textures)) throw new Error('--batch ne se combine pas avec des projets ou --textures');
  return {sources: positional, options};
}

function loadProject(source) {
  const candidates = [path.resolve(source), path.join(ROOT, 'editor', 'projects', source + '.json')];
  const file = candidates.find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  if (!file) throw new Error(`Projet introuvable : ${source}`);
  return {file, project: JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''))};
}

function loadPlaywright() {
  for (const name of ['playwright', 'playwright-core']) {
    try { return require(name); } catch (_) {}
  }
  const candidates = [];
  try {
    const globalRoot = execSync('npm root -g', {encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']}).trim();
    candidates.push(path.join(globalRoot, 'playwright'));
  } catch (_) {}
  if (process.env.APPDATA) candidates.push(path.join(process.env.APPDATA, 'npm', 'node_modules', 'playwright'));
  for (const candidate of new Set(candidates)) {
    try { return require(candidate); } catch (_) {}
    try { fs.readFileSync(path.join(candidate, 'package.json')); }
    catch (error) {
      if (['EPERM', 'EACCES'].includes(error.code)) throw new Error(`Playwright est installé mais inaccessible dans le bac à sable (accès refusé : ${candidate}). Relancez les tests Chromium hors du bac à sable.`);
    }
  }
  throw new Error('Playwright est introuvable. Installez-le avec : npm install -g playwright && npx playwright install chromium');
}

// Seuls l’émulateur, la page de rendu et les miniatures de la bibliothèque sont servis.
function routeFile(url) {
  const pathname = decodeURIComponent(new URL(url).pathname);
  if (pathname === '/render.html') return path.join(ROOT, 'editor', 'render.html');
  if (pathname === '/emulator.js') return path.join(ROOT, 'editor', 'emulator.js');
  const match = pathname.match(/^\/library\/((?:beams\/|meshes\/)?(?:images|previews)\/[\w-]+\.png)$/);
  return match ? path.join(ROOT, match[1]) : null;
}

const numbers = text => (Array.isArray(text) ? text : String(text).split(',')).map(Number);

function settingsFor(options, project = {}) {
  const dimensions = numbers(String(options.size).replace('x', ','));
  const [width, height] = dimensions;
  if (!(dimensions.length === 2 && Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0 && width <= 1920 && height <= 1080)) throw new Error('--size attend LARGEURxHAUTEUR (1920x1080 maximum)');
  const settings = {
    frames: Number(options.frames), columns: Number(options.columns), width, height, seed: Number(options.seed),
    background: options.background, ground: options.ground, individual: !!options.framesDir,
    autoCamera: options.autoCamera, dummy: options.dummy,
  };
  if (options.backgrounds !== undefined) {
    if (options.background !== undefined && options.background !== null) throw new Error('--background et --backgrounds sont exclusifs');
    const values = Array.isArray(options.backgrounds) ? options.backgrounds : typeof options.backgrounds === 'string' ? options.backgrounds.split(',') : [];
    if (!values.length || values.length > 8 || values.some(value => typeof value !== 'string' || !/^(sombre|gris|ciel|noir|roblox|dark|#[\da-f]{6})$/i.test(value.trim()))) throw new Error('--backgrounds attend 1 à 8 presets ou couleurs #RRGGBB');
    settings.backgrounds = values.map(value => value.trim().toLowerCase());
  }
  if (!Number.isInteger(settings.frames) || settings.frames < 1) throw new Error('--frames attend un entier positif');
  if (!Number.isInteger(settings.columns) || settings.columns < 1) throw new Error('--columns attend un entier positif');
  if (!Number.isFinite(settings.seed)) throw new Error('--seed attend un nombre fini');
  if (options.times !== undefined) settings.times = numbers(options.times);
  if (settings.times && (!settings.times.length || settings.times.some(t => !Number.isFinite(t) || t < 0))) throw new Error('--times attend des secondes positives séparées par des virgules');
  if (options.camera) {
    const values = numbers(options.camera);
    if (values.length !== 6 || values.some(v => !Number.isFinite(v))) throw new Error('--camera attend px,py,pz,tx,ty,tz');
    settings.camera = {position: values.slice(0, 3), target: values.slice(3), fov: options.fov !== undefined ? Number(options.fov) : project.camera?.fov || 50};
    // An explicit camera is exact. fit/focus may still use its direction below.
    settings.autoCamera = false;
  } else if (options.fov !== undefined) settings.camera = {...project.camera, fov: Number(options.fov)};
  if (settings.camera && (!(settings.camera.fov >= 1 && settings.camera.fov <= 120))) throw new Error('--fov attend un angle entre 1 et 120');
  if (options.fit !== undefined) {
    if (typeof options.fit !== 'string' || !options.fit.trim()) throw new Error('--fit attend un identifiant de node');
    settings.fit = options.fit;
  }
  settings.fitPercentile = options.fitPercentile === undefined ? 90 : Number(options.fitPercentile);
  if (!(Number.isFinite(settings.fitPercentile) && settings.fitPercentile > 0 && settings.fitPercentile <= 100)) throw new Error('--fit-percentile attend un nombre dans ]0,100]');
  settings.fitAll = !!options.fitAll;
  if (options.focus !== undefined) {
    settings.focus = numbers(options.focus);
    if (settings.focus.length !== 3 || settings.focus.some(v => !Number.isFinite(v))) throw new Error('--focus attend x,y,z');
    settings.radius = Number(options.radius);
    if (!(settings.radius > 0 && Number.isFinite(settings.radius))) throw new Error('--focus exige --radius positif');
  } else if (options.radius !== undefined) throw new Error('--radius exige --focus');
  if (settings.fit && settings.focus) throw new Error('--fit et --focus sont exclusifs');
  return settings;
}

function prepareJob(value, index = 0, defaults = DEFAULTS) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`Job ${index + 1} : objet attendu`);
  const options = {...defaults, ...value};
  const sources = value.projects || [];
  if (!Array.isArray(sources) || (!sources.length && !options.textures)) throw new Error(`Job ${index + 1} : projects doit contenir au moins une recette`);
  const projects = sources.map(source => typeof source === 'string' ? loadProject(source).project : source);
  if (projects.some(p => !p || typeof p !== 'object' || !Array.isArray(p.nodes))) throw new Error(`Job ${index + 1} : recette JSON attendue`);
  const project = projects[0] || {};
  const settings = settingsFor(options, project);
  if (settings.fit) for (const recipe of projects) {
    if (!recipe.nodes.some(node => node.id === settings.fit)) throw new Error(`--fit : objet introuvable ${settings.fit} dans ${recipe.name || 'la recette'}`);
  }
  const out = path.resolve(options.out || (options.textures ? 'textures.png' : `rendu-${project.id || 'effet'}${index ? '-' + (index + 1) : ''}.png`));
  return {projects, options, settings, out};
}

function readJobs(sources, options) {
  let jobs;
  if (options.batch) {
    const manifest = JSON.parse(fs.readFileSync(options.batch, 'utf8').replace(/^\uFEFF/, ''));
    const values = Array.isArray(manifest) ? manifest : manifest.jobs;
    if (!Array.isArray(values) || !values.length) throw new Error('--batch attend {"jobs":[...]} avec au moins un job');
    jobs = values.map((value, i) => prepareJob(value, i, options));
  } else jobs = [prepareJob({...options, projects: sources})];
  const outputs = new Set();
  for (const job of jobs) {
    if (outputs.has(job.out)) throw new Error(`Plusieurs jobs écrivent le même fichier : ${job.out}`);
    outputs.add(job.out);
  }
  return jobs;
}

// Kept self-contained so Playwright can serialize it into the render page.
async function renderInPage({projects, settings, textureItems}) {
  const emulator = window.DatakyEmulator;
  if (textureItems) return emulator.renderTextureSheet(textureItems, {columns: settings.columns || 6});
  const config = {...settings};
  const framingWarnings = [];
  const fitSamples = [];
  const fitPoints = [];
  const fallbackPoints = [];
  const textureBounds = settings.fit && !settings.fitAll
    ? await emulator.textureAlphaBounds(projects, {...settings, alphaPercentile: settings.fitPercentile, alphaPower: 2}) : null;
  const referenceCamera = settings.camera || projects[0]?.camera;
  let requestedBounds = null;
  const times = settings.fit ? emulator.renderTimes(projects, settings) : null;
  const sampleFit = camera => {
    requestedBounds = null;
    fitSamples.length = fitPoints.length = fallbackPoints.length = framingWarnings.length = 0;
    for (const project of projects) {
      const bound = settings.fitAll
        ? emulator.effectBounds(project, {ids: [settings.fit], seed: settings.seed})
        : emulator.sampledParticleBounds(project, {ids: [settings.fit], seed: settings.seed, times, percentile: settings.fitPercentile,
            camera, textureBounds});
      if (!bound) throw new Error(`--fit : objet sans étendue ${settings.fit}`);
      if (!settings.fitAll) {
        if (bound.fitPoints) for (const point of bound.fitPoints) fitPoints.push(point);
        // Comparison rows share one camera, including rows that have no live
        // particles and therefore fall back to their Part/Attachments.
        else if (bound.fallback) for (let k = 0; k < 8; k++) {
          fallbackPoints.push([0, 1, 2].map(i => (k >> i) & 1 ? bound.max[i] : bound.min[i]));
        }
        fitSamples.push({project: project.name, particles: bound.particles, retained: bound.retained, fallback: bound.fallback});
        if (bound.fallback) framingWarnings.push(`--fit ${settings.fit} (${project.name || 'recette'}) : aucune particule vivante aux instants rendus ; repli sur la Part et ses Attachments.`);
      }
      if (!requestedBounds) requestedBounds = bound;
      else {
        const min = bound.min.map((v, i) => Math.min(v, requestedBounds.min[i]));
        const max = bound.max.map((v, i) => Math.max(v, requestedBounds.max[i]));
        requestedBounds = {min, max, center: min.map((v, i) => (v + max[i]) / 2)};
      }
    }
    if (fitPoints.length) for (const point of fallbackPoints) fitPoints.push(point);
  };
  if (settings.fit) sampleFit(referenceCamera);
  else if (settings.focus) {
    requestedBounds = {center: settings.focus, min: settings.focus.map(v => v - settings.radius), max: settings.focus.map(v => v + settings.radius), radius: settings.radius};
  }
  if (requestedBounds) {
    const fittedCamera = () => {
      const cameraOptions = {bounds: requestedBounds, camera: referenceCamera, aspect: settings.width / settings.height};
      return settings.focus
        ? emulator.sphereCamera(projects[0], {...cameraOptions, center: settings.focus, radius: settings.radius})
        : fitPoints.length ? emulator.particleCamera(projects[0], {...cameraOptions, points: fitPoints})
        : emulator.autoCamera(projects[0], cameraOptions);
    };
    config.camera = fittedCamera();
    // World-up and velocity-parallel billboards face the camera's position,
    // not just its viewing direction. Rebuild their footprints after moving
    // the camera, otherwise a recentered quad can be wider than its fit.
    if (settings.fit && !settings.fitAll && fitPoints.length) for (let iteration = 0; iteration < 8; iteration++) {
      const previous = config.camera;
      sampleFit(previous);
      config.camera = fittedCamera();
      const difference = Math.max(...['position', 'target'].flatMap(key => config.camera[key].map((v, i) => Math.abs(v - previous[key][i]))));
      const distance = Math.hypot(...config.camera.position.map((v, i) => v - config.camera.target[i]));
      if (difference <= Math.max(1, distance) * 1e-6) break;
    }
    config.autoCamera = false;
  }
  const result = await (projects.length > 1 ? emulator.renderComparison(projects, config) : emulator.renderSheet(projects[0], config));
  if (requestedBounds) {
    const {fitPoints: _points, ...bounds} = requestedBounds;
    result.framing = {fit: settings.fit, fitAll: settings.fitAll, fitPercentile: settings.fitPercentile, focus: settings.focus, radius: settings.radius, bounds, samples: fitSamples};
  }
  result.warnings = [...framingWarnings, ...(result.warnings || [])];
  return result;
}

function writeResult(result, job, batch) {
  const png = value => {
    if (typeof value !== 'string' || !value.startsWith('data:image/png;base64,')) throw new Error('Le rendu ne contient pas une image PNG');
    return Buffer.from(value.split(',')[1], 'base64');
  };
  fs.mkdirSync(path.dirname(job.out), {recursive: true});
  fs.writeFileSync(job.out, png(result.image));
  const written = [job.out];
  if (job.options.framesDir) {
    fs.mkdirSync(job.options.framesDir, {recursive: true});
    for (const frame of result.frames || []) {
      const jobPrefix = batch ? path.basename(job.out, path.extname(job.out)) + '_' : '';
      const rowPrefix = job.projects.length > 1 || job.settings.backgrounds ? String.fromCharCode(65 + frame.row % 26) + '_' : '';
      const file = path.resolve(job.options.framesDir, `${jobPrefix}${rowPrefix}t${frame.time.toFixed(2).replace('.', '_')}.png`);
      fs.writeFileSync(file, png(frame.image));
      written.push(file);
    }
  }
  return {files: written, times: result.times, camera: result.camera, framing: result.framing, rows: result.rows, sheet: result.sheet, warnings: result.warnings || []};
}

async function runJobs(jobs, chromium = loadPlaywright().chromium) {
  const browser = await chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
  const results = [];
  try {
    for (const job of jobs) {
      // Closing each page frees its WebGL contexts while keeping Chromium warm.
      const page = await browser.newPage();
      try {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
          const file = routeFile(route.request().url());
          if (!file || !fs.existsSync(file)) return route.fulfill({status: 404, body: ''});
          const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'image/png';
          return route.fulfill({status: 200, contentType: type, body: fs.readFileSync(file)});
        });
        await page.goto(ORIGIN + '/render.html');
        await page.waitForFunction(() => window.DatakyEmulator);
        const textureItems = job.options.textures ? JSON.parse(fs.readFileSync(job.options.textures, 'utf8')).map(item => ({...item, url: item.path ? '/library/' + item.path : null})) : null;
        const result = await page.evaluate(renderInPage, {projects: job.projects, settings: job.settings, textureItems});
        if (errors.length) throw new Error(errors.join('\n'));
        results.push(writeResult(result, job, jobs.length > 1));
      } finally {
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  return results;
}

async function main(argv = process.argv.slice(2)) {
  const {sources, options} = parse(argv);
  const results = await runJobs(readJobs(sources, options));
  console.log(JSON.stringify(options.batch ? {jobs: results, files: results.flatMap(r => r.files), browser_launches: 1} : results[0], null, 2));
}

module.exports = {parse, loadProject, loadPlaywright, routeFile, settingsFor, prepareJob, readJobs, renderInPage, runJobs};
if (require.main === module) main().catch(error => { console.error(error.message); process.exit(1); });
