/* Direction and human review use the editor's existing project/undo surface. */
(() => {
  'use strict';
  const $ = selector => dialog.querySelector(selector);
  const PHASES = ['anticipation','charge','release','impact','secondary','dissipation'];
  const LABELS = ['Anticipation','Accumulation','Déclenchement','Impact','Secondaires','Dissipation'];
  const CRITERIA = {depth:'Profondeur',silhouette:'Silhouette',readability:'Lisibilité',palette:'Couleurs',motion:'Mouvement',impact:'Force de l’impact',composition:'Composition',redundancy:'Éléments inutiles',overload:'Surcharge'};
  const dialog = document.createElement('dialog');
  dialog.className = 'artistry-dialog'; dialog.id = 'artistry-dialog';
  dialog.innerHTML = `<header><div><h2>Direction & revue</h2><p class="artistry-note">Donner une intention à chaque couche, puis regarder l’attaque dans le temps.</p></div><button id="art-close" aria-label="Fermer">✕</button></header>
    <nav class="artistry-tabs" aria-label="Atelier artistique">${[['direction','Direction'],['motion','Mouvement'],['review','Revue visuelle'],['references','Références'],['demos','Démonstrations']].map(([id,label])=>`<button data-art-tab="${id}" aria-selected="${id==='direction'}">${label}</button>`).join('')}</nav>
    <section data-art-panel="direction"><div class="artistry-grid">
      <label>Thème<input id="art-theme" placeholder="Ex. une lame de marée comprimée"></label>
      <label>Personnalité du personnage<input id="art-character" placeholder="Précis, vif, retenu…"></label>
      <label>Silhouette<textarea id="art-silhouette" placeholder="Quelle forme doit-on reconnaître ?"></textarea></label>
      <label>Mouvement<textarea id="art-motion-intent" placeholder="Sens, rythme, accélération, rebond…"></textarea></label>
      <label>Palette · 2 à 5 couleurs #RRGGBB<input id="art-palette" value="#62dcff, #19406f, #fff4d6"></label>
      <label>Point focal · x, y, z<input id="art-focal" value="0, 2, 0"></label>
      <label>Lisibilité Tower Defense<textarea id="art-readability" placeholder="Ce qui doit rester visible depuis la caméra de jeu"></textarea></label>
      <label>Puissance visuelle <select id="art-power"><option value="1">1 · discret</option><option value="2">2</option><option selected value="3">3 · marqué</option><option value="4">4</option><option value="5">5 · exceptionnel</option></select></label>
    </div><h3>Les six phases</h3><p class="artistry-note">Temps en secondes. Les courbes servent d’intention ; le panneau Mouvement les applique aux objets.</p>
    <table class="artistry-table"><thead><tr><th>Phase</th><th>Début</th><th>Durée</th><th>Courbe</th></tr></thead><tbody id="art-phases"></tbody></table>
    <h3>Fonction des couches</h3><p class="artistry-note">Chaque objet appartient à une couche. Sélection multiple avec Ctrl/Cmd.</p><div id="art-layers"></div><button id="art-add-layer">+ Couche</button>
    <div class="artistry-actions"><button id="art-save-plan" class="primary">Enregistrer la direction</button><button id="art-inspect">Vérifier la composition</button></div><pre id="art-inspection" class="artistry-report" hidden></pre>
    <h3>Variantes de qualité</h3><div class="artistry-actions"><label>Émissions maximales<input id="art-budget" type="number" min="1" max="100000" value="600"></label><button data-art-quality="medium">Densité moyenne</button><button data-art-quality="low">Densité légère</button><button id="art-reduced">Réduire les effets lumineux</button></div></section>
    <section data-art-panel="motion" hidden><p class="artistry-note">La trajectoire devient une animation éditable et exportable. Les Attachments se déplacent dans le repère de leur parent.</p>
    <div class="artistry-grid"><label>Objet<select id="art-motion-node"></select></label><label>Trajectoire<select id="art-motion-type"><option value="bezier">Courbe Bézier</option><option value="arc">Arc courbé</option><option value="helix">Spirale 3D</option><option value="orbit">Orbite</option></select></label><label>Début (s)<input id="art-motion-start" type="number" min="0" step="0.01" value="0"></label><label>Durée (s)<input id="art-motion-duration" type="number" min="0.01" step="0.01" value="1"></label>
    <label>Courbe<select id="art-motion-easing">${['linear','in','out','inOut','backOut'].map(e=>`<option>${e}</option>`).join('')}</select></label><label>Précision<select id="art-motion-samples"><option>31</option><option selected>61</option><option>121</option><option>241</option></select></label></div>
    <div id="art-bezier-fields" class="artistry-grid">${['Départ','Contrôle 1','Contrôle 2','Arrivée'].map((label,i)=>`<label>${label} · x, y, z<input data-point="${i}" value="${[[0,2,0],[2,5,-2],[6,5,-4],[8,2,-6]][i].join(', ')}"></label>`).join('')}</div>
    <div id="art-orbit-fields" class="artistry-grid" hidden><label>Centre · x, y, z<input id="art-center" value="0, 2, 0"></label><label>Axe<select id="art-axis"><option>x</option><option selected>y</option><option>z</option></select></label><label>Rayon initial<input id="art-radius" type="number" min="0" value="2" step="0.1"></label><label>Rayon final<input id="art-end-radius" type="number" min="0" value="0.5" step="0.1"></label><label>Tours<input id="art-turns" type="number" value="1.5" step="0.1"></label><label>Hauteur<input id="art-height" type="number" value="3" step="0.1"></label></div>
    <label class="artistry-actions"><input id="art-replace-motion" type="checkbox"> Remplacer la piste Position existante</label><div class="artistry-actions"><button id="art-apply-motion" class="primary">Appliquer la trajectoire</button></div></section>
    <section data-art-panel="review" hidden><p class="artistry-note">Deux angles, deux fonds et les phases clés. La tentative suivante compare avec la précédente. Examinez les images avant de remplir les observations.</p>
    <div class="artistry-actions"><label>Maximum de tentatives<input id="art-max-attempts" type="number" value="3" min="1" max="8"></label><button id="art-capture" class="primary">Capturer pour la revue</button><button id="art-new-review">Nouvelle session</button></div><p id="art-review-state" role="status">Aucune session.</p><div id="art-captures" class="artistry-captures"></div>
    <div id="art-observations" class="artistry-grid">${Object.entries(CRITERIA).map(([key,label])=>`<label>${label}<textarea data-criterion="${key}" placeholder="Observation concrète sur les captures"></textarea></label>`).join('')}</div>
    <div class="artistry-actions"><button id="art-revise">Demander une correction</button><button id="art-approve">Valider cette version</button></div></section>
    <section data-art-panel="references" hidden><p class="artistry-note">Les observations viennent de vous ou d’un agent doté de vision. Elles guident un effet original. Les vidéos sont conservées ; leur analyse automatique n’est pas incluse.</p><div class="artistry-grid"><label class="artistry-wide">Fichier local · chemin complet<input id="art-ref-path" placeholder="C:\\...\\reference.png"></label><label>Type<select id="art-ref-kind"><option value="image">Image</option><option value="spritesheet">Spritesheet</option><option value="video">Vidéo</option></select></label><label>Nom<input id="art-ref-name"></label><label>Formes<textarea id="art-ref-forms"></textarea></label><label>Couleurs<textarea id="art-ref-colors"></textarea></label><label>Rythme<textarea id="art-ref-rhythm"></textarea></label><label>Mouvement et profondeur<textarea id="art-ref-motion"></textarea></label></div><div class="artistry-actions"><button id="art-add-ref" class="primary">Ajouter la référence observée</button></div><div id="art-references"></div></section>
    <section data-art-panel="demos" hidden><p class="artistry-note">Ces exemples ouvrent une nouvelle composition ; le brouillon actuel reste accessible avec Annuler.</p><div id="art-demos"></div></section>
    <p id="art-error" class="artistry-error" role="status"></p>`;
  document.body.append(dialog);
  const trigger = document.createElement('button'); trigger.id='artistry-button'; trigger.className='quiet';trigger.textContent='✦ Direction & revue';
  document.querySelector('.toolbar-actions').prepend(trigger);
  let plan=null, review=null, identity='', busy=false;
  const project = () => window.DatakyFX.getProject();
  async function request(action, body) {
    const response = await fetch('/api/artistry/'+action, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json(); if(!response.ok)throw new Error(value.error||'Opération impossible');return value;
  }
  async function run(work) {if(busy)return;busy=true;$('#art-error').textContent='';dialog.setAttribute('aria-busy','true');try{await work();}catch(error){$('#art-error').textContent=error.message;}finally{busy=false;dialog.removeAttribute('aria-busy');}}
  const vector = input => {const v=input.value.split(',').map(s=>Number(s.trim()));if(v.length!==3||v.some(n=>!Number.isFinite(n)))throw new Error('Trois nombres séparés par des virgules sont requis.');return v;};
  function tab(id){dialog.querySelectorAll('[data-art-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.artTab===id)));dialog.querySelectorAll('[data-art-panel]').forEach(p=>p.hidden=p.dataset.artPanel!==id);}
  function layer(value={}) {
    const row=document.createElement('div'); row.className='artistry-layer'; row.dataset.layerId=value.id||'layer_'+crypto.randomUUID().slice(0,8);
    row.innerHTML='<div class="artistry-grid"><label>Rôle<select data-layer="role"><option value="primary">Principal</option><option value="secondary">Secondaire</option><option value="accent">Accent</option></select></label><label>Phase<select data-layer="phase"></select></label><label>Profondeur<select data-layer="depth"><option value="foreground">Premier plan</option><option value="midground">Plan central</option><option value="background">Arrière-plan</option></select></label><label class="artistry-wide">Fonction artistique<input data-layer="purpose" placeholder="Ex. guider l’œil vers le tranchant"></label><label class="artistry-wide">Objets<select multiple data-layer="nodes"></select></label></div><button data-remove-layer>Retirer la couche</button>';
    PHASES.forEach((p,i)=>row.querySelector('[data-layer=phase]').add(new Option(LABELS[i],p)));
    project().nodes.forEach(n=>{const option=new Option((n.name||n.id)+' · '+n.class,n.id);option.selected=(value.nodes||[]).includes(n.id);row.querySelector('[data-layer=nodes]').add(option);});
    for(const key of ['role','phase','depth','purpose'])if(value[key])row.querySelector(`[data-layer=${key}]`).value=value[key];
    row.querySelector('[data-remove-layer]').onclick=()=>row.remove();$('#art-layers').append(row);
  }
  function fillPlan(p) {
    const b=p?.brief||{};for(const key of ['theme','character','silhouette','readability'])$('#art-'+key).value=b[key]||'';
    $('#art-motion-intent').value=b.motion||'';$('#art-focal').value=(b.focal||project().camera.target).join(', ');$('#art-power').value=b.power||3;
    if(b.palette)$('#art-palette').value=b.palette.map(c=>'#'+c.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')).join(', ');
    $('#art-phases').replaceChildren();let start=0;
    PHASES.forEach((name,i)=>{const d=project().duration*[.12,.2,.08,.15,.15,.3][i],phase=p?.phases[i]||{start,duration:d,easing:'linear'};const row=document.createElement('tr');row.innerHTML=`<td>${LABELS[i]}</td><td><input type="number" min="0" step="0.01" data-phase-start value="${+phase.start.toFixed(5)}"></td><td><input type="number" min="0" step="0.01" data-phase-duration value="${+phase.duration.toFixed(5)}"></td><td><select data-phase-easing>${['linear','in','out','inOut','backOut'].map(x=>`<option>${x}</option>`).join('')}</select></td>`;row.querySelector('select').value=phase.easing;$('#art-phases').append(row);start+=d;});
    $('#art-layers').replaceChildren();(p?.layers||[]).forEach(layer);if(!p?.layers?.length)layer();
  }
  function readBrief(){const palette=$('#art-palette').value.split(',').map(s=>{const color=s.trim();if(!/^#[\da-f]{6}$/i.test(color))throw new Error('Palette : couleurs #RRGGBB séparées par des virgules.');return [1,3,5].map(i=>parseInt(color.slice(i,i+2),16)/255);});
    return {theme:$('#art-theme').value,character:$('#art-character').value,silhouette:$('#art-silhouette').value,motion:$('#art-motion-intent').value,readability:$('#art-readability').value,palette,focal:vector($('#art-focal')),power:Number($('#art-power').value),budget:plan?.budget,
      phases:Array.from($('#art-phases').rows,(row,i)=>({name:PHASES[i],start:Number(row.querySelector('[data-phase-start]').value),duration:Number(row.querySelector('[data-phase-duration]').value),easing:row.querySelector('select').value})),
      layers:Array.from($('#art-layers').children,row=>({id:row.dataset.layerId,role:row.querySelector('[data-layer=role]').value,phase:row.querySelector('[data-layer=phase]').value,depth:row.querySelector('[data-layer=depth]').value,purpose:row.querySelector('[data-layer=purpose]').value,nodes:Array.from(row.querySelector('[data-layer=nodes]').selectedOptions,o=>o.value)}))};}
  function sessionKey(){return 'dataky-art-review:'+identity;}
  function showReview(){const state=review?.state;const labels={ready:'Prête à capturer',revise:'Correction attendue avant la prochaine capture',awaiting_human_review:'Validation humaine requise',awaiting_vision_review:'Revue visuelle requise',approved:'Version validée',exhausted:'Limite atteinte · commencer une nouvelle session si nécessaire'};
    $('#art-review-state').textContent=review?`${labels[state]||state} · ${review.attempts.length}/${review.max_attempts} tentatives`:'Aucune session.';
    $('#art-captures').replaceChildren();const last=review?.attempts.at(-1);
    (last?.images||[]).forEach((path,i)=>{const a=document.createElement('a');a.target='_blank';a.rel='noopener';a.href='/api/artistry/file/'+review.id+'/'+path.split(/[\\/]/).at(-1);const image=document.createElement('img');image.src=a.href;image.alt=i?'Vue Tower Defense · jour et nuit':'Vue rapprochée · jour et nuit';a.append(image,document.createTextNode(image.alt+' · ouvrir en grand'));$('#art-captures').append(a);});
    const pending=state==='awaiting_human_review'||state==='awaiting_vision_review';$('#art-approve').disabled=$('#art-revise').disabled=!pending;$('#art-capture').disabled=!!review&&!['ready','revise'].includes(state);
    dialog.querySelectorAll('[data-criterion]').forEach(field=>{field.value=last?.review?.observations?.[field.dataset.criterion]||'';field.disabled=!pending;});
  }
  async function references(){const data=await request('references');$('#art-references').replaceChildren();for(const ref of data.references){const card=document.createElement('div');card.className='artistry-layer';const a=document.createElement('a');a.href='/api/artistry/reference/'+ref.id;a.target='_blank';a.rel='noopener';a.textContent=ref.name+' · '+ref.kind;const note=document.createElement('p');note.textContent=Object.entries(ref.observations||{}).map(([k,v])=>k+': '+v).join(' · ');card.append(a,note);$('#art-references').append(card);}}
  trigger.onclick=()=>run(async()=>{
    identity=project().id||project().name;
    plan=project().id?await request('plan/'+encodeURIComponent(project().id)):null;
    fillPlan(plan);
    const select=$('#art-motion-node');select.replaceChildren();
    project().nodes.filter(n=>['Part','MeshPart','Attachment'].includes(n.class)).forEach(n=>select.add(new Option(n.name||n.id,n.id)));
    $('#art-motion-duration').value=Math.min(1,project().duration);review=null;
    const saved=localStorage.getItem(sessionKey());
    if(saved&&saved!=='new'){
      try{review=await request('review/'+saved);}catch(_){localStorage.removeItem(sessionKey());}
    }else if(!saved&&project().id){
      const history=await request('reviews?project_id='+encodeURIComponent(project().id));
      if(history.reviews.length){review=await request('review/'+history.reviews[0].id);localStorage.setItem(sessionKey(),review.id);}
    }
    showReview();await references();dialog.showModal();
  });
  $('#art-close').onclick=()=>dialog.close();dialog.querySelectorAll('[data-art-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.artTab));$('#art-add-layer').onclick=()=>layer();
  $('#art-save-plan').onclick=()=>run(async()=>{const brief=readBrief();if(!brief.budget)delete brief.budget;plan=await request('plan',{project:project(),brief});$('#art-error').textContent='Direction enregistrée.';});
  $('#art-inspect').onclick=()=>run(async()=>{const report=await request('inspect',{project:project(),plan});$('#art-inspection').hidden=false;$('#art-inspection').textContent=JSON.stringify(report,null,2);});
  const profile=(quality,reduced=false)=>run(async()=>{const result=await request('profile',{project:project(),plan,quality,reduced,max_particles:Number($('#art-budget').value)});window.DatakyFX.setProject(result.project);$('#art-error').textContent='Variante appliquée au brouillon. Annuler restaure la précédente.';});
  dialog.querySelectorAll('[data-art-quality]').forEach(b=>b.onclick=()=>profile(b.dataset.artQuality));$('#art-reduced').onclick=()=>profile('medium',true);
  $('#art-motion-type').onchange=()=>{const type=$('#art-motion-type').value;$('#art-bezier-fields').hidden=!['bezier','arc'].includes(type);$('#art-orbit-fields').hidden=['bezier','arc'].includes(type);};
  $('#art-apply-motion').onclick=()=>run(async()=>{const type=$('#art-motion-type').value,spec={type,node:$('#art-motion-node').value,start:Number($('#art-motion-start').value),duration:Number($('#art-motion-duration').value),samples:Number($('#art-motion-samples').value),easing:$('#art-motion-easing').value,replace:$('#art-replace-motion').checked};const points=Array.from(dialog.querySelectorAll('[data-point]'),vector);if(type==='bezier')spec.points=points;else if(type==='arc')Object.assign(spec,{from:points[0],to:points[3],height:Number($('#art-height').value)});else{Object.assign(spec,{center:vector($('#art-center')),radius:Number($('#art-radius').value),end_radius:Number($('#art-end-radius').value),turns:Number($('#art-turns').value),axis:$('#art-axis').value});if(type==='helix')spec.height=Number($('#art-height').value);}const result=await request('motion',{project:project(),specs:spec});window.DatakyFX.setProject(result.project);$('#art-error').textContent='Trajectoire appliquée. Fermez ce panneau et lancez la lecture.';});
  $('#art-new-review').onclick=()=>{review=null;localStorage.setItem(sessionKey(),'new');showReview();};
  $('#art-capture').onclick=()=>run(async()=>{if(!review){review=await request('review_create',{project:project(),plan,max_attempts:Number($('#art-max-attempts').value),vision:false});localStorage.setItem(sessionKey(),review.id);}$('#art-review-state').textContent='Captures en cours…';review=await request('review_capture',{id:review.id,project:project(),plan});showReview();});
  const submit=decision=>run(async()=>{const observations=Object.fromEntries(Array.from(dialog.querySelectorAll('[data-criterion]'),field=>[field.dataset.criterion,field.value]));review=await request('review_submit',{id:review.id,attempt:review.attempts.at(-1).number,observer:'human',decision,observations});showReview();});
  $('#art-revise').onclick=()=>submit('revise');$('#art-approve').onclick=()=>submit('approve');
  $('#art-add-ref').onclick=()=>run(async()=>{const observations={};for(const key of ['forms','colors','rhythm','motion'])if($('#art-ref-'+key).value.trim())observations[key]=$('#art-ref-'+key).value;await request('reference_add',{path:$('#art-ref-path').value,kind:$('#art-ref-kind').value,name:$('#art-ref-name').value||undefined,observer:'human',observations});await references();$('#art-error').textContent='Référence conservée avec vos observations.';});
  const DEMOS=[['CelestialRiftSlash','Celestial Rift Slash','Entaille céleste courbée, seconde coupe retardée et fragments en profondeur.'],['SolarSpear','Solar Spear','Lance solaire à facettes, filaments hélicoïdaux et impact monocible.'],['PhantomBloom','Phantom Bloom','Sept pétales spectraux inégaux deviennent des lames convergentes.'],['artistry-slash-azur','Slash azur','Un tranchant courbé, trois traînées et une fin pincée.'],['artistry-projectile-ambre','Projectile ambre','Noyau lisible, orbites et trajectoire Bézier.'],['artistry-calligraphe-astral','Calligraphe astral','Une signature verticale et une coupe finale étroite.']];
  for(const [id,title,description]of DEMOS){const b=document.createElement('button');b.className='artistry-demo';const strong=document.createElement('strong');strong.textContent=title;const span=document.createElement('span');span.textContent=description;b.append(strong,span);b.onclick=()=>run(async()=>{const response=await fetch('/api/project/'+id);const data=await response.json();if(!response.ok)throw new Error(data.error);window.DatakyFX.setProject(data);dialog.close();});$('#art-demos').append(b);}
})();
