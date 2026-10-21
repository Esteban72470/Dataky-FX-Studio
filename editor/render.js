/* Dataky FX Studio · planche de rendu d’un projet enregistré : /render.html?project=ID&frames=8 */
(async () => {
  'use strict';
  const params = new URLSearchParams(location.search);
  const id = params.get('project');
  const status = document.getElementById('render-status');
  const image = document.getElementById('render-image');
  if (!id || !window.DatakyEmulator) return;
  try {
    const response = await fetch('/api/project/' + encodeURIComponent(id), {cache: 'no-store'});
    const project = await response.json();
    if (!response.ok) throw new Error(project.error || response.statusText);
    const times = params.get('times') ? params.get('times').split(',').map(Number).filter(Number.isFinite) : undefined;
    const [width, height] = (params.get('size') || '480x270').split('x').map(Number);
    const result = await window.DatakyEmulator.renderSheet(project, {
      times, frames: Number(params.get('frames')) || 8, columns: Number(params.get('columns')) || 4, width, height,
      background: params.get('background') || undefined, ground: params.get('ground') !== '0', seed: Number(params.get('seed')) || 1,
    });
    image.src = result.image;
    image.hidden = false;
    status.textContent = `${project.name} · ${result.times.length} instants · émulation navigateur` + (result.warnings.length ? ' · ' + result.warnings.join(' ') : '');
  } catch (error) {
    status.textContent = 'Rendu impossible : ' + error.message;
  }
})();
