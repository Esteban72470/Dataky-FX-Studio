/* Dataky FX Studio · curve authoring. No dependencies or runtime code evaluation. */
(function (global) {
  'use strict';
  const EPSILON = 1e-8;
  const MAX_POINTS = 20;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const copy = value => JSON.parse(JSON.stringify(value));
  const finite = (value, label = 'Valeur') => {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(label + ' doit être un nombre fini.');
    return value;
  };
  const round = value => Math.round(value * 1e8) / 1e8;
  const boundsOf = definition => ({
    min: typeof definition?.min === 'number' && Number.isFinite(definition.min) ? definition.min : -Infinity,
    max: typeof definition?.max === 'number' && Number.isFinite(definition.max) ? definition.max : Infinity
  });
  function assertBounds(value, definition, label = 'Valeur') {
    finite(value, label); const {min, max} = boundsOf(definition);
    if (min > max) throw new Error('Les limites min / max sont inversées.');
    if (value < min || value > max) throw new Error(`${label} doit être compris entre ${min} et ${max}.`);
    return value;
  }
  function inputPoint(point, index) {
    if (Array.isArray(point)) return {time: point[0], value: point[1], envelope: point[2] ?? 0};
    if (!point || typeof point !== 'object') throw new Error(`Point ${index + 1} invalide.`);
    return {time: point.time, value: point.value, envelope: point.envelope ?? 0, in: point.in, out: point.out};
  }
  function normalizeNumber(value, options = {}) {
    if (!Array.isArray(value) || value.length < 2 || value.length > MAX_POINTS) throw new Error('Une courbe doit contenir de 2 à 20 points.');
    const duration = options.duration ?? 1; finite(duration, 'Durée');
    if (duration <= 0) throw new Error('La durée doit être positive.');
    const points = value.map((entry, i) => {
      const p = inputPoint(entry, i); const t = finite(p.time, 'Temps') / duration;
      if (t < 0 || t > 1) throw new Error('Les temps doivent rester dans la durée de la courbe.');
      const envelope = finite(p.envelope, 'Enveloppe'); if (envelope < 0) throw new Error('L’enveloppe doit être positive.');
      const result = {time: t, value: assertBounds(p.value, options.definition), envelope};
      if (p.in) result.in = {x: finite(p.in.x, 'Poignée X'), y: finite(p.in.y, 'Poignée Y')};
      if (p.out) result.out = {x: finite(p.out.x, 'Poignée X'), y: finite(p.out.y, 'Poignée Y')};
      return result;
    }).sort((a, b) => a.time - b.time);
    for (let i = 1; i < points.length; i++) if (points[i].time - points[i - 1].time < EPSILON) throw new Error('Chaque point doit avoir un temps distinct.');
    if (options.extendEndpoints) {
      if (points[0].time > EPSILON) points.unshift({time: 0, value: points[0].value, envelope: points[0].envelope});
      if (points.at(-1).time < 1 - EPSILON) points.push({time: 1, value: points.at(-1).value, envelope: points.at(-1).envelope});
      if (points.length > MAX_POINTS) throw new Error('L’ajout des bornes de durée dépasserait 20 points.');
    }
    if (Math.abs(points[0].time) > EPSILON || Math.abs(points.at(-1).time - 1) > EPSILON) throw new Error('Les bornes de la courbe doivent être à 0 et à sa durée finale.');
    points[0].time = 0; points.at(-1).time = 1;
    return makeLinear(points);
  }
  function normalizeColor(value, options = {}) {
    if (!Array.isArray(value) || value.length < 2 || value.length > MAX_POINTS) throw new Error('Un dégradé doit contenir de 2 à 20 couleurs.');
    const points = value.map((entry, i) => {
      const p = inputPoint(entry, i); finite(p.time, 'Temps');
      if (p.time < 0 || p.time > 1) throw new Error('Les temps du dégradé doivent rester entre 0 et 1.');
      if (!Array.isArray(p.value) || p.value.length !== 3) throw new Error('Chaque couleur contient trois composantes RVB.');
      p.value.forEach(v => assertBounds(v, {min: 0, max: 1}, 'Composante RVB'));
      return {time: p.time, value: [...p.value]};
    }).sort((a, b) => a.time - b.time);
    if (points[0].time !== 0 || points.at(-1).time !== 1) throw new Error('Le dégradé commence à 0 et se termine à 1.');
    for (let i = 1; i < points.length; i++) if (points[i].time - points[i - 1].time < EPSILON) throw new Error('Chaque couleur doit avoir un temps distinct.');
    return points;
  }
  function makeLinear(input) {
    const points = copy(input);
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      if (i && !p.in) { const previous = points[i - 1]; p.in = {x: -(p.time - previous.time) / 3, y: -(p.value - previous.value) / 3}; }
      if (i < points.length - 1 && !p.out) { const next = points[i + 1]; p.out = {x: (next.time - p.time) / 3, y: (next.value - p.value) / 3}; }
      p.envelope = p.envelope ?? 0;
    }
    return points;
  }
  function bezier(a, b, c, d, t) { const u = 1 - t; return u*u*u*a + 3*u*u*t*b + 3*u*t*t*c + t*t*t*d; }
  function segmentControls(a, b, definition) {
    const dt = b.time - a.time; const dv = b.value - a.value;
    const out = a.out || {x: dt / 3, y: dv / 3}; const incoming = b.in || {x: -dt / 3, y: -dv / 3};
    let x1 = clamp(a.time + out.x, a.time, b.time); let x2 = clamp(b.time + incoming.x, a.time, b.time);
    if (x1 > x2) { const midpoint = (x1 + x2) / 2; x1 = midpoint; x2 = midpoint; }
    const {min, max} = boundsOf(definition);
    return {x0:a.time,x1,x2,x3:b.time,y0:a.value,y1:clamp(a.value+out.y,min,max),y2:clamp(b.value+incoming.y,min,max),y3:b.value};
  }
  function parameterAtTime(controls, time) {
    if (time <= controls.x0) return 0; if (time >= controls.x3) return 1;
    let lo = 0, hi = 1;
    for (let i = 0; i < 38; i++) {const middle = (lo + hi) / 2; if (bezier(controls.x0,controls.x1,controls.x2,controls.x3,middle) < time) lo = middle; else hi = middle;}
    return (lo + hi) / 2;
  }
  function evaluate(points, time, definition) {
    if (!points.length) throw new Error('Courbe vide.'); finite(time, 'Temps');
    if (time <= points[0].time) return points[0].value; if (time >= points.at(-1).time) return points.at(-1).value;
    let i = 1; while (points[i].time < time) i++;
    const controls = segmentControls(points[i - 1], points[i], definition); const t = parameterAtTime(controls, time);const {min,max}=boundsOf(definition);
    return clamp(bezier(controls.y0,controls.y1,controls.y2,controls.y3,t),min,max);
  }
  function linearAt(points, time, key = 'value') {
    if (time <= points[0].time) return points[0][key] || 0; if (time >= points.at(-1).time) return points.at(-1)[key] || 0;
    let i=1;while(points[i].time<time)i++;const a=points[i-1],b=points[i],t=(time-a.time)/(b.time-a.time);
    return (a[key] || 0) + ((b[key] || 0)-(a[key] || 0))*t;
  }
  function sampleTimes(curves, options = {}) {
    const maxPoints = clamp(Math.floor(options.maxPoints ?? MAX_POINTS),2,MAX_POINTS);const tolerance = options.tolerance ?? 0.002;
    finite(tolerance,'Précision');if(tolerance<0)throw new Error('La précision doit être positive.');
    const times = [...new Set(curves.flatMap(points=>points.map(p=>p.time)))].sort((a,b)=>a-b);
    if (times.length > maxPoints) throw new Error('La courbe dépasse la limite de points exportables.');
    const ranges=curves.map(points=>Math.max(1,...points.map(p=>p.value))-Math.min(0,...points.map(p=>p.value)));
    while(times.length<maxPoints){let bestError=tolerance,bestTime=null;
      for(let i=1;i<times.length;i++){const a=times[i-1],b=times[i];if(b-a<EPSILON*4)continue;
        for(const fraction of [0.25,0.5,0.75]){const t=a+(b-a)*fraction;let error=0;
          for(let c=0;c<curves.length;c++){const points=curves[c];const ya=evaluate(points,a,options.definition),yb=evaluate(points,b,options.definition);const value=evaluate(points,t,options.definition);error=Math.max(error,Math.abs(value-(ya+(yb-ya)*fraction))/ranges[c]);}
          if(error>bestError){bestError=error;bestTime=t;}
        }
      }
      if(bestTime===null)break;times.push(bestTime);times.sort((a,b)=>a-b);
    }
    return times;
  }
  function bake(points, options = {}) {
    const checked = normalizeNumber(points,{definition:options.definition});const times=sampleTimes([checked],options);
    return times.map(time=>({time:round(time),value:round(evaluate(checked,time,options.definition)),envelope:round(Math.max(0,linearAt(checked,time,'envelope')))}));
  }
  function bakeAnimation(curves, options = {}) {
    const duration=options.duration??1;finite(duration,'Durée');if(duration<=0)throw new Error('La durée doit être positive.');
    const checked=curves.map(points=>normalizeNumber(points,{definition:options.definition}));const times=sampleTimes(checked,options);
    return times.map(time=>({time:round(time*duration),value:curves.length===1&&!options.vector?round(evaluate(checked[0],time,options.definition)):checked.map(points=>round(evaluate(points,time,options.definition)))}));
  }
  const PRESETS = {
    Linear:[0,0,1,1],EaseIn:[0.42,0,1,1],EaseOut:[0,0,0.58,1],EaseInOut:[0.42,0,0.58,1]
  };
  function applyPreset(input, name) {
    if(name==='Burst')return makeLinear([{time:0,value:0,envelope:0},{time:0.12,value:1,envelope:0},{time:0.32,value:0.72,envelope:0},{time:1,value:0,envelope:0}]);
    if(name==='Fade')return makeLinear([{time:0,value:1,envelope:0},{time:0.25,value:1,envelope:0},{time:1,value:0,envelope:0}]);
    const preset=PRESETS[name];if(!preset)throw new Error('Préréglage inconnu : '+name);const points=copy(input);
    for(let i=0;i<points.length-1;i++){const a=points[i],b=points[i+1],dt=b.time-a.time,dv=b.value-a.value;a.out={x:preset[0]*dt,y:preset[1]*dv};b.in={x:(preset[2]-1)*dt,y:(preset[3]-1)*dv};}
    return points;
  }
  function sampleColor(points,time) {
    if(time<=points[0].time)return [...points[0].value];if(time>=points.at(-1).time)return [...points.at(-1).value];let i=1;while(points[i].time<time)i++;const a=points[i-1],b=points[i],t=(time-a.time)/(b.time-a.time);return a.value.map((v,j)=>v+(b.value[j]-v)*t);
  }
  function normalizeAnimation(value, options = {}) {
    if(!Array.isArray(value)||value.length<2||value.length>MAX_POINTS)throw new Error('Une animation contient de 2 à 20 points clés dans cet éditeur.');
    const first=inputPoint(value[0],0);const vector=Array.isArray(first.value);const count=vector?first.value.length:1;
    if(vector&&(count<2||count>3))throw new Error('Un vecteur doit contenir 2 ou 3 composantes.');
    for(const entry of value){const p=inputPoint(entry,0);if(vector&&(!Array.isArray(p.value)||p.value.length!==count))throw new Error('Les vecteurs doivent avoir le même nombre de composantes.');if(!vector&&Array.isArray(p.value))throw new Error('Les points doivent tous avoir le même type de valeur.');}
    const curves=Array.from({length:count},(_,channel)=>normalizeNumber(value.map((entry,index)=>{const p=inputPoint(entry,index);return{time:p.time,value:vector?p.value[channel]:p.value,envelope:0};}),{...options,extendEndpoints:true}));
    return{curves,vector};
  }
  function valueSignature(value,type,duration=1){
    if(type==='ColorSequence')return JSON.stringify(normalizeColor(value).map(p=>({time:round(p.time),value:p.value.map(round)})));
    if(type==='animation')return JSON.stringify(value.map((entry,i)=>{const p=inputPoint(entry,i);return{time:round(finite(p.time)),value:Array.isArray(p.value)?p.value.map(v=>round(finite(v))):round(finite(p.value))};}));
    return JSON.stringify(normalizeNumber(value).map(p=>({time:round(p.time),value:round(p.value),envelope:round(p.envelope||0)})));
  }
  const MathAPI=Object.freeze({MAX_POINTS,normalizeNumber,normalizeColor,normalizeAnimation,makeLinear,bezier,segmentControls,parameterAtTime,evaluate,linearAt,sampleTimes,bake,bakeAnimation,preset:applyPreset,sampleColor,boundsOf,assertBounds,valueSignature});
  global.DatakyCurvesMath=MathAPI;
  if(typeof module!=='undefined'&&module.exports)module.exports=MathAPI;

  let dialog, ui, state=null;
  const LABELS={Linear:'Linéaire',EaseIn:'Accélérer',EaseOut:'Ralentir',EaseInOut:'Doux',Burst:'Impulsion',Fade:'Fondu'};
  const COLORS=['#a997ef','#8ce9e2','#f2b383'];
  const hex = rgb => '#'+rgb.map(v=>Math.round(clamp(v,0,1)*255).toString(16).padStart(2,'0')).join('');
  function rgb(value){if(!/^#[0-9a-f]{6}$/i.test(value))throw new Error('Couleur attendue : #RRGGBB.');return[1,3,5].map(i=>parseInt(value.slice(i,i+2),16)/255);}
  const escape = text => String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function install() {
    if(dialog)return;
    const style=document.createElement('style');style.textContent=CSS;document.head.append(style);
    dialog=document.createElement('dialog');dialog.className='dc-dialog';dialog.setAttribute('aria-labelledby','dc-title');
    dialog.innerHTML=`<div class="dc-heading"><div><span class="dc-eyebrow">DATAKY · ÉDITEUR DE COURBES</span><h2 id="dc-title">Courbe</h2></div><button type="button" class="dc-close" aria-label="Fermer">×</button></div>
      <div class="dc-toolbar"><div class="dc-channels"></div><div class="dc-presets"></div><button type="button" class="dc-fit">⊙ Cadrer</button><button type="button" class="dc-reset">↺ Linéaire</button></div>
      <div class="dc-main"><section class="dc-graph-area"><svg class="dc-svg" viewBox="0 0 1000 440" tabindex="0" role="img" aria-label="Courbe éditable : glissez les points et les poignées, double-cliquez pour ajouter un point"></svg><div class="dc-gradient-wrap"><div class="dc-gradient"></div><div class="dc-color-stops"></div></div><div class="dc-legend"><span class="dc-legend-smooth">Courbe Bézier</span><span class="dc-legend-native">Courbe exportée dans Roblox</span><span class="dc-point-count"></span></div><p class="dc-guidance">Double-clic : ajouter · Glisser : déplacer · Suppr : retirer · Maj + flèches : déplacement fin</p></section>
      <aside class="dc-inspector"><span class="dc-eyebrow">POINT SÉLECTIONNÉ</span><h3 class="dc-point-title">Point 1</h3><label>Temps <span class="dc-time-unit"></span><input class="dc-point-time" type="number" step="0.01"></label><label class="dc-value-label">Valeur<input class="dc-point-value" type="number" step="any"></label><label class="dc-color-label">Couleur<div class="dc-color-inputs"><input class="dc-point-color" type="color"><input class="dc-point-hex" type="text" maxlength="7" spellcheck="false"></div></label><label class="dc-envelope-label">Aléa ± <input class="dc-point-envelope" type="number" min="0" step="any"></label><div class="dc-handle-fields"><span>POIGNÉES BÉZIER</span><label>Entrée <div><input class="dc-in-x" type="number" step="0.01" aria-label="Poignée d’entrée X"><input class="dc-in-y" type="number" step="any" aria-label="Poignée d’entrée Y"></div></label><label>Sortie <div><input class="dc-out-x" type="number" step="0.01" aria-label="Poignée de sortie X"><input class="dc-out-y" type="number" step="any" aria-label="Poignée de sortie Y"></div></label></div><div class="dc-point-actions"><button class="dc-add" type="button">+ Point</button><button class="dc-remove" type="button">Supprimer</button></div><div class="dc-bound-note"></div></aside></div>
      <details class="dc-json-details"><summary>Copier, coller ou importer les points JSON <span>↗</span></summary><textarea class="dc-json" spellcheck="false" aria-label="Données JSON de la courbe"></textarea><div class="dc-json-buttons"><button type="button" class="dc-copy">Copier les points</button><button type="button" class="dc-paste">Coller</button><button type="button" class="dc-json-import">Appliquer ce JSON</button></div></details>
      <div class="dc-error" role="alert"></div><div class="dc-bottom"><p class="dc-export-note">Roblox utilise des segments droits. La courbe est échantillonnée en 20 points maximum ; le tracé pointillé montre les données réellement exportées.</p><button type="button" class="dc-cancel">Annuler</button><button type="button" class="dc-apply">Appliquer la courbe</button></div>`;
    document.body.append(dialog);
    const q=selector=>dialog.querySelector(selector);
    ui={q,svg:q('.dc-svg'),gradient:q('.dc-gradient'),stops:q('.dc-color-stops')};
    q('.dc-close').onclick=q('.dc-cancel').onclick=()=>dialog.close();
    q('.dc-apply').onclick=apply;
    q('.dc-add').onclick=()=>addPoint();q('.dc-remove').onclick=deleteSelected;
    q('.dc-fit').onclick=()=>{state.range=null;draw();};q('.dc-reset').onclick=()=>preset('Linear');
    q('.dc-point-time').onchange=()=>changeTime(Number(q('.dc-point-time').value));
    q('.dc-point-value').onchange=()=>changeValue(Number(q('.dc-point-value').value));
    q('.dc-point-envelope').onchange=()=>{try{const v=finite(Number(q('.dc-point-envelope').value),'Aléa');if(v<0)throw new Error('L’aléa doit être positif.');current()[state.selected].envelope=v;changed();}catch(error){showError(error);renderInspector();}};
    q('.dc-point-color').oninput=()=>changeColor(q('.dc-point-color').value);q('.dc-point-hex').onchange=()=>changeColor(q('.dc-point-hex').value);
    for(const direction of ['in','out'])for(const axis of ['x','y'])q(`.dc-${direction}-${axis}`).onchange=()=>changeHandle(direction,axis,Number(q(`.dc-${direction}-${axis}`).value));
    q('.dc-copy').onclick=async()=>{try{await navigator.clipboard.writeText(JSON.stringify(exportValue(),null,2));q('.dc-copy').textContent='Copié ✓';setTimeout(()=>q('.dc-copy').textContent='Copier les points',1200);}catch(_){q('.dc-json').select();showError(new Error('Copiez le texte sélectionné avec Ctrl C.'));}};
    q('.dc-paste').onclick=async()=>{try{q('.dc-json').value=await navigator.clipboard.readText();importJSON();}catch(_){q('.dc-json').focus();showError(new Error('Collez votre JSON dans le champ, puis cliquez sur Appliquer ce JSON.'));}};
    q('.dc-json-import').onclick=importJSON;
    ui.svg.addEventListener('pointerdown',pointerDown);ui.svg.addEventListener('pointermove',pointerMove);ui.svg.addEventListener('pointerup',pointerUp);ui.svg.addEventListener('pointercancel',pointerUp);
    ui.svg.addEventListener('dblclick',event=>{if(event.target.closest('[data-point],[data-handle]'))return;const p=eventCoordinates(event);addPoint(clamp((p.x-PLOT.left)/PLOT.width,0,1),graphValue(p.y));});
    ui.svg.addEventListener('keydown',event=>{if(!state)return;if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();deleteSelected();}if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const p=current()[state.selected];const fine=event.shiftKey?.001:.01;if(event.key==='ArrowLeft')changeTime((p.time-fine)*state.duration);if(event.key==='ArrowRight')changeTime((p.time+fine)*state.duration);if(event.key==='ArrowUp'&&state.type!=='ColorSequence')changeValue(p.value+(state.graphRange.max-state.graphRange.min)*fine);if(event.key==='ArrowDown'&&state.type!=='ColorSequence')changeValue(p.value-(state.graphRange.max-state.graphRange.min)*fine);}});
    ui.stops.addEventListener('pointerdown',event=>{const target=event.target.closest('[data-stop]');if(!target)return;state.selected=Number(target.dataset.stop);state.drag={kind:'color',pointerId:event.pointerId};ui.stops.setPointerCapture(event.pointerId);renderInspector();draw();});
    ui.stops.addEventListener('pointermove',event=>{if(state?.drag?.kind!=='color')return;const rect=ui.stops.getBoundingClientRect();moveTime(clamp((event.clientX-rect.left)/rect.width,0,1));});
    ui.stops.addEventListener('pointerup',event=>{if(state?.drag?.kind==='color'){state.drag=null;if(ui.stops.hasPointerCapture(event.pointerId))ui.stops.releasePointerCapture(event.pointerId);changed();}});
    ui.stops.addEventListener('pointercancel',event=>{if(state?.drag?.kind==='color'){state.drag=null;if(ui.stops.hasPointerCapture(event.pointerId))ui.stops.releasePointerCapture(event.pointerId);changed();}});
    ui.gradient.ondblclick=event=>{const rect=ui.gradient.getBoundingClientRect();addPoint(clamp((event.clientX-rect.left)/rect.width,0,1));};
    dialog.addEventListener('close',()=>{state=null;});
  }
  function open(options) {
    if(!options||!['NumberSequence','ColorSequence','animation'].includes(options.type))throw new Error('Type de courbe inconnu.');
    const duration=options.type==='animation'?(options.duration??1):1;const definition=options.definition||{};
    let curves=[],colors=[],vector=false;
    if(options.type==='ColorSequence')colors=normalizeColor(options.value);
    else if(options.type==='animation'){const normalized=normalizeAnimation(options.value,{duration,definition});curves=normalized.curves;vector=normalized.vector;}
    else curves=[normalizeNumber(options.value,{definition})];
    install();state={type:options.type,duration,definition,curves,colors,vector,selected:0,channel:0,onApply:options.onApply,title:options.title||'Évolution de la propriété',range:null,drag:null};
    if(options.editor?.version===1&&Array.isArray(options.editor.curves)&&options.type!=='ColorSequence'){
      try{const restored=options.editor.curves.map(points=>normalizeNumber(points,{definition}));const signature=options.editor.valueSignature;const matches=signature&&signature===valueSignature(options.value,options.type,duration)&&options.editor.duration===duration;const shared=restored.every(points=>points.length===restored[0].length&&points.every((p,i)=>Math.abs(p.time-restored[0][i].time)<EPSILON));const restoredValue=options.type==='animation'?bakeAnimation(restored,{duration,definition,vector}):bake(restored[0],{definition});const faithful=valueSignature(restoredValue,options.type,duration)===signature;if(matches&&faithful&&shared&&restored.length===curves.length)state.curves=restored;}catch(_){}
    }
    ui.q('#dc-title').textContent=state.title;ui.q('.dc-time-unit').textContent=duration===1&&options.type!=='animation'?'0 → 1':'secondes';ui.q('.dc-json-details').open=false;showError(null);renderToolbar();renderInspector();draw();updateJSON();
    if(!dialog.open)dialog.showModal();ui.svg.focus();return{close:()=>dialog.close(),getValue:()=>exportValue()};
  }
  const PLOT={left:65,top:28,width:900,height:350};
  function current(){return state.type==='ColorSequence'?state.colors:state.curves[state.channel];}
  function format(v){return Number(v.toFixed(5)).toString();}
  function graphValue(y){const range=state.graphRange;return range.max-(y-PLOT.top)/PLOT.height*(range.max-range.min);}
  function graphX(t){return PLOT.left+t*PLOT.width;}
  function graphY(v){const range=state.graphRange;return PLOT.top+(range.max-v)/(range.max-range.min)*PLOT.height;}
  function rangeForGraph(){
    if(state.range)return state.range;const points=state.curves.flat();const vals=points.flatMap(p=>[p.value-(p.envelope||0),p.value+(p.envelope||0),p.value+(p.in?.y||0),p.value+(p.out?.y||0)]);let min=Math.min(0,...vals),max=Math.max(1,...vals);const gap=(max-min)*.12;const limits=boundsOf(state.definition);min=Math.max(limits.min,min-gap);max=Math.min(limits.max,max+gap);if(max-min<1e-6){min-=.5;max+=.5;}return{min,max};
  }
  function renderToolbar(){
    const channels=ui.q('.dc-channels');channels.replaceChildren();if(state.type!=='ColorSequence')state.curves.forEach((_,index)=>{const button=document.createElement('button');button.type='button';button.textContent=state.vector?(['X','Y','Z'][index]||String(index+1)):'Valeur';button.classList.toggle('active',index===state.channel);button.style.setProperty('--dc-channel',COLORS[index]);button.onclick=()=>{state.channel=index;state.range=null;renderToolbar();renderInspector();draw();};channels.append(button);});
    const presets=ui.q('.dc-presets');presets.replaceChildren();if(state.type!=='ColorSequence')for(const [key,label]of Object.entries(LABELS)){const button=document.createElement('button');button.type='button';button.textContent=label;button.title=key==='Burst'||key==='Fade'?'Remplace la forme de la courbe sélectionnée':label+' entre chaque paire de points';button.onclick=()=>preset(key);presets.append(button);}
    ui.q('.dc-reset').hidden=state.type==='ColorSequence';ui.q('.dc-fit').hidden=state.type==='ColorSequence';
  }
  function renderInspector(){
    const points=current();state.selected=clamp(state.selected,0,points.length-1);const point=points[state.selected];const color=state.type==='ColorSequence',endpoint=state.selected===0||state.selected===points.length-1;
    ui.q('.dc-point-title').textContent=`Point ${state.selected+1} / ${points.length}`;const time=ui.q('.dc-point-time');time.value=format(point.time*state.duration);time.min='0';time.max=state.duration;time.disabled=endpoint;ui.q('.dc-value-label').hidden=color;ui.q('.dc-color-label').hidden=!color;ui.q('.dc-envelope-label').hidden=color||state.type==='animation';ui.q('.dc-handle-fields').hidden=color;
    if(color){ui.q('.dc-point-color').value=hex(point.value);ui.q('.dc-point-hex').value=hex(point.value).toUpperCase();}
    else{const value=ui.q('.dc-point-value');value.value=format(point.value);const bounds=boundsOf(state.definition);if(Number.isFinite(bounds.min))value.min=bounds.min;else value.removeAttribute('min');if(Number.isFinite(bounds.max))value.max=bounds.max;else value.removeAttribute('max');ui.q('.dc-point-envelope').value=format(point.envelope||0);for(const direction of ['in','out']){for(const axis of ['x','y']){const input=ui.q(`.dc-${direction}-${axis}`);input.disabled=!point[direction];input.value=point[direction]?format(point[direction][axis]):'';}}}
    ui.q('.dc-remove').disabled=endpoint;ui.q('.dc-add').disabled=points.length>=MAX_POINTS;
    const bounds=boundsOf(state.definition);ui.q('.dc-bound-note').textContent=color?'Les couleurs Roblox utilisent des composantes de 0 à 1.':`${endpoint?'Le temps des points aux extrémités est verrouillé. ':''}${Number.isFinite(bounds.min)||Number.isFinite(bounds.max)?'Valeur autorisée : '+bounds.min+' → '+bounds.max+'. ':''}Glissez les poignées pour dessiner la courbure.`;
    ui.q('.dc-export-note').textContent=color?'Ce dégradé est transmis à Roblox sans conversion. Les couleurs sont interpolées entre les points.':'Roblox utilise des segments droits. La courbe est échantillonnée en 20 points maximum ; le tracé pointillé montre les données réellement exportées.';
    ui.q('.dc-legend-smooth').hidden=color;ui.q('.dc-legend-native').hidden=color;
  }
  function draw(){
    if(!state)return;const color=state.type==='ColorSequence';ui.q('.dc-gradient-wrap').hidden=!color;ui.svg.classList.toggle('dc-color-graph',color);ui.svg.innerHTML='';
    const svg=ui.svg;const ns='http://www.w3.org/2000/svg';const element=(tag,attributes={},text)=>{const el=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))el.setAttribute(key,value);if(text!==undefined)el.textContent=text;svg.append(el);return el;};
    if(color){drawColor();return;}
    state.graphRange=rangeForGraph();const range=state.graphRange;
    for(let i=0;i<=10;i++){const x=PLOT.left+i/10*PLOT.width;element('line',{x1:x,y1:PLOT.top,x2:x,y2:PLOT.top+PLOT.height,class:'dc-grid'});element('text',{x,y:PLOT.top+PLOT.height+25,'text-anchor':'middle',class:'dc-axis'},format(i/10*state.duration)+(state.type==='animation'?' s':''));}
    for(let i=0;i<=5;i++){const value=range.min+(range.max-range.min)*i/5;const y=graphY(value);element('line',{x1:PLOT.left,y1:y,x2:PLOT.left+PLOT.width,y2:y,class:'dc-grid'});element('text',{x:PLOT.left-12,y:y+4,'text-anchor':'end',class:'dc-axis'},format(value));}
    element('rect',{x:PLOT.left,y:PLOT.top,width:PLOT.width,height:PLOT.height,fill:'none',stroke:'#55475e','stroke-width':1});
    if(state.type!=='animation'){element('text',{x:PLOT.left,y:425,class:'dc-axis'},'Naissance');element('text',{x:PLOT.left+PLOT.width,y:425,'text-anchor':'end',class:'dc-axis'},'Fin de vie');}
    state.curves.forEach((points,channel)=>{
      const active=channel===state.channel;const color=COLORS[channel%COLORS.length];let path=`M ${graphX(points[0].time)} ${graphY(points[0].value)}`;
      for(let i=1;i<points.length;i++){const controls=segmentControls(points[i-1],points[i],state.definition);path+=` C ${graphX(controls.x1)} ${graphY(controls.y1)}, ${graphX(controls.x2)} ${graphY(controls.y2)}, ${graphX(controls.x3)} ${graphY(controls.y3)}`;}
      if(active&&state.type==='NumberSequence'){const upper=points.map(p=>[graphX(p.time),graphY(p.value+(p.envelope||0))]);const lower=[...points].reverse().map(p=>[graphX(p.time),graphY(p.value-(p.envelope||0))]);element('polygon',{points:[...upper,...lower].map(p=>p.join(',')).join(' '),fill:'#aa95e514',stroke:'none'});}
      element('path',{d:path,fill:'none',stroke:color,'stroke-width':active?2.6:1.2,opacity:active?1:.25,'pointer-events':'none'});
    });
    let baked;try{baked=state.type==='animation'?bakeAnimation(state.curves,{duration:state.duration,vector:state.vector,definition:state.definition}):bake(current(),{definition:state.definition});}catch(error){showError(error);return;}
    const nativePoints=baked.map(p=>[graphX(p.time/(state.type==='animation'?state.duration:1)),graphY(state.type==='animation'&&Array.isArray(p.value)?p.value[state.channel]:p.value)]);
    element('polyline',{points:nativePoints.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#eee7fa','stroke-width':1.25,'stroke-dasharray':'5 6',opacity:.6,'pointer-events':'none'});
    for(const [x,y]of nativePoints)element('circle',{cx:x,cy:y,r:2,fill:'#d9cce8',opacity:.65,'pointer-events':'none'});
    const points=current(),selected=points[state.selected];
    for(const direction of ['in','out'])if(selected[direction]){
      const adjacent=direction==='in'?points[state.selected-1]:points[state.selected+1];if(!adjacent)continue;const controls=direction==='in'?segmentControls(adjacent,selected,state.definition):segmentControls(selected,adjacent,state.definition);const x=graphX(direction==='in'?controls.x2:controls.x1),y=graphY(direction==='in'?controls.y2:controls.y1);element('line',{x1:graphX(selected.time),y1:graphY(selected.value),x2:x,y2:y,stroke:'#d0b7f0','stroke-width':1.2,'stroke-dasharray':'4 3'});element('circle',{cx:x,cy:y,r:10,fill:'transparent','data-handle':direction,class:'dc-handle-hit'});element('circle',{cx:x,cy:y,r:4.5,fill:'#21192c',stroke:'#d0b7f0','stroke-width':2,'pointer-events':'none'});
    }
    points.forEach((p,index)=>{element('circle',{cx:graphX(p.time),cy:graphY(p.value),r:12,fill:'transparent','data-point':index,class:'dc-point-hit'});element('circle',{cx:graphX(p.time),cy:graphY(p.value),r:index===state.selected?6:4.7,fill:index===state.selected?'#f7edff':COLORS[state.channel],stroke:index===state.selected?'#c6adee':'#241b2f','stroke-width':2,'pointer-events':'none'});});
    ui.q('.dc-point-count').textContent=`${points.length} points de contrôle · ${baked.length} points exportés`;
  }
  function drawColor(){
    const points=state.colors;ui.gradient.style.background=`linear-gradient(90deg,${points.map(p=>hex(p.value)+' '+p.time*100+'%').join(',')})`;ui.stops.replaceChildren();
    points.forEach((p,index)=>{const stop=document.createElement('button');stop.type='button';stop.className='dc-color-stop'+(index===state.selected?' selected':'');stop.dataset.stop=index;stop.style.left=p.time*100+'%';stop.style.setProperty('--dc-stop-color',hex(p.value));stop.title=`${format(p.time)} · ${hex(p.value)}`;stop.setAttribute('aria-label','Couleur '+(index+1)+' à '+format(p.time));stop.onclick=()=>{state.selected=index;renderInspector();drawColor();};stop.onkeydown=event=>{state.selected=index;if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();deleteSelected();}if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();changeTime(p.time+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?.001:.01));ui.stops.querySelector(`[data-stop="${state.selected}"]`)?.focus();}};ui.stops.append(stop);});
    ui.q('.dc-point-count').textContent=`${points.length} couleurs · double-clic sur le dégradé pour ajouter`;
  }
  function eventCoordinates(event){const rect=ui.svg.getBoundingClientRect();return{x:(event.clientX-rect.left)/rect.width*1000,y:(event.clientY-rect.top)/rect.height*440};}
  function pointerDown(event){if(!state||state.type==='ColorSequence')return;const point=event.target.closest('[data-point]'),handle=event.target.closest('[data-handle]');if(!point&&!handle)return;event.preventDefault();if(point)state.selected=Number(point.dataset.point);state.range=state.graphRange;state.drag={kind:handle?'handle':'point',direction:handle?.dataset.handle,pointerId:event.pointerId};ui.svg.setPointerCapture(event.pointerId);renderInspector();draw();ui.svg.focus();}
  function pointerMove(event){if(!state?.drag||state.drag.kind==='color')return;const position=eventCoordinates(event),t=clamp((position.x-PLOT.left)/PLOT.width,0,1),value=graphValue(position.y);if(state.drag.kind==='handle'){const point=current()[state.selected],direction=state.drag.direction;const index=state.selected;const min=direction==='in'?current()[index-1]?.time??point.time:point.time;const max=direction==='out'?current()[index+1]?.time??point.time:point.time;point[direction]={x:clamp(t,min,max)-point.time,y:clamp(value,boundsOf(state.definition).min,boundsOf(state.definition).max)-point.value};normalizeHandles(current());}
    else{moveTime(t,false);const limits=boundsOf(state.definition);current()[state.selected].value=clamp(value,limits.min,limits.max);}renderInspector();draw();}
  function pointerUp(event){if(!state?.drag||state.drag.kind==='color')return;state.drag=null;if(ui.svg.hasPointerCapture(event.pointerId))ui.svg.releasePointerCapture(event.pointerId);changed();}
  function normalizeHandles(points){for(let i=1;i<points.length;i++){const controls=segmentControls(points[i-1],points[i],state.definition);points[i-1].out={x:controls.x1-points[i-1].time,y:controls.y1-points[i-1].value};points[i].in={x:controls.x2-points[i].time,y:controls.y2-points[i].value};}}
  function moveTime(time,redraw=true){const points=current(),index=state.selected;if(index===0||index===points.length-1)return;const clamped=clamp(time,points[index-1].time+1e-5,points[index+1].time-1e-5);if(state.type==='ColorSequence')points[index].time=clamped;else for(const curve of state.curves){curve[index].time=clamped;normalizeHandles(curve);}if(redraw){renderInspector();draw();updateJSON();}}
  function changeTime(seconds){try{finite(seconds,'Temps');moveTime(seconds/state.duration);showError(null);}catch(error){showError(error);renderInspector();}}
  function changeValue(value){try{current()[state.selected].value=assertBounds(value,state.definition);normalizeHandles(current());changed();}catch(error){showError(error);renderInspector();}}
  function changeColor(value){try{state.colors[state.selected].value=rgb(value);changed();}catch(error){showError(error);renderInspector();}}
  function changeHandle(direction,axis,value){try{finite(value,'Poignée');const point=current()[state.selected];if(point[direction])point[direction][axis]=value;normalizeHandles(current());changed();}catch(error){showError(error);renderInspector();}}
  function addPoint(time,value){try{const points=current();if(points.length>=MAX_POINTS)throw new Error('La limite est de 20 points.');if(time===undefined){let best=0;for(let i=1;i<points.length;i++)if(points[i].time-points[i-1].time>points[best+1].time-points[best].time)best=i-1;time=(points[best].time+points[best+1].time)/2;}if(time<=EPSILON||time>=1-EPSILON||points.some(p=>Math.abs(p.time-time)<1e-5))return;let index=points.findIndex(p=>p.time>time);if(state.type==='ColorSequence')points.splice(index,0,{time,value:sampleColor(points,time)});else{for(let channel=0;channel<state.curves.length;channel++){const curve=state.curves[channel];const v=channel===state.channel&&value!==undefined?clamp(value,boundsOf(state.definition).min,boundsOf(state.definition).max):evaluate(curve,time,state.definition);curve.splice(index,0,{time,value:v,envelope:Math.max(0,linearAt(curve,time,'envelope'))});state.curves[channel]=makeLinear(curve);normalizeHandles(state.curves[channel]);}}state.selected=index;changed();}catch(error){showError(error);}}
  function deleteSelected(){const points=current();if(state.selected===0||state.selected===points.length-1)return;const index=state.selected;if(state.type==='ColorSequence')points.splice(index,1);else for(const curve of state.curves){curve.splice(index,1);normalizeHandles(curve);}state.selected=Math.max(0,index-1);changed();}
  function preset(name){try{if(state.type==='ColorSequence')return;let next=applyPreset(current(),name);if(name==='Burst'||name==='Fade'){const limits=boundsOf(state.definition);const original=current();const min=Math.max(limits.min,Math.min(...original.map(p=>p.value)));const max=Math.min(limits.max,Math.max(...original.map(p=>p.value)));const low=Number.isFinite(min)?min:0,high=Number.isFinite(max)&&max>low?max:Math.min(limits.max,low+1);next=next.map(p=>({...p,value:low+p.value*(high-low)}));next=makeLinear(next.map(({in:incoming,out,...p})=>p));const times=next.map(p=>p.time);for(let channel=0;channel<state.curves.length;channel++)if(channel!==state.channel){const previous=state.curves[channel];state.curves[channel]=makeLinear(times.map(time=>({time,value:evaluate(previous,time,state.definition),envelope:linearAt(previous,time,'envelope')})));}}state.curves[state.channel]=next;state.selected=Math.min(state.selected,next.length-1);state.range=null;changed();}catch(error){showError(error);}}
  function changed(){showError(null);renderInspector();draw();updateJSON();}
  function exportValue(){if(!state)throw new Error('Aucun éditeur ouvert.');if(state.type==='ColorSequence')return normalizeColor(state.colors).map(p=>({time:round(p.time),value:p.value.map(round)}));if(state.type==='animation')return bakeAnimation(state.curves,{duration:state.duration,vector:state.vector,definition:state.definition});return bake(current(),{definition:state.definition});}
  function updateJSON(){try{ui.q('.dc-json').value=JSON.stringify(exportValue(),null,2);}catch(error){showError(error);}}
  function importJSON(){try{const value=JSON.parse(ui.q('.dc-json').value);if(state.type==='ColorSequence')state.colors=normalizeColor(value);else if(state.type==='animation'){const result=normalizeAnimation(value,{duration:state.duration,definition:state.definition});state.curves=result.curves;state.vector=result.vector;state.channel=0;}else state.curves=[normalizeNumber(value,{definition:state.definition})];state.selected=0;state.range=null;renderToolbar();changed();}catch(error){showError(error);}}
  function showError(error){if(ui)ui.q('.dc-error').textContent=error?.message||'';}
  function apply(){try{const value=exportValue();const editor={version:1,mode:state.type==='ColorSequence'?'gradient':'bezier',...(state.type==='ColorSequence'?{colors:copy(state.colors)}:{curves:copy(state.curves)}),duration:state.duration,valueSignature:valueSignature(value,state.type,state.duration)};state.onApply?.({value,editor});dialog.close();}catch(error){showError(error);}}
  const CSS=`.dc-dialog{width:min(1220px,96vw);max-width:96vw;max-height:94dvh;margin:auto;padding:23px 26px;background:#201a29;color:#ece5f4;border:1px solid #5b486b;border-radius:15px;font-family:'DM Sans',system-ui,sans-serif;box-shadow:0 25px 120px #0009;overflow:auto}.dc-dialog::backdrop{background:#09060dcc;backdrop-filter:blur(5px)}.dc-dialog [hidden]{display:none!important}.dc-dialog button{cursor:pointer;color:#bfb2cd;font:11px inherit;border:1px solid #4d405c;background:#2c2437;border-radius:5px;padding:7px 11px;transition:background .15s}.dc-dialog button:hover{background:#40314f}.dc-dialog button:disabled{opacity:.35;cursor:default}.dc-dialog input,.dc-dialog textarea{font:11px/1.5 ui-monospace,monospace;color:#e5dced;background:#15101c;border:1px solid #51405f;border-radius:5px;padding:8px;min-width:0;outline-offset:2px}.dc-dialog input:focus,.dc-dialog textarea:focus{border-color:#bc9bec;outline:1px solid #bc9bec44}.dc-dialog input[type=number]{appearance:textfield}.dc-dialog input::-webkit-inner-spin-button{opacity:.2}.dc-dialog h2,.dc-dialog h3,.dc-dialog p{margin:0}.dc-heading{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:22px}.dc-heading h2{font:500 24px 'Space Grotesk',system-ui,sans-serif;letter-spacing:-.5px;margin-top:5px}.dc-eyebrow{color:#9a87ad;font-size:8px;font-weight:600;letter-spacing:1.8px}.dc-dialog .dc-close{font-size:24px;line-height:1;border:0;background:none;padding:0 5px}.dc-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:13px;flex-wrap:wrap}.dc-channels{display:flex;gap:3px;margin-right:10px}.dc-channels button{min-width:32px;border-color:#51405f}.dc-channels button.active{color:var(--dc-channel,#aa95e5);border-color:var(--dc-channel,#aa95e5);background:#aa95e516}.dc-presets{display:flex;gap:4px;flex:1;flex-wrap:wrap}.dc-presets button{font-size:10px;padding:6px 9px;background:transparent;color:#a997bd}.dc-main{display:grid;grid-template-columns:minmax(0,1fr) 200px;gap:20px}.dc-graph-area{min-width:0}.dc-svg{display:block;width:100%;height:auto;aspect-ratio:1000/440;background:radial-gradient(ellipse at 50% 70%,#2a2035,#17111f);border:1px solid #4d3d5c;border-radius:8px;touch-action:none;user-select:none;outline-offset:3px}.dc-svg.dc-color-graph{display:none}.dc-grid{stroke:#4e3b5a77;stroke-width:.8}.dc-axis{font:10px ui-monospace,monospace;fill:#9d87ad;user-select:none}.dc-point-hit{cursor:grab}.dc-point-hit:active,.dc-handle-hit:active{cursor:grabbing}.dc-handle-hit{cursor:move}.dc-inspector{border-left:1px solid #4a385766;padding-left:19px}.dc-inspector h3{font-size:15px;font-weight:500;margin:9px 0 17px}.dc-inspector>label{display:flex;flex-direction:column;gap:5px;color:#a996bb;font-size:10px;margin-bottom:13px}.dc-inspector label input{width:100%}.dc-time-unit{color:#796586;font-size:8px;margin-left:auto;margin-top:-16px}.dc-handle-fields{border-top:1px solid #4d3b5c66;margin-top:8px;padding-top:13px}.dc-handle-fields>span{font-size:8px;letter-spacing:1px;color:#7f6c8e}.dc-handle-fields label{display:flex;flex-direction:column;gap:5px;font-size:9px;color:#9985aa;margin-top:10px}.dc-handle-fields label>div{display:flex;gap:5px}.dc-handle-fields input{width:50%;padding:6px}.dc-inspector .dc-point-actions{display:flex;gap:5px;margin-top:15px}.dc-point-actions button{font-size:9px;padding:6px 7px}.dc-point-actions .dc-remove{color:#e5a4bc}.dc-bound-note{font-size:9px;color:#7f6b8e;line-height:1.7;margin-top:12px}.dc-legend{display:flex;align-items:center;gap:20px;margin:14px 0 8px;color:#b9a8c9;font-size:9px}.dc-legend-smooth:before,.dc-legend-native:before{content:'';display:inline-block;width:19px;vertical-align:middle;margin-right:7px;border-top:2px solid #b69aed}.dc-legend-native:before{border-color:#eee7fa;border-top-style:dashed}.dc-point-count{color:#887495;margin-left:auto;font-size:9px}.dc-guidance{color:#796587;font-size:9px;line-height:1.7}.dc-json-details{margin-top:20px;border-top:1px solid #4d3c5b88;padding-top:13px;color:#a48bb6;font-size:10px}.dc-json-details summary{cursor:pointer;list-style:none;display:flex;gap:8px}.dc-json-details summary span{margin-left:auto}.dc-json{width:100%;height:155px;resize:vertical;margin-top:12px;tab-size:2}.dc-json-buttons{display:flex;gap:7px;margin-top:7px}.dc-json-buttons button{font-size:10px}.dc-json-buttons button:last-child{margin-left:auto}.dc-bottom{display:flex;gap:9px;align-items:center;border-top:1px solid #4d3b5c88;margin-top:16px;padding-top:17px}.dc-export-note{font-size:9px;color:#897496;line-height:1.8;flex:1;max-width:710px;padding-right:24px}.dc-dialog .dc-apply{background:#8ce9e2;border-color:#8ce9e2;color:#163b34;font-weight:600;padding:10px 14px}.dc-dialog .dc-apply:hover{background:#b5f5ec}.dc-error{color:#f5a2bf;font-size:11px;line-height:1.7;white-space:pre-wrap;margin-top:9px}.dc-gradient-wrap{height:330px;background:radial-gradient(ellipse at 50% 70%,#2a2035,#17111f);border:1px solid #4d3d5c;border-radius:8px;display:flex;flex-direction:column;justify-content:center;padding:40px 35px}.dc-gradient{height:125px;border-radius:6px;cursor:crosshair;border:1px solid #f7edff22;box-shadow:0 10px 35px #0004}.dc-color-stops{position:relative;height:45px;touch-action:none;margin-top:0}.dc-dialog .dc-color-stop{position:absolute;top:10px;transform:translateX(-50%);width:19px;height:27px;padding:0;border:2px solid #a48bb688;background:var(--dc-stop-color);border-radius:3px;cursor:ew-resize;box-shadow:0 2px 5px #0007}.dc-color-stop:before{content:'';position:absolute;top:-8px;left:3px;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:6px solid #a48bb6}.dc-dialog .dc-color-stop.selected{border-color:#fff2ff;box-shadow:0 0 0 3px #bc9bec33}.dc-color-stop.selected:before{border-bottom-color:#fff2ff}.dc-color-inputs{display:flex;gap:7px}.dc-color-inputs input[type=color]{padding:3px;width:44px;height:34px;flex:none;cursor:pointer}.dc-color-inputs input[type=text]{flex:1;font-size:10px}@media(max-width:850px){.dc-dialog{padding:18px}.dc-main{grid-template-columns:minmax(0,1fr) 160px;gap:12px}.dc-inspector{padding-left:11px}.dc-export-note{font-size:8px;padding-right:10px}.dc-legend{gap:9px;flex-wrap:wrap}.dc-point-count{width:100%;margin-left:0}.dc-presets button{font-size:9px;padding:5px}.dc-heading h2{font-size:20px}}`;
  global.DatakyCurves=Object.freeze({open});
})(typeof window!=='undefined'?window:globalThis);
