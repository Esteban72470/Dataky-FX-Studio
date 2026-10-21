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
  --fov 50                 champ de vision vertical
  --background sombre|gris|ciel|noir
  --no-ground              sans sol ni grille
  --seed 1                 graine de l’aléatoire (même graine = mêmes images)
  --frames-dir DOSSIER     enregistre aussi chaque image séparément`;

function parse(argv) {
  const options = {frames: 8, columns: 4, size: '480x270', seed: 1, ground: true, autoCamera: false, dummy: false};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') { console.log(USAGE); process.exit(0); }
    if (arg === '--no-ground') { options.ground = false; continue; }
    if (arg === '--auto-camera') { options.autoCamera = true; continue; }
    if (arg === '--dummy') { options.dummy = true; continue; }
    if (!arg.startsWith('--')) { positional.push(arg); continue; }
    const key = arg.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (i + 1 >= argv.length) throw new Error(`${arg} attend une valeur`);
    options[key] = argv[++i];
  }
  if (!positional.length && !options.textures) throw new Error(USAGE);
  return {sources: positional, options};
}

function loadProject(source) {
  const candidates = [path.resolve(source), path.join(ROOT, 'editor', 'projects', source + '.json')];
  const file = candidates.find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  if (!file) throw new Error(`Projet introuvable : ${source}`);
  return {file, project: JSON.parse(fs.readFileSync(file, 'utf8'))};
}

function loadPlaywright() {
  for (const name of ['playwright', 'playwright-core']) {
    try { return require(name); } catch (_) {}
  }
  try {
    const globalRoot = execSync('npm root -g', {encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']}).trim();
    return require(path.join(globalRoot, 'playwright'));
  } catch (_) {}
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

const numbers = text => String(text).split(',').map(Number);

async function main() {
  const {sources, options} = parse(process.argv.slice(2));
  const projects = sources.map(source => loadProject(source).project);
  const project = projects[0] || {};
  const [width, height] = numbers(options.size.replace('x', ','));
  if (!(width > 0 && height > 0 && width <= 1920 && height <= 1080)) throw new Error('--size attend LARGEURxHAUTEUR (1920x1080 maximum)');
  const settings = {
    frames: Number(options.frames), columns: Number(options.columns), width, height, seed: Number(options.seed),
    background: options.background, ground: options.ground, individual: !!options.framesDir,
    autoCamera: options.autoCamera, dummy: options.dummy,
  };
  if (options.times) settings.times = numbers(options.times);
  if (settings.times && settings.times.some(t => !Number.isFinite(t) || t < 0)) throw new Error('--times attend des secondes positives séparées par des virgules');
  if (options.camera) {
    const values = numbers(options.camera);
    if (values.length !== 6 || values.some(v => !Number.isFinite(v))) throw new Error('--camera attend px,py,pz,tx,ty,tz');
    settings.camera = {position: values.slice(0, 3), target: values.slice(3), fov: Number(options.fov) || project.camera?.fov || 50};
  } else if (options.fov) settings.camera = {...project.camera, fov: Number(options.fov)};

  const {chromium} = loadPlaywright();
  const browser = await chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
  try {
    const page = await browser.newPage();
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
    let result;
    if (options.textures) {
      const items = JSON.parse(fs.readFileSync(options.textures, 'utf8')).map(item => ({...item, url: item.path ? '/library/' + item.path : null}));
      result = await page.evaluate(([list, config]) => window.DatakyEmulator.renderTextureSheet(list, config), [items, {columns: Number(options.columns) || 6}]);
    } else {
      result = await page.evaluate(([values, config]) => values.length > 1 ? window.DatakyEmulator.renderComparison(values, config)
        : window.DatakyEmulator.renderSheet(values[0], config), [projects, settings]);
    }
    if (errors.length) throw new Error(errors.join('\n'));
    const out = path.resolve(options.out || (options.textures ? 'textures.png' : `rendu-${project.id || 'effet'}.png`));
    fs.writeFileSync(out, Buffer.from(result.image.split(',')[1], 'base64'));
    const written = [out];
    if (options.framesDir) {
      fs.mkdirSync(options.framesDir, {recursive: true});
      for (const frame of result.frames || []) {
        const prefix = projects.length > 1 ? String.fromCharCode(65 + frame.row % 26) + '_' : '';
        const file = path.resolve(options.framesDir, `${prefix}t${frame.time.toFixed(2).replace('.', '_')}.png`);
        fs.writeFileSync(file, Buffer.from(frame.image.split(',')[1], 'base64'));
        written.push(file);
      }
    }
    console.log(JSON.stringify({files: written, times: result.times, camera: result.camera, warnings: result.warnings || []}, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exit(1); });
