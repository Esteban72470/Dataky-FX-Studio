'use strict';

(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const clone = value => JSON.parse(JSON.stringify(value));
  const STORE = 'dataky-fx-studio.project.v1';
  const CACHE_SCHEMA = 'dataky-fx-studio.schema.v1';
  const ICONS = {Part:'◇',MeshPart:'⬡',SpecialMesh:'⬡',Attachment:'⊹',ParticleEmitter:'✦',Beam:'⌁',Trail:'↝',PointLight:'☀',SpotLight:'◉',SurfaceLight:'◧',Folder:'▱',Model:'▣'};
  const COLLECTION_LABELS = {textures:'textures', beams:'beams', meshes:'meshes'};
  const TIMED_CLASSES = ['ParticleEmitter','Beam','Trail','PointLight','SpotLight','SurfaceLight'];
  const CONTENT_BY_CLASS = {ParticleEmitter:'Texture',Beam:'Texture',Trail:'Texture',MeshPart:'MeshId',SpecialMesh:'MeshId'};
  const GROUPS = [
    ['Position & forme', ['Position','Orientation','Size','Scale','Offset','MeshType','Shape','ShapeStyle','ShapeInOut','ShapePartial','EmissionDirection','SpreadAngle','Rotation','RotSpeed']],
    ['Apparence', ['Texture','MeshId','TextureID','TextureId','Color','Transparency','Material','MaterialVariant','Reflectance','LightEmission','LightInfluence','Brightness','ZOffset','CastShadow','Enabled','Face','Style']],
    ['Émission & mouvement', ['Rate','Lifetime','Speed','Acceleration','Drag','VelocityInheritance','VelocitySpread','LockedToPart','WindAffectsDrag','TimeScale','Orientation','Squash']],
    ['Liaison & courbure', ['Attachment0','Attachment1','Width0','Width1','CurveSize0','CurveSize1','Segments','FaceCamera','TextureLength','TextureSpeed','TextureMode','MinLength','MaxLength','WidthScale']],
    ['Flipbook', ['FlipbookLayout','FlipbookMode','FlipbookFramerate','FlipbookStartRandom','FlipbookSizeX','FlipbookSizeY']],
    ['Lumière', ['Range','Angle','Shadows']],
    ['Comportement', ['Anchored','CanCollide','CanTouch','CanQuery','Massless','Locked','Archivable','DoubleSided','RenderFidelity','CollisionFidelity','PivotOffset']]
  ];
  const fallbackSchema = {version:1,classes:{
    Part:{properties:{Position:{type:'Vector3',default:[0,0,0]},Orientation:{type:'Vector3',default:[0,0,0]},Size:{type:'Vector3',default:[2,1,2]},Transparency:{type:'number',default:1,min:0,max:1},Anchored:{type:'boolean',default:true},CanCollide:{type:'boolean',default:false},Color:{type:'Color3',default:[1,1,1]}}},
    Attachment:{properties:{Position:{type:'Vector3',default:[0,0,0]},Orientation:{type:'Vector3',default:[0,0,0]}}},
    ParticleEmitter:{properties:{Texture:{type:'content',default:'rbxasset://textures/particles/sparkles_main.dds'},Color:{type:'ColorSequence',default:[[0,[1,1,1]],[1,[1,1,1]]]},Size:{type:'NumberSequence',default:[[0,1,0],[1,0,0]]},Transparency:{type:'NumberSequence',default:[[0,0,0],[1,1,0]]},Lifetime:{type:'NumberRange',default:[0.5,1]},Speed:{type:'NumberRange',default:[3,6]},Rate:{type:'number',default:20,min:0},SpreadAngle:{type:'Vector2',default:[180,180]},Acceleration:{type:'Vector3',default:[0,0,0]},Enabled:{type:'boolean',default:true}}},
    Beam:{properties:{Attachment0:{type:'reference',default:null},Attachment1:{type:'reference',default:null},Texture:{type:'content',default:''},Color:{type:'ColorSequence',default:[[0,[1,1,1]],[1,[1,1,1]]]},Transparency:{type:'NumberSequence',default:[[0,0,0],[1,0,0]]},Width0:{type:'number',default:0.5,min:0},Width1:{type:'number',default:0.5,min:0},CurveSize0:{type:'number',default:0},CurveSize1:{type:'number',default:0},FaceCamera:{type:'boolean',default:true},Segments:{type:'integer',default:10,min:1}}},
    Trail:{properties:{Attachment0:{type:'reference',default:null},Attachment1:{type:'reference',default:null},Texture:{type:'content',default:''},Lifetime:{type:'number',default:0.5,min:0},Color:{type:'ColorSequence',default:[[0,[1,1,1]],[1,[1,1,1]]]},Transparency:{type:'NumberSequence',default:[[0,0,0],[1,1,0]]},WidthScale:{type:'NumberSequence',default:[[0,1,0],[1,0,0]]},FaceCamera:{type:'boolean',default:true}}},
    MeshPart:{properties:{MeshId:{type:'content',default:''},TextureID:{type:'content',default:''},Position:{type:'Vector3',default:[0,0,0]},Orientation:{type:'Vector3',default:[0,0,0]},Size:{type:'Vector3',default:[2,2,2]},Color:{type:'Color3',default:[1,1,1]},Transparency:{type:'number',default:0},Anchored:{type:'boolean',default:true},CanCollide:{type:'boolean',default:false}}},
    SpecialMesh:{properties:{MeshId:{type:'content',default:''},TextureId:{type:'content',default:''},Scale:{type:'Vector3',default:[1,1,1]},Offset:{type:'Vector3',default:[0,0,0]}}},
    PointLight:{properties:{Brightness:{type:'number',default:2,min:0},Range:{type:'number',default:10,min:0},Color:{type:'Color3',default:[1,1,1]},Shadows:{type:'boolean',default:false},Enabled:{type:'boolean',default:true}}},
    SpotLight:{properties:{Brightness:{type:'number',default:2,min:0},Range:{type:'number',default:10,min:0},Angle:{type:'number',default:90,min:0,max:180},Color:{type:'Color3',default:[1,1,1]},Enabled:{type:'boolean',default:true}}},
    SurfaceLight:{properties:{Brightness:{type:'number',default:2,min:0},Range:{type:'number',default:10,min:0},Angle:{type:'number',default:90,min:0,max:180},Color:{type:'Color3',default:[1,1,1]},Enabled:{type:'boolean',default:true}}},
    Folder:{properties:{}},Model:{properties:{}}
  }};
  let storedSchema;
  try { storedSchema = JSON.parse(localStorage.getItem(CACHE_SCHEMA) || 'null'); } catch (_) {}
  let schema = storedSchema?.classes ? storedSchema : fallbackSchema;
  let schemaOnline = false;
  let initial;
  try { initial = JSON.parse(localStorage.getItem(STORE) || 'null'); } catch (_) {}
  const emptyProject = () => ({version:1,name:'Mon nouvel effet',duration:3,loop:false,nodes:[],animations:[],camera:{position:[10,6,12],target:[0,1,0]},environment:{background:'#191522'}});
  let project = initial?.version === 1 && Array.isArray(initial.nodes) ? initial : emptyProject();
  let selectedId = project.nodes[0]?.id || null;
  let catalog = {textures:[],beams:[],meshes:[]};
  let collection = 'textures';
  let assetSelection = null;
  let filters = {textures:{search:'',tag:'',page:0},beams:{search:'',tag:'',page:0},meshes:{search:'',tag:'',page:0}};
  let catalogLoaded = false;
  let catalogFailed = false;
  let history = [];
  let future = [];
  let dirty = false;
  let time = 0;
  let nativeStatus = {connected:false};
  let runtime = {};
  let nativePaused = false;
  let nativePlaying = false;
  let sequenceEdit = null;
  let animationNode = null;
  let dragState = null;
  let screenStream = null;
  let viewportMode = 'native';
  let nativeFrameSequence=null,nativeFrameBusy=false,nativeFrameObjectURL=null,nativeFrameMeta=null,autoPreviewTimer=null,nativeFrameToken=0,replayAfterPermission=false;
  let planScale = 29;
  let cameraPan = [0,0];
  let sceneHitTargets = [];
  let saving = false;
  let schemaWarning = false;
  const numberFormat = new Intl.NumberFormat('fr-FR');
  const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (x, fallback = 0) => Number.isFinite(Number(x)) ? Number(x) : fallback;
  const bounded = (x,min,max) => Math.max(min,Math.min(max,x));
  const round = x => Math.round(x*1000)/1000;
  const nodeById = id => project.nodes.find(n => n.id === id);
  const selected = () => nodeById(selectedId);
  function uid(prefix='obj') { return prefix.toLowerCase().replace(/[^a-z0-9]/g,'') + '_' + (globalThis.crypto?.randomUUID?.().slice(0,8) || Math.random().toString(36).slice(2,10)); }
  function message(text, kind='info') {
    $('#status-text').textContent = text;
    const toast = document.createElement('div'); toast.className='toast '+kind; toast.textContent=text;
    $('#toast-region').append(toast); setTimeout(()=>toast.remove(),kind==='error'?8500:4200);
  }
  async function api(path, options={}) {
    const response = await fetch(path,{...options,headers:{...(options.body ? {'Content-Type':'application/json'} : {}),...options.headers}});
    let body; try { body = await response.json(); } catch (_) { body={error:response.statusText}; }
    if (!response.ok) {
      let error = body.error || body.message || `Erreur ${response.status}`;
      if (typeof error !== 'string') error = JSON.stringify(error);
      if (body.details) error += '\n' + (typeof body.details === 'string' ? body.details : JSON.stringify(body.details));
      throw new Error(error);
    }
    return body;
  }
  function persist() {
    try { localStorage.setItem(STORE,JSON.stringify(project)); }
    catch (_) { message('Le stockage du navigateur est plein. Enregistrez ou exportez votre projet.','error'); }
    $('#save-status').textContent = dirty ? 'Modifications conservées sur cet appareil' : 'Enregistré sur cet appareil';
    $('#save-status').classList.toggle('dirty-indicator',dirty);
  }
  function remember() { history.push(clone(project)); if(history.length>80)history.shift(); future=[]; }
  function commit(change, options={}) {
    if(options.history!==false)remember();
    change(project); dirty=true; persist();
    renderAll(options.properties!==false);scheduleNativePreview();
  }
  function undo() { if(!history.length)return; future.push(clone(project)); project=history.pop(); if(!nodeById(selectedId))selectedId=project.nodes[0]?.id||null; dirty=true;persist();renderAll(); }
  function redo() { if(!future.length)return; history.push(clone(project));project=future.pop();if(!nodeById(selectedId))selectedId=project.nodes[0]?.id||null;dirty=true;persist();renderAll(); }
  function defaults(className) {
    const properties={}; for(const [name,def] of Object.entries(schema.classes[className]?.properties||{}))if('default' in def&&!def.omitOnCreate)properties[name]=clone(def.default);
    return properties;
  }
  function makeNode(className,parent=null,name) { return {id:uid(className),class:className,name:name||className,parent,properties:defaults(className),...(TIMED_CLASSES.includes(className)?{timing:{start:0,duration:className==='ParticleEmitter'?0.3:1,mode:className==='ParticleEmitter'?'burst':'continuous',count:30}}:{})}; }
  function setKnown(node, values) { for(const [key,value] of Object.entries(values)){const def=schema.classes[node.class]?.properties?.[key];if(def)node.properties[key]=['NumberSequence','ColorSequence'].includes(def.type)?sequenceArray(pointsOf(value,def.type),def.type):clone(value);} return node; }
  function compatibleParent(className, parentNode) {
    if(!parentNode)return !['Attachment','ParticleEmitter','Beam','Trail','SpecialMesh','PointLight','SpotLight','SurfaceLight'].includes(className);
    if(['Folder','Model'].includes(className))return ['Folder','Model'].includes(parentNode.class);
    if(['Part','MeshPart'].includes(className))return ['Folder','Model'].includes(parentNode.class);
    if(className==='SpecialMesh')return parentNode.class==='Part';
    if(className==='Attachment')return ['Part','MeshPart','Attachment'].includes(parentNode.class);
    if(['ParticleEmitter','Beam','Trail','PointLight','SpotLight','SurfaceLight'].includes(className))return ['Part','MeshPart','Attachment'].includes(parentNode.class);
    return true;
  }
  function supportFor(nodes, wanted='Part') {
    let parent=selected();
    if(parent?.class==='Attachment'&&wanted==='Part')parent=nodeById(parent.parent);
    if(parent?.class===wanted)return parent;
    let cursor=parent; const visited=new Set();
    while(cursor&&!visited.has(cursor.id)){visited.add(cursor.id);if(cursor.class===wanted)return cursor;cursor=nodeById(cursor.parent);}
    const support=makeNode('Part',null,'Source'); setKnown(support,{Transparency:1,Anchored:true,CanCollide:false});nodes.push(support);return support;
  }
  function addNode(className) {
    if(!schema.classes[className])return message('Cette classe n’est pas disponible dans le schéma du serveur.','error');
    commit(p=>{
      let parent=selected(); const additions=[];
      if(!compatibleParent(className,parent)) {
        parent=null;
        if(['Attachment','SpecialMesh','ParticleEmitter','Beam','Trail','PointLight','SpotLight','SurfaceLight'].includes(className))parent=supportFor(additions);
      }
      const node=makeNode(className,parent?.id||null);
      if(className==='Beam'||className==='Trail') {
        const part=parent?.class==='Attachment'?nodeById(parent.parent):parent;
        const first=makeNode('Attachment',part.id,'Départ'); const second=makeNode('Attachment',part.id,'Arrivée');
        setKnown(first,{Position:[-2,0,0]});setKnown(second,{Position:[2,0,0]});additions.push(first,second);
        setKnown(node,{Attachment0:first.id,Attachment1:second.id});
      }
      if(className==='MeshPart')node.properties.Transparency=0;
      if(className==='SpecialMesh'&&parent?.properties.Transparency===1)parent.properties.Transparency=0;
      if(node.timing)node.timing.duration=Math.min(node.timing.duration,Math.max(0.01,p.duration));
      additions.push(node);p.nodes.push(...additions);selectedId=node.id;
    });
  }
  function selectNode(id) { selectedId=id;renderTree();renderProperties();renderTimeline();drawScene(); }
  function removeNode() {
    if(!selected())return;
    const remove=new Set([selectedId]);let changed=true;
    while(changed){changed=false;for(const n of project.nodes)if(remove.has(n.parent)&&!remove.has(n.id)){remove.add(n.id);changed=true;}}
    commit(p=>{p.nodes=p.nodes.filter(n=>!remove.has(n.id));p.animations=(p.animations||[]).filter(a=>!remove.has(a.node));for(const n of p.nodes)for(const [key,def] of Object.entries(schema.classes[n.class]?.properties||{}))if(def.type==='reference'&&remove.has(n.properties[key]))n.properties[key]=null;selectedId=p.nodes[0]?.id||null;});
  }
  function duplicateNode() {
    const source=selected();if(!source)return;
    commit(p=>{const originals=[source];let i=0;while(i<originals.length){const n=originals[i++];for(const child of p.nodes.filter(c=>c.parent===n.id))if(!originals.includes(child))originals.push(child);}
      const map=new Map(originals.map(n=>[n.id,uid(n.class)]));const copies=originals.map(n=>{const copy=clone(n);copy.id=map.get(n.id);copy.parent=map.get(n.parent)||n.parent;copy.name=n===source?n.name+' copie':n.name;for(const [key,def] of Object.entries(schema.classes[n.class]?.properties||{}))if(def.type==='reference'&&map.has(copy.properties[key]))copy.properties[key]=map.get(copy.properties[key]);return copy;});
      p.nodes.push(...copies);p.animations.push(...p.animations.filter(a=>map.has(a.node)).map(a=>({...clone(a),node:map.get(a.node)})));selectedId=copies[0].id;
    });
  }
  function template(kind) {
    const p=emptyProject();
    if(kind==='empty') { p.name='Nouvel effet';return p; }
    const source=makeNode('Part',null,'Source');setKnown(source,{Size:[2,1,2],Transparency:1,Position:[0,1,0],Anchored:true,CanCollide:false});p.nodes.push(source);
    if(kind==='impact'||kind==='smoke') {
      p.name=kind==='impact'?'Impact lumineux':'Fumée ascendante';
      const attachment=makeNode('Attachment',source.id,'Origine');p.nodes.push(attachment);
      const emitter=makeNode('ParticleEmitter',attachment.id,kind==='impact'?'Étincelles':'Fumée');
      setKnown(emitter,kind==='impact'?{Texture:'rbxasset://textures/particles/sparkles_main.dds',Color:[[0,[0.55,0.95,1]],[1,[0.72,0.5,1]]],Size:[[0,0.35,0],[0.25,0.55,0],[1,0,0]],Transparency:[[0,0,0],[0.65,0.15,0],[1,1,0]],Lifetime:[0.35,0.8],Speed:[5,12],SpreadAngle:[180,180],Drag:3,LightEmission:1,Rate:0}: {Texture:'rbxasset://textures/particles/smoke_main.dds',Color:[[0,[0.68,0.65,0.74]],[1,[0.35,0.31,0.42]]],Size:[[0,0.6,0.15],[1,3.5,0.7]],Transparency:[[0,0.5,0],[0.3,0.65,0],[1,1,0]],Lifetime:[1.2,2],Speed:[1,2],SpreadAngle:[12,12],Acceleration:[0,2,0],Rate:15});
      emitter.timing={start:0,duration:kind==='impact'?0.1:1.5,mode:kind==='impact'?'burst':'continuous',count:35};p.nodes.push(emitter);p.duration=kind==='impact'?2:4;
      if(kind==='impact'&&schema.classes.PointLight){const light=makeNode('PointLight',attachment.id,'Éclair');setKnown(light,{Color:[0.55,0.95,1],Range:12,Brightness:3});light.timing={start:0,duration:0.12};p.nodes.push(light);}
    } else {
      p.name=kind==='beam'?'Arc lumineux':'Traînée en mouvement';
      const a=makeNode('Attachment',source.id,'Départ');const b=makeNode('Attachment',source.id,'Arrivée');setKnown(a,{Position:kind==='beam'?[-3,0,0]:[0,0.6,0]});setKnown(b,{Position:kind==='beam'?[3,0,0]:[0,-0.6,0]});p.nodes.push(a,b);
      const fx=makeNode(kind==='beam'?'Beam':'Trail',source.id,kind==='beam'?'Arc':'Ruban');setKnown(fx,{Attachment0:a.id,Attachment1:b.id,Color:[[0,[0.55,0.95,0.88]],[1,[0.65,0.45,1]]],Transparency:[[0,0,0],[1,kind==='beam'?0:1,0]],Width0:0.45,Width1:0.15,LightEmission:1,FaceCamera:true,CurveSize0:2,CurveSize1:-2,Lifetime:0.55});fx.timing={start:0,duration:kind==='beam'?p.duration:2,mode:'continuous'};p.nodes.push(fx);
      if(kind==='trail')p.animations=[{node:source.id,property:'Position',keyframes:[{time:0,value:[-4,1,0]},{time:1,value:[0,3,0]},{time:2,value:[4,1,0]}]}];
    }
    return p;
  }
  function useTemplate(kind) {
    if(project.nodes.length&&dirty&&!confirm('Remplacer l’effet en cours ? Vos changements sont conservés seulement si vous enregistrez le projet avant.'))return;
    remember();project=template(kind);selectedId=project.nodes.find(n=>n.class==='ParticleEmitter'||n.class==='Beam'||n.class==='Trail')?.id||project.nodes[0]?.id||null;dirty=true;time=0;persist();renderAll();$('#projects-dialog').close();message('Modèle prêt. Modifiez les propriétés, puis lancez l’aperçu dans Studio.');
  }
  function renderAll(properties=true) {
    $('#project-name').value=project.name;$('#composition-name').textContent=project.name;
    $('#duration').value=project.duration;$('#loop').checked=!!project.loop;$('#playhead-time').max=project.duration;$('#playhead-time').value=round(time);
    $('#node-count').textContent=project.nodes.length+' objets';$('#scene-empty').classList.toggle('hidden',!!project.nodes.length||viewportMode!=='plan');
    $('#undo-button').disabled=!history.length;$('#redo-button').disabled=!future.length;
    $('#clone-button').disabled=!selected();$('#delete-button').disabled=!selected();
    renderTree();if(properties)renderProperties();renderTimeline();drawScene();
  }
  function renderTree() {
    const tree=$('#node-tree');tree.replaceChildren();
    if(!project.nodes.length){tree.innerHTML='<div class="inspector-empty"><p>Ajoutez un objet ou choisissez un modèle.</p></div>';return;}
    const visited=new Set();
    function append(node,depth){if(visited.has(node.id))return;visited.add(node.id);const row=document.createElement('div');row.className='tree-node'+(node.id===selectedId?' selected':'');row.dataset.class=node.class;row.setAttribute('role','treeitem');row.setAttribute('aria-selected',node.id===selectedId);row.setAttribute('aria-level',depth+1);row.tabIndex=0;row.style.paddingLeft=(7+depth*15)+'px';row.innerHTML=`<span class="node-icon">${ICONS[node.class]||'◇'}</span><span class="node-name">${escape(node.name||node.class)}</span><span class="node-type">${escape(node.class)}</span>`;row.onclick=()=>selectNode(node.id);row.onkeydown=e=>{if(e.key==='Enter')selectNode(node.id);};tree.append(row);for(const child of project.nodes.filter(n=>n.parent===node.id))append(child,depth+1);}
    for(const node of project.nodes.filter(n=>!n.parent||!nodeById(n.parent)))append(node,0);for(const node of project.nodes)if(!visited.has(node.id))append(node,0);
  }

  // All property controls are generated from the live Roblox schema.
  function fieldLabel(name) { return name.replace(/([a-z0-9])([A-Z])/g,'$1 $2'); }
  function rowFor(name,control) {const row=document.createElement('div');row.className='property-row';const label=document.createElement('label');label.textContent=fieldLabel(name);label.title=name;label.htmlFor=control.id||(control.id='field-'+uid('control'));row.append(label,control);return row;}
  function propertyValue(node,key,def) {return key in node.properties ? node.properties[key] : def.default;}
  function colorHex(value) {const c=Array.isArray(value)?value:[1,1,1];return '#'+c.slice(0,3).map(x=>Math.round(bounded(num(x,1),0,1)*255).toString(16).padStart(2,'0')).join('');}
  function hexColor(hex) {const value=hex.replace('#','');if(!/^[a-f\d]{6}$/i.test(value))throw new Error('Couleur attendue : #RRGGBB');return [0,2,4].map(i=>parseInt(value.slice(i,i+2),16)/255);}
  function pointsOf(value,type) {return (Array.isArray(value)?value:[]).map(p=>Array.isArray(p)?{time:p[0],value:clone(p[1]),envelope:p[2]||0}:{time:p.time,value:clone(p.value),envelope:p.envelope||0}).sort((a,b)=>a.time-b.time);}
  function sequenceArray(points,type) {return points.map(p=>type==='ColorSequence'?{time:round(num(p.time)),value:p.value}:{time:round(num(p.time)),value:num(p.value),envelope:Math.max(0,num(p.envelope))});}
  function sequenceGradient(value) {return 'linear-gradient(90deg,'+pointsOf(value,'ColorSequence').map(p=>colorHex(p.value)+' '+p.time*100+'%').join(',')+')';}
  function updateProperty(id,key,value){commit(()=>{const node=nodeById(id);node.properties[key]=value;if(node.class==='Attachment'){if(key==='Orientation'){delete node.properties.Axis;delete node.properties.SecondaryAxis;}if(key==='Axis'||key==='SecondaryAxis')delete node.properties.Orientation;}},{properties:false});}
  function makeControl(node,key,def) {
    const value=propertyValue(node,key,def);const type=def.type;let control;
    if(type==='boolean') {control=document.createElement('input');control.type='checkbox';control.checked=!!value;control.onchange=()=>updateProperty(node.id,key,control.checked);}
    else if(['number','integer'].includes(type)){control=document.createElement('input');control.type='number';control.step=type==='integer'?'1':(def.step||'any');if(def.min!==undefined)control.min=def.min;if(def.max!==undefined)control.max=def.max;control.value=value??0;control.onchange=()=>{const v=Number(control.value);if(!Number.isFinite(v)||(type==='integer'&&!Number.isInteger(v))||(def.min!==undefined&&v<def.min)||(def.max!==undefined&&v>def.max)){control.value=value??0;message(`${key} : valeur hors limites.`, 'error');return;}updateProperty(node.id,key,v);};}
    else if(type==='enum'){control=document.createElement('select');const values=def.enum||def.values||[];for(const item of values){const option=document.createElement('option');option.value=typeof item==='object'?(item.value??item.name):item;option.textContent=typeof item==='object'?(item.label??item.name??item.value):item;control.append(option);}if(value!==undefined&&!values.includes(value)){const option=new Option(String(value),String(value));control.append(option);}control.value=value;control.onchange=()=>updateProperty(node.id,key,control.value);}
    else if(type==='reference'){control=document.createElement('select');control.append(new Option('Aucun', ''));for(const n of project.nodes.filter(n=>n.class==='Attachment'))control.append(new Option(n.name+' · '+(nodeById(n.parent)?.name||'racine'),n.id));if(value&&!nodeById(value))control.append(new Option('Introuvable : '+value,value));control.value=value||'';control.onchange=()=>updateProperty(node.id,key,control.value||null);}
    else if(type==='Vector3'||type==='Vector2'||type==='NumberRange'){control=document.createElement('div');control.className='vector-inputs';const length=type==='Vector3'?3:2;const labels=type==='NumberRange'?['↓','↑']:['X','Y','Z'];for(let i=0;i<length;i++){const wrap=document.createElement('label');wrap.className='vector-component';const span=document.createElement('span');span.textContent=labels[i];const input=document.createElement('input');input.type='number';input.step='any';input.value=Array.isArray(value)?value[i]??0:0;input.setAttribute('aria-label',`${key} ${labels[i]}`);input.onchange=()=>{const values=$$('input',control).map(v=>Number(v.value));if(values.some(v=>!Number.isFinite(v))||(type==='NumberRange'&&values[0]>values[1])){input.value=Array.isArray(value)?value[i]:0;message(`${key} : les bornes doivent être numériques et ordonnées.`, 'error');return;}updateProperty(node.id,key,values);};wrap.append(span,input);control.append(wrap);}}
    else if(type==='Color3'){control=document.createElement('div');control.className='color-control';const picker=document.createElement('input');picker.type='color';picker.value=colorHex(value);const text=document.createElement('input');text.type='text';text.value=colorHex(value).toUpperCase();text.setAttribute('aria-label',key+' hexadécimal');picker.onchange=()=>{text.value=picker.value.toUpperCase();updateProperty(node.id,key,hexColor(picker.value));};text.onchange=()=>{try{const color=hexColor(text.value);picker.value=colorHex(color);updateProperty(node.id,key,color);}catch(e){message(e.message,'error');text.value=picker.value;}};control.append(picker,text);}
    else if(type==='NumberSequence'||type==='ColorSequence'){control=document.createElement('button');control.className='sequence-button';control.type='button';const points=pointsOf(value,type);if(type==='ColorSequence')control.innerHTML=`<span class="sequence-swatch" style="background:${escape(sequenceGradient(value))}"></span><span>${points.length} points</span><span>↗</span>`;else{const max=Math.max(1,...points.map(p=>num(p.value)));const path=points.map((p,i)=>(i?'L':'M')+(p.time*44+1)+' '+(18-(num(p.value)/max)*15)).join(' ');control.innerHTML=`<svg class="sequence-sparkline" viewBox="0 0 47 20"><path d="${path}" fill="none" stroke="#a690e1" stroke-width="1.3"/></svg><span>${points.length} points</span><span>↗</span>`;}control.onclick=()=>openSequence(node,key,type,value);}
    else if(type==='string'||type==='content'){control=document.createElement('input');control.type='text';control.value=value??'';if(type==='content'){control.placeholder='rbxassetid://…';control.title='ID Roblox ou URI de ressource';}control.onchange=()=>{let v=control.value.trim();if(type==='content'&&/^\d+$/.test(v))v='rbxassetid://'+v;control.value=v;updateProperty(node.id,key,v);};}
    else {control=document.createElement('button');control.type='button';control.className='sequence-button';control.textContent='Modifier le JSON ↗';control.onclick=()=>{const text=prompt(`${key} (${type}) — valeur JSON`,JSON.stringify(value??null));if(text===null)return;try{updateProperty(node.id,key,JSON.parse(text));renderProperties();}catch(e){message(e.message,'error');}};}
    control.dataset.property=key;return control;
  }
  function renderProperties() {
    const host=$('#properties');host.replaceChildren();const node=selected();$('#selected-class').textContent=node?.class||'Aucun objet';
    if(!node){host.innerHTML='<div class="inspector-empty"><span>◈</span><p>Sélectionnez un objet pour ajuster ses propriétés.</p></div>';return;}
    const name=document.createElement('input');name.className='node-name-input';name.value=node.name||node.class;name.setAttribute('aria-label','Nom de l’objet');name.onchange=()=>commit(()=>{node.name=name.value.trim()||node.class;},{properties:false});host.append(name);
    const parent=document.createElement('select');parent.append(new Option('Racine de l’effet',''));const descendants=new Set([node.id]);let before=-1;while(before!==descendants.size){before=descendants.size;for(const n of project.nodes)if(descendants.has(n.parent))descendants.add(n.id);}for(const n of project.nodes)if(!descendants.has(n.id)&&compatibleParent(node.class,n))parent.append(new Option(n.name+' · '+n.class,n.id));if(node.parent&&!Array.from(parent.options).some(o=>o.value===node.parent))parent.append(new Option((nodeById(node.parent)?.name||node.parent)+' (parent actuel)',node.parent));parent.value=node.parent||'';parent.onchange=()=>{if(!compatibleParent(node.class,nodeById(parent.value))){parent.value=node.parent||'';return message('Ce type d’objet nécessite un parent compatible.','error');}commit(()=>{node.parent=parent.value||null;},{properties:false});};host.append(rowFor('Parent',parent));
    if(node.class==='ParticleEmitter'){const note=document.createElement('p');note.className='inline-note';note.textContent=nodeById(node.parent)?.class==='Attachment'?'Émission depuis le point Attachment, selon son orientation.':'Émission dans le volume du Part, selon Shape et ShapeStyle.';host.append(note);}
    if(TIMED_CLASSES.includes(node.class))host.append(timingControls(node));
    const search=document.createElement('input');search.className='property-search';search.placeholder='Filtrer les propriétés…';search.setAttribute('aria-label','Filtrer les propriétés');host.append(search);
    const entries=Object.entries(schema.classes[node.class]?.properties||{});const used=new Set();const groups=[];
    for(const [title,keys] of GROUPS){const fields=entries.filter(([key])=>keys.includes(key)&&!used.has(key));if(fields.length){fields.forEach(([key])=>used.add(key));groups.push([title,fields]);}}
    const rest=entries.filter(([key])=>!used.has(key));if(rest.length)groups.push(['Autres propriétés',rest]);
    for(const [title,fields] of groups){const details=document.createElement('details');details.className='property-group';details.open=true;const summary=document.createElement('summary');summary.textContent=title;details.append(summary);for(const [key,def] of fields)details.append(rowFor(key,makeControl(node,key,def)));host.append(details);}
    search.oninput=()=>{const q=search.value.toLowerCase();for(const group of $$('.property-group',host)){let any=false;for(const row of $$('.property-row',group)){const show=row.textContent.toLowerCase().includes(q)||($('[data-property]',row)?.dataset.property||'').toLowerCase().includes(q);row.classList.toggle('hidden',!show);any||=show;}group.classList.toggle('hidden',!any);if(q)group.open=true;}};
    const animation=document.createElement('button');animation.className='secondary';animation.textContent='◇ Animer une propriété';animation.style.marginTop='14px';animation.onclick=()=>openAnimation(node);host.append(animation);
    const advanced=document.createElement('details');advanced.className='property-group';const summary=document.createElement('summary');summary.textContent='Propriétés JSON avancées';const area=document.createElement('textarea');area.className='advanced-property-json';area.spellcheck=false;area.value=JSON.stringify(node.properties,null,2);area.setAttribute('aria-label','Toutes les propriétés de cet objet au format JSON');const note=document.createElement('p');note.className='inline-note';note.textContent='Toutes les propriétés sont conservées. Le serveur vérifie leur compatibilité avec Roblox à l’enregistrement.';const apply=document.createElement('button');apply.className='secondary';apply.textContent='Appliquer les propriétés';apply.onclick=()=>{try{const values=JSON.parse(area.value);if(!values||Array.isArray(values)||typeof values!=='object')throw new Error('Un objet JSON est attendu.');commit(()=>{node.properties=values;});}catch(e){message(e.message,'error');}};advanced.append(summary,area,note,apply);host.append(advanced);
    const id=document.createElement('p');id.className='inline-note';id.textContent='ID : '+node.id;host.append(id);
  }
  function timingControls(node) {
    const box=document.createElement('details');box.className='property-group';box.open=true;box.innerHTML='<summary>Déclenchement</summary>';const timing=node.timing||{start:0,duration:1,mode:'continuous'};
    for(const [key,label] of [['start','Début (s)'],['duration','Durée (s)']]){const input=document.createElement('input');input.type='number';input.min='0';input.max=project.duration;input.step='0.05';input.value=timing[key]??0;input.onchange=()=>{const value=Number(input.value);const next={...(node.timing||timing),[key]:value};if(!Number.isFinite(value)||value<0||next.start+next.duration>project.duration+1e-9){input.value=node.timing?.[key]??timing[key];message('La plage doit rester dans la durée du projet.','error');return;}commit(()=>{node.timing=next;},{properties:false});};box.append(rowFor(label,input));}
    if(node.class==='ParticleEmitter'){const mode=document.createElement('div');mode.className='timing-mode';for(const [key,label]of[['burst','Émission unique'],['continuous','Continue']]){const b=document.createElement('button');b.textContent=label;b.classList.toggle('active',(timing.mode||'burst')===key);b.onclick=()=>commit(()=>{node.timing={...(node.timing||timing),mode:key};});mode.append(b);}box.append(mode);if((timing.mode||'burst')==='burst'){const count=document.createElement('input');count.type='number';count.min='0';count.step='1';count.value=timing.count??30;count.onchange=()=>{if(!Number.isInteger(Number(count.value))||Number(count.value)<0)return;commit(()=>{node.timing={...(node.timing||timing),count:Number(count.value)};},{properties:false});};box.append(rowFor('Quantité',count));}}
    return box;
  }

  function openSequence(node,key,type,value) {
    if(window.DatakyCurves){const curveKey=node.id+'::'+key;window.DatakyCurves.open({type,value,definition:schema.classes[node.class]?.properties[key],editor:project.editor?.curves?.[curveKey],title:key,onApply:result=>{commit(p=>{node.properties[key]=result.value;p.editor??={version:1,curves:{}};p.editor.curves??={};p.editor.curves[curveKey]=result.editor;});}});return;}
    let points=pointsOf(value,type);if(points.length<2)points=[{time:0,value:type==='ColorSequence'?[1,1,1]:1,envelope:0},{time:1,value:type==='ColorSequence'?[1,1,1]:1,envelope:0}];
    sequenceEdit={node:node.id,key,type,points};$('#sequence-title').textContent=key+(type==='ColorSequence'?' · Couleurs':' · Courbe');$('#sequence-error').textContent='';renderSequenceEditor();$('#sequence-dialog').showModal();
  }
  function renderSequenceEditor() {
    const {points,type}=sequenceEdit;const host=$('#sequence-points');host.replaceChildren();
    points.forEach((point,index)=>{const row=document.createElement('div');row.className='sequence-point';const tlabel=document.createElement('label');tlabel.textContent='Temps';const t=document.createElement('input');t.type='number';t.min='0';t.max='1';t.step='0.01';t.value=point.time;t.disabled=index===0||index===points.length-1;t.oninput=()=>{point.time=Number(t.value);drawSequence();};tlabel.append(t);row.append(tlabel);const vlabel=document.createElement('label');vlabel.textContent=type==='ColorSequence'?'Couleur':'Valeur';const v=document.createElement('input');v.type=type==='ColorSequence'?'color':'number';if(type==='ColorSequence')v.value=colorHex(point.value);else{v.value=point.value;v.step='any';}v.oninput=()=>{point.value=type==='ColorSequence'?hexColor(v.value):Number(v.value);drawSequence();};vlabel.append(v);row.append(vlabel);if(type!=='ColorSequence'){const elabel=document.createElement('label');elabel.className='envelope-control';elabel.textContent='Aléa ±';const e=document.createElement('input');e.type='number';e.min='0';e.step='any';e.value=point.envelope||0;e.oninput=()=>{point.envelope=Number(e.value);drawSequence();};elabel.append(e);row.append(elabel);}const remove=document.createElement('button');remove.className='icon-button danger';remove.textContent='×';remove.title='Supprimer ce point';remove.disabled=index===0||index===points.length-1;remove.onclick=()=>{points.splice(index,1);renderSequenceEditor();};row.append(remove);host.append(row);});drawSequence();
  }
  function drawSequence() {
    if(!sequenceEdit)return;const canvas=$('#sequence-canvas');const ctx=canvas.getContext('2d');if(!ctx)return;const w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#15111c';ctx.fillRect(0,0,w,h);const points=[...sequenceEdit.points].sort((a,b)=>a.time-b.time);
    if(sequenceEdit.type==='ColorSequence'){const gradient=ctx.createLinearGradient(30,0,w-30,0);for(const p of points)gradient.addColorStop(bounded(num(p.time),0,1),colorHex(p.value));ctx.fillStyle=gradient;ctx.fillRect(30,32,w-60,90);for(const p of points){ctx.beginPath();ctx.fillStyle=colorHex(p.value);ctx.strokeStyle='#eeeaf3';ctx.arc(30+bounded(num(p.time),0,1)*(w-60),132,5,0,Math.PI*2);ctx.fill();ctx.stroke();}}
    else {const min=Math.min(0,...points.map(p=>num(p.value)-num(p.envelope)));const max=Math.max(1,...points.map(p=>num(p.value)+num(p.envelope)));const x=p=>30+bounded(num(p.time),0,1)*(w-60),y=v=>h-28-(v-min)/(max-min)*(h-54);ctx.strokeStyle='#342c40';ctx.lineWidth=1;for(let i=0;i<=4;i++){ctx.beginPath();ctx.moveTo(30,y(min+(max-min)*i/4));ctx.lineTo(w-30,y(min+(max-min)*i/4));ctx.stroke();}ctx.fillStyle='#a690e125';ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(p),y(num(p.value)+num(p.envelope))):ctx.moveTo(x(p),y(num(p.value)+num(p.envelope))));[...points].reverse().forEach(p=>ctx.lineTo(x(p),y(num(p.value)-num(p.envelope))));ctx.closePath();ctx.fill();ctx.strokeStyle='#b49aeb';ctx.lineWidth=2;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(p),y(num(p.value))):ctx.moveTo(x(p),y(num(p.value))));ctx.stroke();for(const p of points){ctx.beginPath();ctx.fillStyle='#d6c8ed';ctx.arc(x(p),y(num(p.value)),4,0,Math.PI*2);ctx.fill();}}
    ctx.font='10px monospace';ctx.fillStyle='#877994';ctx.textAlign='left';ctx.fillText('0 · naissance',30,h-8);ctx.textAlign='right';ctx.fillText('1 · fin de vie',w-30,h-8);
  }
  function validateSequence() {
    const {points,type}=sequenceEdit;const sorted=[...points].sort((a,b)=>a.time-b.time);if(sorted.length<2||sorted.length>20)throw new Error('Une courbe contient de 2 à 20 points.');if(sorted[0].time!==0||sorted.at(-1).time!==1)throw new Error('Les points de début et de fin doivent être à 0 et 1.');for(let i=0;i<sorted.length;i++){const p=sorted[i];if(!Number.isFinite(p.time)||p.time<0||p.time>1||(i&&p.time<=sorted[i-1].time))throw new Error('Les temps doivent être distincts et compris entre 0 et 1.');if(type==='ColorSequence'){if(!Array.isArray(p.value)||p.value.length!==3||p.value.some(v=>!Number.isFinite(v)||v<0||v>1))throw new Error('Chaque couleur doit contenir trois valeurs de 0 à 1.');}else if(!Number.isFinite(p.value)||!Number.isFinite(p.envelope)||p.envelope<0)throw new Error('Les valeurs doivent être numériques et l’aléa positif.');}return sorted;
  }
  function openAnimation(node) {
    animationNode=node.id;const select=$('#animation-property');select.replaceChildren();for(const [key,def]of Object.entries(schema.classes[node.class]?.properties||{}))if(def.animatable!==false&&['number','integer','Vector2','Vector3','Color3','NumberRange','boolean','enum'].includes(def.type))select.append(new Option(fieldLabel(key),key));if(!select.options.length)return message('Cette classe ne propose pas de propriété animable.');const existing=project.animations.find(a=>a.node===node.id);if(existing&&Array.from(select.options).some(o=>o.value===existing.property))select.value=existing.property;select.onchange=()=>loadAnimationKeyframes();loadAnimationKeyframes();$('#animation-error').textContent='';$('#animation-dialog').showModal();
  }
  function loadAnimationKeyframes() {
    const property=$('#animation-property').value;const existing=project.animations.find(a=>a.node===animationNode&&a.property===property);const node=nodeById(animationNode);const value=node.properties[property]??schema.classes[node.class].properties[property].default;$('#animation-json').value=JSON.stringify(existing?.keyframes||[{time:0,value:clone(value)},{time:Math.min(2,project.duration),value:clone(value)}],null,2);$('#animation-remove').disabled=!existing;
  }

  function catalogPath(record,kind) {
    let path=record.preview_path||record.image_path||'';if(!path)return '';
    path=path.replaceAll('\\','/');if(/^(https?:|data:)/.test(path))return path;
    if(path.startsWith('/library/'))return path;if(path.startsWith('/'))return path;
    if(kind!=='textures'&&!path.startsWith(kind+'/'))path=kind+'/'+path;
    return '/library/'+path.split('/').map(encodeURIComponent).join('/');
  }
  function assetUri(record) {return record.uri||record.raw_uri||record.asset_uri||(record.asset_id?'rbxassetid://'+record.asset_id:'');}
  function renderCatalog(refreshTags=false) {
    const state=filters[collection];const records=catalog[collection]||[];
    $$('[data-collection]').forEach(button=>{const active=button.dataset.collection===collection;button.classList.toggle('active',active);button.setAttribute('aria-selected',active);});
    $('#catalog-search').value=state.search;
    if(refreshTags){const tags=[...new Set(records.flatMap(r=>r.tags||[]))].sort((a,b)=>a.localeCompare(b));$('#catalog-tag').replaceChildren(new Option('Tous les tags',''));for(const tag of tags)$('#catalog-tag').append(new Option(tag,tag));}
    $('#catalog-tag').value=state.tag;const search=state.search.toLocaleLowerCase();const filtered=records.filter(r=>(!state.tag||(r.tags||[]).includes(state.tag))&&(!search||(String(r.name||'')+' '+String(r.asset_id||'')+' '+(r.tags||[]).join(' ')).toLocaleLowerCase().includes(search)));
    const pageSize=36;const pages=Math.max(1,Math.ceil(filtered.length/pageSize));state.page=bounded(state.page,0,pages-1);const rows=filtered.slice(state.page*pageSize,(state.page+1)*pageSize);$('#catalog-count').textContent=numberFormat.format(filtered.length);$('#catalog-page').textContent=catalogLoaded?`${state.page+1} / ${pages}`:catalogFailed?'Catalogue indisponible':'Chargement…';$('#catalog-prev').disabled=!state.page;$('#catalog-next').disabled=state.page>=pages-1;
    const grid=$('#catalog-grid');grid.replaceChildren();
    if(!rows.length){grid.innerHTML=`<div class="empty-message">${catalogLoaded?'Aucune ressource pour ce filtre.':catalogFailed?'La bibliothèque est indisponible. Les modèles intégrés restent utilisables.':'Chargement de votre bibliothèque…'}</div>`;return;}
    for(const record of rows){const button=document.createElement('button');button.className='catalog-card'+(assetSelection?.record===record?' selected':'');button.title=`${record.name||'Ressource'}\n${record.asset_id||assetUri(record)}`;button.draggable=true;const path=catalogPath(record,collection);if(path){const image=document.createElement('img');image.loading='lazy';image.alt=record.name||'Aperçu';image.src=path;image.onerror=()=>{image.remove();const missing=document.createElement('span');missing.className='missing-image';missing.textContent='◇';button.prepend(missing);};button.append(image);}else{const missing=document.createElement('span');missing.className='missing-image';missing.textContent='◇';button.append(missing);}const name=document.createElement('span');name.textContent=record.name||record.asset_id||'Ressource';button.append(name);button.onclick=()=>{assetSelection={record,kind:collection};renderCatalog();renderResourceDetail();};button.ondblclick=()=>applyAsset(record,collection);button.ondragstart=e=>{assetSelection={record,kind:collection};e.dataTransfer.setData('application/x-dataky-asset',JSON.stringify({kind:collection,record}));e.dataTransfer.setData('text/plain',assetUri(record));e.dataTransfer.effectAllowed='copy';renderResourceDetail();};grid.append(button);}
  }
  function renderResourceDetail() {
    const host=$('#resource-detail');if(!assetSelection){host.innerHTML='<span class="mini-label">RESSOURCE</span><p>Sélectionnez une image pour l’utiliser dans votre effet.</p>';return;}
    const {record,kind}=assetSelection;host.innerHTML=`<span class="mini-label">${escape(COLLECTION_LABELS[kind].toUpperCase())}</span><div class="resource-name" title="${escape(record.name)}">${escape(record.name||'Ressource')}</div><div class="resource-id">${escape(record.asset_id||assetUri(record))}</div><div class="resource-buttons"><button class="primary" id="use-resource">Utiliser</button><button class="secondary" id="copy-resource">Copier l’ID</button></div>`;
    $('#use-resource').onclick=()=>applyAsset(record,kind);$('#copy-resource').onclick=()=>copyText(String(record.asset_id||assetUri(record)),'ID copié');
  }
  function applyAsset(record,kind,targetId=selectedId) {
    const uri=assetUri(record);if(!uri)return message('Cette ressource ne possède pas d’ID utilisable.','error');
    let target=nodeById(targetId);const property=target&&CONTENT_BY_CLASS[target.class];const compatible=kind==='meshes'?['SpecialMesh','MeshPart'].includes(target?.class):kind==='beams'?['Beam','Trail'].includes(target?.class):['ParticleEmitter','Beam','Trail'].includes(target?.class);
    if(compatible&&property&&schema.classes[target.class]?.properties?.[property]){
      commit(()=>{target.properties[property]=uri;selectedId=target.id;if(kind==='meshes'){if(target.class==='SpecialMesh')target.properties.MeshType='FileMesh';applyMeshTexture(target,record);}else if(target.class==='ParticleEmitter')applyFlipbook(target,record);});message('Ressource appliquée à '+target.name+'.');return;
    }
    const className=kind==='meshes'?'SpecialMesh':kind==='beams'?'Beam':'ParticleEmitter';addNode(className);target=selected();if(target){commit(()=>{const prop=CONTENT_BY_CLASS[className];target.properties[prop]=uri;target.name=record.name||target.name;if(kind==='meshes'){target.properties.MeshType='FileMesh';applyMeshTexture(target,record);const support=nodeById(target.parent);if(support&&support.properties.Transparency===1)support.properties.Transparency=0;}else if(className==='ParticleEmitter')applyFlipbook(target,record);});message(className+' créé avec cette ressource.');}
  }
  function applyFlipbook(node,record) {if(record.kind!=='flipbook'){if(record.kind==='static'&&'FlipbookLayout'in node.properties)node.properties.FlipbookLayout='None';return;}const grid=Number(record.grid);if([2,4,8].includes(grid)&&schema.classes.ParticleEmitter?.properties.FlipbookLayout){node.properties.FlipbookLayout='Grid'+grid+'x'+grid;message('Grille '+grid+'×'+grid+' appliquée. Vérifiez son estimation dans le catalogue.');}else message('Flipbook sélectionné : choisissez sa grille dans les propriétés.');}
  function applyMeshTexture(node,record) {const ref=(record.references||[]).find(r=>/texture/i.test(r.label||r.property||''));const key=node.class==='MeshPart'?'TextureID':'TextureId';if(ref&&schema.classes[node.class]?.properties?.[key])node.properties[key]=ref.uri||ref.raw_uri||(ref.asset_id?'rbxassetid://'+ref.asset_id:'');}

  function renderTimeline() {
    const host=$('#timeline');const scroll=host.scrollTop;host.replaceChildren();const duration=Math.max(0.1,num(project.duration,3));const tracks=project.nodes.filter(n=>TIMED_CLASSES.includes(n.class));$('#timeline-count').textContent=tracks.length+(project.animations?.length||0)+' pistes';
    const ruler=document.createElement('div');ruler.className='timeline-ruler';ruler.innerHTML='<div class="ruler-label">OBJET / PROPRIÉTÉ</div><div class="ruler-track"></div>';const rulerTrack=$('.ruler-track',ruler);const count=duration>20?5:10;for(let i=0;i<=count;i++){const tick=document.createElement('span');tick.className='ruler-tick';tick.style.left=(i/count*100)+'%';tick.textContent=round(duration*i/count);rulerTrack.append(tick);}rulerTrack.onpointerdown=e=>scrubAt(e,rulerTrack);host.append(ruler);
    for(const node of tracks){const timing=node.timing||{start:0,duration:1};const row=document.createElement('div');row.className='timeline-row'+(selectedId===node.id?' selected':'');row.innerHTML=`<div class="track-label"><span class="node-icon">${ICONS[node.class]||'◇'}</span><span>${escape(node.name)}</span></div><div class="track-surface"></div>`;$('.track-label',row).onclick=()=>selectNode(node.id);const surface=$('.track-surface',row);surface.onpointerdown=e=>{if(e.target===surface)scrubAt(e,surface);};const bar=document.createElement('div');bar.className='track-bar '+node.class.toLowerCase();bar.style.left=(num(timing.start)/duration*100)+'%';bar.style.width=(Math.min(num(timing.duration,1),Math.max(0,duration-num(timing.start)))/duration*100)+'%';bar.textContent=node.class==='ParticleEmitter'&&timing.mode==='burst'?'✦ '+(timing.count??30):round(num(timing.duration,1))+' s';bar.title=`Début ${timing.start||0} s · Durée ${timing.duration??1} s`;const handle=document.createElement('span');handle.className='bar-handle';bar.append(handle);bar.onpointerdown=e=>startBarDrag(e,node,surface,e.target===handle);bar.ondblclick=()=>selectNode(node.id);surface.append(bar);host.append(row);}
    for(const [index,animation]of (project.animations||[]).entries()){const node=nodeById(animation.node);if(!node)continue;const row=document.createElement('div');row.className='timeline-row'+(selectedId===node.id?' selected':'');row.innerHTML=`<div class="track-label"><span class="node-icon">◇</span><span>${escape(node.name)} · ${escape(animation.property)}</span></div><div class="track-surface"></div>`;$('.track-label',row).onclick=()=>{selectNode(node.id);openAnimation(node);$('#animation-property').value=animation.property;loadAnimationKeyframes();};const surface=$('.track-surface',row);surface.onpointerdown=e=>scrubAt(e,surface);const frames=animation.keyframes||[];const start=frames[0]?.time||0;const end=frames.at(-1)?.time||duration;const bar=document.createElement('div');bar.className='track-bar animation';bar.style.left=(start/duration*100)+'%';bar.style.width=((end-start)/duration*100)+'%';bar.innerHTML=frames.map(f=>`<span style="position:absolute;left:${(f.time-start)/(end-start||1)*95}%;font-size:8px">◆</span>`).join('');bar.onclick=()=>{openAnimation(node);$('#animation-property').value=animation.property;loadAnimationKeyframes();};surface.append(bar);host.append(row);}
    if(!tracks.length&&!project.animations?.length){const empty=document.createElement('div');empty.className='timeline-placeholder';empty.textContent='Les émetteurs, beams, trails et animations apparaissent ici.';host.append(empty);}
    const playhead=document.createElement('div');playhead.className='timeline-playhead';const labelWidth=parseFloat(getComputedStyle(ruler).gridTemplateColumns.split(' ')[0])||134;playhead.style.left=`calc(${labelWidth}px + (100% - ${labelWidth}px) * ${bounded(time/duration,0,1)})`;host.append(playhead);host.scrollTop=scroll;
  }
  function scrubAt(event,surface) {
    const rect=surface.getBoundingClientRect();time=round(bounded((event.clientX-rect.left)/rect.width,0,1)*project.duration);$('#playhead-time').value=time;renderTimeline();drawScene();
  }
  function startBarDrag(event,node,surface,resize) {
    event.preventDefault();event.stopPropagation();selectedId=node.id;const rect=surface.getBoundingClientRect();remember();const original=clone(node.timing||{start:0,duration:1});const startX=event.clientX;const id=node.id;const move=e=>{const delta=(e.clientX-startX)/rect.width*project.duration;const timing=resize?{...original,duration:round(Math.max(0.01,original.duration+delta))}:{...original,start:round(Math.max(0,original.start+delta))};nodeById(id).timing=timing;dirty=true;renderTimeline();drawScene();};const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);persist();renderAll();};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true});
  }

  // The canvas is a placement diagram; no particle or mesh render is simulated here.
  function rotateVector(v,orientation) {
    let [x,y,z]=v;const [rx,ry,rz]=(orientation||[0,0,0]).map(a=>num(a)*Math.PI/180);let yy=y*Math.cos(rx)-z*Math.sin(rx);let zz=y*Math.sin(rx)+z*Math.cos(rx);y=yy;z=zz;let xx=x*Math.cos(ry)+z*Math.sin(ry);zz=-x*Math.sin(ry)+z*Math.cos(ry);x=xx;z=zz;xx=x*Math.cos(rz)-y*Math.sin(rz);yy=x*Math.sin(rz)+y*Math.cos(rz);return [xx,yy,z];
  }
  function animatedProperty(node,key) {
    const animation=(project.animations||[]).find(a=>a.node===node.id&&a.property===key);const frames=animation?.keyframes;if(!frames?.length)return node.properties[key];if(time<=frames[0].time)return frames[0].value;if(time>=frames.at(-1).time)return frames.at(-1).value;for(let i=1;i<frames.length;i++)if(time<=frames[i].time){const a=frames[i-1],b=frames[i],t=(time-a.time)/(b.time-a.time);return Array.isArray(a.value)?a.value.map((v,j)=>v+(b.value[j]-v)*t):a.value+(b.value-a.value)*t;}return node.properties[key];
  }
  function worldPosition(node,visited=new Set()) {
    if(!node||visited.has(node.id))return [0,0,0];visited.add(node.id);const pos=animatedProperty(node,'Position')||[0,0,0];const parent=nodeById(node.parent);if(!parent)return pos;const base=worldPosition(parent,visited);const offset=rotateVector(pos,animatedProperty(parent,'Orientation'));return base.map((x,i)=>num(x)+num(offset[i]));
  }
  function projectPoint(point,w,h) {return [w/2+cameraPan[0]+(point[0]-point[2])*.866*planScale,h*.54+cameraPan[1]+(point[0]+point[2])*.35*planScale-point[1]*planScale];}
  function drawScene() {
    const canvas=$('#scene-canvas');const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);const ctx=canvas.getContext('2d');if(!ctx)return;ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;const toScreen=p=>projectPoint(p,w,h);ctx.clearRect(0,0,w,h);sceneHitTargets=[];
    for(let i=-20;i<=20;i++){ctx.strokeStyle=i===0?'#76618448':'#6f57751d';ctx.lineWidth=i===0?1:0.65;for(const axis of [0,1]){const a=toScreen(axis?[i,0,-20]:[-20,0,i]);const b=toScreen(axis?[i,0,20]:[20,0,i]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();}}
    const origin=toScreen([0,0,0]);for(const [v,c,label]of [[[2.3,0,0],'#b27d96','X'],[[0,2.3,0],'#8caf88','Y'],[[0,0,2.3],'#7198b4','Z']]){const p=toScreen(v);ctx.strokeStyle=c+'9c';ctx.beginPath();ctx.moveTo(...origin);ctx.lineTo(...p);ctx.stroke();ctx.fillStyle=c;ctx.font='9px monospace';ctx.fillText(label,p[0]+5,p[1]-3);}
    for(const animation of project.animations||[]){if(animation.property!=='Position')continue;const node=nodeById(animation.node);if(!node)continue;ctx.strokeStyle='#d18eb060';ctx.setLineDash([3,5]);ctx.beginPath();for(const [i,frame]of animation.keyframes.entries()){const parent=worldPosition(nodeById(node.parent));const pos=frame.value.map((v,j)=>v+parent[j]);const p=toScreen(pos);i?ctx.lineTo(...p):ctx.moveTo(...p);}ctx.stroke();ctx.setLineDash([]);}
    for(const node of project.nodes.filter(n=>['Part','MeshPart'].includes(n.class))){const pos=worldPosition(node);const size=animatedProperty(node,'Size')||[2,1,2];const orientation=animatedProperty(node,'Orientation')||[0,0,0];const vertices=[];for(let x=-1;x<=1;x+=2)for(let y=-1;y<=1;y+=2)for(let z=-1;z<=1;z+=2){const offset=rotateVector([x*size[0]/2,y*size[1]/2,z*size[2]/2],orientation);vertices.push(toScreen(offset.map((v,i)=>v+pos[i])));}ctx.strokeStyle=node.id===selectedId?'#a690e1':'#766184';ctx.lineWidth=node.id===selectedId?1.6:1;ctx.fillStyle=node.id===selectedId?'#a690e10b':'#a690e104';const edges=[[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];for(const [a,b]of edges){ctx.beginPath();ctx.moveTo(...vertices[a]);ctx.lineTo(...vertices[b]);ctx.stroke();}const p=toScreen(pos);sceneHitTargets.push({id:node.id,x:p[0],y:p[1],radius:Math.max(16,Math.min(45,planScale*Math.max(...size)/2))});ctx.fillStyle='#ad9bbb';ctx.font='9px sans-serif';ctx.fillText(node.name,p[0]+9,p[1]+18);if(node.class==='MeshPart'){ctx.fillStyle='#a690e1';ctx.fillText('mesh · volume indicatif',p[0]+9,p[1]+31);}}
    for(const node of project.nodes.filter(n=>['Beam','Trail'].includes(n.class))){const first=nodeById(node.properties.Attachment0);const second=nodeById(node.properties.Attachment1);if(!first||!second)continue;const p=toScreen(worldPosition(first)),q=toScreen(worldPosition(second));ctx.strokeStyle=node.id===selectedId?'#b3fff2':node.class==='Beam'?'#8ce9e280':'#f3b47b90';ctx.lineWidth=node.id===selectedId?3:1.8;ctx.setLineDash(node.class==='Trail'?[5,4]:[]);ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();ctx.setLineDash([]);const middle=[(p[0]+q[0])/2,(p[1]+q[1])/2];sceneHitTargets.push({id:node.id,x:middle[0],y:middle[1],radius:12});ctx.fillStyle='#a5ccc6';ctx.font='9px sans-serif';ctx.fillText(node.name,middle[0]+7,middle[1]-8);}
    for(const node of project.nodes.filter(n=>!['Part','MeshPart','Beam','Trail','Folder','Model'].includes(n.class))){const pos=worldPosition(node);const p=toScreen(pos);const isAttachment=node.class==='Attachment',isEmitter=node.class==='ParticleEmitter';const offset=isEmitter?[-14,-12]:node.class==='SpecialMesh'?[15,0]:[0,0];const marker=[p[0]+offset[0],p[1]+offset[1]];ctx.strokeStyle=node.id===selectedId?'#fff3e6':isAttachment?'#8ce9e2':'#f3b47b';ctx.fillStyle=node.id===selectedId?'#f3b47b25':'#191522';ctx.lineWidth=1.4;ctx.beginPath();ctx.arc(...marker,isAttachment?4:9,0,Math.PI*2);ctx.fill();ctx.stroke();if(!isAttachment){ctx.fillStyle=isEmitter?'#f3b47b':'#a690e1';ctx.font='11px sans-serif';ctx.textAlign='center';ctx.fillText(ICONS[node.class]||'◇',marker[0],marker[1]+4);ctx.textAlign='left';}sceneHitTargets.push({id:node.id,x:marker[0],y:marker[1],radius:isAttachment?8:11});if(node.id===selectedId){ctx.fillStyle='#e4d6ed';ctx.font='10px sans-serif';ctx.fillText(node.name,marker[0]+13,marker[1]-7);}}
    ctx.font='9px sans-serif';ctx.fillStyle='#6b5b77';ctx.textAlign='right';ctx.fillText('1 carreau = 1 stud · molette pour zoomer',w-19,h-69);ctx.textAlign='left';
  }
  function attachCanvasEvents() {
    const canvas=$('#scene-canvas');canvas.addEventListener('wheel',e=>{e.preventDefault();planScale=bounded(planScale*(e.deltaY>0?.9:1.1),8,100);drawScene();},{passive:false});
    canvas.addEventListener('pointerdown',e=>{const rect=canvas.getBoundingClientRect();const x=e.clientX-rect.left,y=e.clientY-rect.top;const hit=[...sceneHitTargets].reverse().find(t=>Math.hypot(t.x-x,t.y-y)<t.radius);if(hit){selectNode(hit.id);const node=nodeById(hit.id);if(['Part','MeshPart','Attachment'].includes(node.class)){const initial=clone(node.properties.Position||[0,0,0]);const start=[e.clientX,e.clientY];let moved=false;const move=event=>{if(Math.hypot(event.clientX-start[0],event.clientY-start[1])<3&&!moved)return;if(!moved){remember();moved=true;}const dx=(event.clientX-start[0])/(.866*planScale),dz=(event.clientY-start[1])/(.35*planScale);node.properties.Position=[round(initial[0]+(dx+dz)/2),initial[1],round(initial[2]+(dz-dx)/2)];dirty=true;drawScene();};const up=()=>{window.removeEventListener('pointermove',move);if(moved){persist();renderAll();}};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true});}}else{const initial=clone(cameraPan);const start=[e.clientX,e.clientY];const move=event=>{cameraPan=[initial[0]+event.clientX-start[0],initial[1]+event.clientY-start[1]];drawScene();};const up=()=>window.removeEventListener('pointermove',move);window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true});}});
    canvas.addEventListener('dragover',e=>{if(e.dataTransfer.types.includes('application/x-dataky-asset')){e.preventDefault();e.dataTransfer.dropEffect='copy';}});canvas.addEventListener('drop',e=>{e.preventDefault();try{const {record,kind}=JSON.parse(e.dataTransfer.getData('application/x-dataky-asset'));applyAsset(record,kind);}catch(_){message('Cette ressource ne peut pas être déposée ici.','error');}});
  }

  function validateProject(value) {
    if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('La recette doit être un objet JSON.');
    if(value.version!==1)throw new Error('La version attendue est 1.');
    if(!Array.isArray(value.nodes))throw new Error('Le champ nodes doit être une liste.');
    const maxDuration=schema.limits?.duration||600;if(!Number.isFinite(value.duration)||value.duration<=0||value.duration>maxDuration)throw new Error('La durée doit être comprise entre 0 et '+maxDuration+' secondes.');
    const ids=new Set();for(const node of value.nodes){if(typeof node.id!=='string'||!node.id||ids.has(node.id))throw new Error('Chaque objet doit avoir un ID unique.');ids.add(node.id);if(!schema.classes[node.class])throw new Error('Classe non prise en charge : '+node.class);if(!node.properties||typeof node.properties!=='object'||Array.isArray(node.properties))throw new Error('Propriétés invalides pour '+node.id);}
    for(const node of value.nodes){if(node.parent&&!ids.has(node.parent))throw new Error('Parent introuvable pour '+node.id+' : '+node.parent);let cursor=node;const visited=new Set();while(cursor?.parent){if(visited.has(cursor.id))throw new Error('La hiérarchie contient une boucle : '+node.id);visited.add(cursor.id);cursor=value.nodes.find(n=>n.id===cursor.parent);}}
    if(value.animations!==undefined&&!Array.isArray(value.animations))throw new Error('Le champ animations doit être une liste.');
    return {...clone(value),name:String(value.name||'Effet sans nom'),animations:value.animations||[]};
  }
  function exportableProject() {return validateProject(project);}
  async function saveProject(silent=false) {
    if(saving)return null;saving=true;$('#save-button').disabled=true;
    try { const saved=await api('/api/project',{method:'POST',body:JSON.stringify(exportableProject())});const result=saved.project||saved;
      if(result.id)project.id=result.id;if(result.updated_at)project.updated_at=result.updated_at;dirty=false;persist();if(!silent)message('Projet enregistré.','success');return project.id;
    }catch(error){message('Enregistrement : '+error.message+' Le brouillon reste sur cet appareil.','error');return null;}
    finally{saving=false;$('#save-button').disabled=false;}
  }
  async function listProjects() {
    $('#projects-dialog').showModal();$('#project-list').innerHTML='<div class="empty-message">Chargement des projets…</div>';
    try{const data=await api('/api/projects');const projects=data.projects||[];const list=$('#project-list');list.replaceChildren();if(!projects.length){list.innerHTML='<div class="empty-message">Votre premier projet attend d’être enregistré.</div>';return;}
      for(const item of projects){const row=document.createElement('div');row.className='project-list-row';const button=document.createElement('button');button.className='project-open';const title=document.createElement('span');title.textContent=item.name||'Effet sans nom';const date=document.createElement('small');const parsed=new Date(item.updated_at);date.textContent=Number.isFinite(parsed.getTime())?'Modifié le '+parsed.toLocaleString('fr-FR'):'Projet enregistré';button.append(title,date);button.onclick=()=>loadProject(item.id);const remove=document.createElement('button');remove.className='icon-button danger';remove.title='Supprimer le projet';remove.setAttribute('aria-label','Supprimer '+item.name);remove.textContent='×';remove.onclick=async()=>{if(!confirm('Supprimer définitivement « '+item.name+' » ?'))return;try{await api('/api/project/'+encodeURIComponent(item.id),{method:'DELETE'});row.remove();message('Projet supprimé.');}catch(e){message(e.message,'error');}};row.append(button,remove);list.append(row);}
    }catch(e){$('#project-list').innerHTML='<div class="empty-message">'+escape(e.message)+'</div>';}
  }
  async function loadProject(id) {
    if(dirty&&project.nodes.length&&!confirm('Ouvrir ce projet et remplacer le brouillon actuel ?'))return;
    try{const data=await api('/api/project/'+encodeURIComponent(id));const loaded=validateProject(data.project||data);remember();project=loaded;selectedId=project.nodes[0]?.id||null;dirty=false;time=0;persist();renderAll();$('#projects-dialog').close();message('Projet ouvert.');}catch(e){message(e.message,'error');}
  }
  function download(content,filename,type='application/json') {const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function projectFilename(extension='json') {return (project.name||'effet').replace(/[^\p{L}\p{N}_-]+/gu,'_')+'.'+extension;}
  async function copyText(value,success='Copié') {try{await navigator.clipboard.writeText(value);message(success,'success');}catch(_){message('La copie a été refusée par le navigateur. Sélectionnez et copiez le texte manuellement.','error');}}
  function showJSON() {$('#project-json').value=JSON.stringify(project,null,2);$('#json-error').textContent='';$('#json-dialog').showModal();}
  function openExportMenu(button) {
    showMenu(button,[['menu-label','EXPORTER VOTRE EFFET'],['Recette JSON · brouillon',()=>download(JSON.stringify(project,null,2),projectFilename())],['Script Roblox Luau',async()=>{const id=await saveProject(true);if(!id)return;const link=document.createElement('a');link.href='/api/export/'+encodeURIComponent(id)+'.lua';link.download=projectFilename('lua');document.body.append(link);link.click();link.remove();}],['Recette JSON validée',async()=>{const id=await saveProject(true);if(!id)return;const link=document.createElement('a');link.href='/api/export/'+encodeURIComponent(id)+'.json';link.download=projectFilename();document.body.append(link);link.click();link.remove();}]]);
  }
  function showMenu(anchor,items) {
    const menu=$('#floating-menu');menu.replaceChildren();
    for(const [label,action]of items){if(label==='menu-label'){const title=document.createElement('div');title.className='menu-label';title.textContent=action;menu.append(title);}else{const b=document.createElement('button');b.textContent=label;b.onclick=()=>{hideMenu();action();};menu.append(b);}}
    menu.classList.remove('hidden');const rect=anchor.getBoundingClientRect();const bounds=menu.getBoundingClientRect();menu.style.top=Math.min(rect.bottom+6,innerHeight-bounds.height-12)+'px';menu.style.left=Math.min(rect.left,innerWidth-bounds.width-12)+'px';
  }
  function hideMenu() {$('#floating-menu').classList.add('hidden');}
  let lastStatusError='';
  let lastAckId='';
  async function refreshStatus(announce=false) {
    try {nativeStatus=await api('/api/status');const ack=nativeStatus.last_ack;const newAck=ack&&(ack.id||JSON.stringify(ack))!==lastAckId;const state=newAck&&ack.ok&&ack.details?ack.details:nativeStatus.runtime;
      if(state){nativePaused=!!state.paused;nativePlaying=!!state.playing;}if(!nativeStatus.connected){nativePaused=false;nativePlaying=false;}renderNativeStatus();
      if(announce)message(nativeStatus.connected?'Roblox Studio est connecté.':'Le pont n’est pas encore connecté.',nativeStatus.connected?'success':'info');const error=nativeStatus.last_error||nativeStatus.last_command?.error||nativeStatus.last_result?.error;if(error&&String(error)!==lastStatusError){lastStatusError=String(error);message('Studio : '+String(error),'error');}if(!error)lastStatusError='';
      if(newAck){lastAckId=ack.id||JSON.stringify(ack);const warnings=ack.details?.warnings||ack.warnings;if(Array.isArray(warnings)&&warnings.length)message('Studio : '+warnings.join(' · '),'error');const errors=ack.details?.errors;if(Array.isArray(errors)&&errors.length)message('Studio : '+errors.join(' · '),'error');}}
    catch(e){nativeStatus={connected:false,last_error:e.message};renderNativeStatus();if(announce)message('Serveur local inaccessible : '+e.message,'error');}
  }
  function renderNativeStatus() {
    const connected=!!nativeStatus.connected;const button=$('#connection-button');button.classList.toggle('connected',connected);$('span',button).textContent=connected?'Studio connecté':'Studio déconnecté';$('#native-indicator').classList.toggle('connected',connected);$('#native-indicator').innerHTML='<i></i>'+(connected?'Rendu natif connecté':'Rendu natif dans Studio');
    const studioName=typeof nativeStatus.studio==='string'?nativeStatus.studio:(nativeStatus.studio?.name||nativeStatus.studio?.place_name||'Roblox Studio');const summary=$('#connection-summary');summary.classList.toggle('connected',connected);summary.textContent=connected?'Connecté à '+studioName+'. Appliquez votre composition pour créer un aperçu isolé.':'Le pont local attend Roblox Studio. Vous pouvez continuer à construire votre effet et connecter Studio ensuite.';
    if(connected&&nativeStatus.bridge_update_required){$('span',button).textContent='Pont à mettre à jour';summary.textContent='Studio utilise encore une ancienne connexion. Redémarrez Studio et activez Plugins → Dataky FX → Connexion. Le nouveau pont est déjà installé.';}else if(connected&&nativeStatus.bridge_capabilities?.capture_context==='command_bar'){summary.textContent='Connexion temporaire active. Pour l’aperçu intégré, redémarrez Studio puis activez le plugin Dataky FX avec son bouton Connexion.';}
    $('#connection-diagnostics').textContent=JSON.stringify(nativeStatus,null,2);
    $('#pause-button').disabled=!connected;$('#pause-button').textContent=nativePaused?'▶ Reprendre':'Ⅱ Pause';
  }
  async function showConnection() {
    $('#connection-dialog').showModal();await Promise.allSettled([refreshStatus(),(async()=>{try{runtime=await api('/api/runtime');$('#bootstrap-command').textContent=runtime.bootstrap_command||runtime.command||'Le serveur ne fournit pas encore de commande de connexion.';$('#bootstrap-download').href=runtime.bootstrap_url||'/bridge/bootstrap.lua';}catch(e){$('#bootstrap-command').textContent='Impossible de charger la commande : '+e.message;}})()]);
  }
  async function nativeAction(action,quiet=false) {
    if(!nativeStatus.connected){message('Connectez Roblox Studio pour afficher le rendu natif.');await showConnection();return;}
    try {const data=await api('/api/preview',{method:'POST',body:JSON.stringify({action,...(['apply','play'].includes(action)?{project:exportableProject(),time:0}:{})})});
      const labels={apply:'Composition envoyée au moteur Roblox.',play:'Lecture envoyée au moteur Roblox.',stop:'Arrêt envoyé.',clear:'Fermeture de l’aperçu envoyée.',pause:'Pause envoyée.',resume:'Reprise envoyée.'};if(!quiet)message(labels[action]||'Commande envoyée.');
      if(action==='play'){nativePlaying=true;nativePaused=false;time=0;renderTimeline();$('#playhead-time').value=0;drawScene();}
      if(action==='stop'||action==='clear'){nativePlaying=false;nativePaused=false;}if(['apply','play','stop','clear'].includes(action))clearNativeFrame();
      if(action==='pause')nativePaused=true;if(action==='resume')nativePaused=false;renderNativeStatus();setTimeout(()=>refreshStatus(),700);
    }catch(e){message('Aperçu Studio : '+e.message,'error');}
  }
  function setViewport(mode) {
    viewportMode=mode;$('#view-plan').classList.toggle('active',mode==='plan');$('#view-native').classList.toggle('active',mode==='native');$('#native-view').classList.toggle('hidden',mode!=='native');$('#scene-empty').classList.toggle('hidden',!!project.nodes.length||mode!=='plan');$('.scene-corner').classList.toggle('hidden',mode!=='plan');$('.scene-label').classList.toggle('hidden',mode!=='plan');
  }
  function clearNativeFrame(){nativeFrameToken++;nativeFrameSequence=null;nativeFrameMeta=null;$('#native-frame').hidden=true;$('#native-frame').removeAttribute('src');$('#native-view').classList.remove('has-native-frame');if(nativeFrameObjectURL){URL.revokeObjectURL(nativeFrameObjectURL);nativeFrameObjectURL=null;}if(!screenStream)$('#video-tools').classList.add('hidden');}
  async function startNativePreview(){
    if(!nativeStatus.connected){message('Connectez Studio pour activer l’aperçu intégré.');await showConnection();return;}
    if(nativeStatus.bridge_update_required){const error='Le pont actif est ancien. Redémarrez Roblox Studio, puis cliquez sur Plugins → Dataky FX → Connexion.';$('#native-preview-message').textContent=error;message(error,'error');await showConnection();return;}
    if(nativeStatus.bridge_capabilities?.capture_context==='command_bar'&&!nativeStatus.preview?.permission){const error='Cette connexion temporaire ne peut pas demander la capture. Redémarrez Studio pour charger le plugin Dataky FX, puis cliquez sur son bouton Connexion.';$('#native-preview-message').textContent=error;message(error,'error');await showConnection();return;}
    if(!project.nodes.length){message('Choisissez un modèle ou ajoutez un objet avant de lancer l’aperçu.');return;}
    stopSharing(false);setViewport('native');$('#native-preview-message').textContent='Démarrage du rendu. Acceptez la demande de capture dans Studio si elle apparaît.';
    try{await api('/api/preview',{method:'POST',body:JSON.stringify({action:'apply',project:exportableProject()})});await api('/api/preview',{method:'POST',body:JSON.stringify({action:'preview_start'})});replayAfterPermission=true;setTimeout(()=>{refreshStatus();pollNativeFrame();},400);message('Aperçu demandé. L’effet sera lu après l’autorisation de capture.');}catch(e){replayAfterPermission=false;$('#native-preview-message').textContent=e.message;message('Aperçu : '+e.message,'error');}
  }
  async function stopNativePreview(){replayAfterPermission=false;stopSharing(false);clearNativeFrame();try{if(nativeStatus.connected)await api('/api/preview',{method:'POST',body:JSON.stringify({action:'preview_stop'})});}catch(e){message(e.message,'error');}$('#native-preview-message').textContent='Aperçu arrêté. Vous pouvez le réactiver à tout moment.';}
  async function pollNativeFrame(){
    if(nativeFrameBusy||screenStream||viewportMode!=='native'||!nativeStatus.connected)return;nativeFrameBusy=true;
    try{const state=await api('/api/preview/frame');nativeStatus.preview=state;
      if(state.error)$('#native-preview-message').textContent=state.error;
      if(replayAfterPermission&&state.enabled&&state.permission){replayAfterPermission=false;await nativeAction('play',true);return;}
      if(!state.enabled&&state.error)replayAfterPermission=false;
      if(!state.enabled||!state.frame){clearNativeFrame();return;}
      const frame=state.frame;if(Number(frame.age)>4){clearNativeFrame();$('#native-preview-message').textContent='Studio attend le viewport actif avant d’envoyer une nouvelle image.';return;}
      if(frame.sequence===nativeFrameSequence)return;
      const token=nativeFrameToken;const response=await fetch('/api/preview/frame.png?sequence='+encodeURIComponent(frame.sequence),{cache:'no-store'});if(!response.ok)return;const blob=await response.blob();if(token!==nativeFrameToken||screenStream||viewportMode!=='native')return;const url=URL.createObjectURL(blob);const image=$('#native-frame');const old=nativeFrameObjectURL;nativeFrameObjectURL=url;nativeFrameSequence=frame.sequence;nativeFrameMeta=frame;image.onload=()=>{if(old)URL.revokeObjectURL(old);};image.src=url;image.hidden=false;$('#studio-video').hidden=true;$('#native-view').classList.add('has-native-frame');$('#video-tools').classList.remove('hidden');$('#native-frame-status').textContent='Roblox · '+Number(frame.time||0).toFixed(2)+' s · '+frame.width+' × '+frame.height;
    }catch(e){if(nativeFrameSequence!==null)$('#native-frame-status').textContent='Aperçu momentanément indisponible';}finally{nativeFrameBusy=false;}
  }
  function scheduleNativePreview(){if(autoPreviewTimer)clearTimeout(autoPreviewTimer);if(!$('#auto-preview')?.checked||!nativeStatus.preview?.enabled||!nativeStatus.connected)return;autoPreviewTimer=setTimeout(()=>nativeAction('play',true),500);}
  async function startSharing() {
    if(!navigator.mediaDevices?.getDisplayMedia)return message('Le partage de fenêtre nécessite un navigateur compatible ouvert sur localhost.','error');
    try {const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});if(nativeStatus.connected)api('/api/preview',{method:'POST',body:JSON.stringify({action:'preview_stop'})}).catch(()=>{});stopSharing(false);clearNativeFrame();screenStream=stream;const video=$('#studio-video');video.hidden=false;video.srcObject=stream;await video.play();$('#native-view').classList.add('has-stream');$('#video-tools').classList.remove('hidden');stream.getVideoTracks()[0].onended=()=>stopSharing();setViewport('native');message('Fenêtre partagée. Le rendu affiché provient directement de la fenêtre choisie.','success');}
    catch(e){if(e.name!=='NotAllowedError')message('Partage de fenêtre : '+e.message,'error');}
  }
  function stopSharing(announce=true) {
    if(screenStream){for(const track of screenStream.getTracks()){track.onended=null;track.stop();}screenStream=null;}$('#studio-video').srcObject=null;$('#studio-video').hidden=true;$('#native-view').classList.remove('has-stream');if(!nativeFrameMeta)$('#video-tools').classList.add('hidden');if(announce)message('Partage de fenêtre arrêté.');
  }
  function cameraFields(camera) {
    const host=$('#camera-fields');host.replaceChildren();
    for(const [key,label]of[['position','Position'],['target','Cible']]){const group=document.createElement('div');group.className='vector-inputs';for(let i=0;i<3;i++){const wrap=document.createElement('label');wrap.className='vector-component';const axis=document.createElement('span');axis.textContent=['X','Y','Z'][i];const input=document.createElement('input');input.type='number';input.step='any';input.value=camera[key][i];input.dataset.camera=key;input.dataset.axis=i;input.setAttribute('aria-label',label+' caméra '+['X','Y','Z'][i]);wrap.append(axis,input);group.append(wrap);}host.append(rowFor(label,group));}
    const fov=document.createElement('input');fov.type='number';fov.min=1;fov.max=120;fov.value=camera.fov||50;fov.id='camera-fov';host.append(rowFor('Champ de vision',fov));
  }
  function openCamera(){cameraFields(project.camera||{position:[10,6,12],target:[0,1,0]});$('#camera-error').textContent='';$('#camera-dialog').showModal();}
  function openAnimationGraph(){
    try{if(!window.DatakyCurves)throw new Error('Rechargez l’application pour charger l’éditeur de courbes.');const node=nodeById(animationNode);const property=$('#animation-property').value;const def=schema.classes[node.class].properties[property];if(!['number','integer','Vector2','Vector3','Color3','NumberRange'].includes(def.type))throw new Error('L’éditeur graphique s’utilise avec des nombres, des vecteurs ou des couleurs.');const value=JSON.parse($('#animation-json').value);const key=node.id+'::'+property;$('#animation-dialog').close();window.DatakyCurves.open({type:'animation',value,definition:def,duration:project.duration,title:node.name+' · '+property,editor:project.editor?.curves?.[key],onApply:result=>{commit(p=>{p.animations=p.animations.filter(a=>!(a.node===node.id&&a.property===property));p.animations.push({node:node.id,property,keyframes:result.value});p.editor??={version:1,curves:{}};p.editor.curves??={};p.editor.curves[key]=result.editor;});}});}catch(e){$('#animation-error').textContent=e.message;}
  }
  async function takeSnapshot() {
    if(nativeFrameMeta&&!screenStream){try{await api('/api/snapshot',{method:'POST',body:JSON.stringify({native:true})});message('Aperçu natif enregistré avec son projet et son instant de capture.','success');}catch(e){message('Capture : '+e.message,'error');}return;}
    const video=$('#studio-video');if(!screenStream||!video.videoWidth)return message('Partagez la fenêtre Studio avant de capturer un aperçu.','error');
    try{const canvas=document.createElement('canvas');const max=1920;const ratio=Math.min(1,max/video.videoWidth);canvas.width=Math.round(video.videoWidth*ratio);canvas.height=Math.round(video.videoHeight*ratio);const ctx=canvas.getContext('2d');const zoom=num($('#video-zoom').value,1);const sw=video.videoWidth/zoom,sh=video.videoHeight/zoom;ctx.drawImage(video,(video.videoWidth-sw)/2,(video.videoHeight-sh)/2,sw,sh,0,0,canvas.width,canvas.height);const data=await api('/api/snapshot',{method:'POST',body:JSON.stringify({image:canvas.toDataURL('image/png'),project_id:project.id||null,time})});message('Aperçu enregistré'+(data.filename?' : '+data.filename:'.'),'success');}
    catch(e){message('Capture : '+e.message,'error');}
  }
  function bindEvents() {
    $('#project-name').onchange=e=>commit(p=>{p.name=e.target.value.trim()||'Effet sans nom';},{properties:false});$('#save-button').onclick=()=>saveProject();$('#undo-button').onclick=undo;$('#redo-button').onclick=redo;$('#clone-button').onclick=duplicateNode;$('#delete-button').onclick=removeNode;
    $('#add-button').onclick=e=>showMenu(e.currentTarget,[['menu-label','STRUCTURE'],...['Part','MeshPart','Attachment','Folder','Model'].filter(c=>schema.classes[c]).map(c=>[(ICONS[c]||'◇')+' '+c,()=>addNode(c)]),['menu-label','EFFETS'],...['ParticleEmitter','Beam','Trail','SpecialMesh','PointLight','SpotLight','SurfaceLight'].filter(c=>schema.classes[c]).map(c=>[(ICONS[c]||'◇')+' '+c,()=>addNode(c)])]);
    $('#empty-add').onclick=()=>addNode('Part');$$('[data-template]').forEach(b=>b.onclick=()=>useTemplate(b.dataset.template));$('#project-menu').onclick=listProjects;
    $('#json-button').onclick=showJSON;$('#export-button').onclick=e=>openExportMenu(e.currentTarget);$('#copy-json').onclick=()=>copyText($('#project-json').value,'Recette copiée');$('#download-json').onclick=()=>download($('#project-json').value,projectFilename());
    $('#apply-json').onclick=()=>{try{const value=validateProject(JSON.parse($('#project-json').value));remember();project=value;selectedId=project.nodes[0]?.id||null;dirty=true;time=0;persist();renderAll();$('#json-dialog').close();message('Recette appliquée au brouillon.');}catch(e){$('#json-error').textContent=e.message;}};
    $('#import-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;$('#project-json').value=await file.text();$('#json-error').textContent='';e.target.value='';};
    $$('[data-collection]').forEach(b=>b.onclick=()=>{collection=b.dataset.collection;renderCatalog(true);});$('#catalog-search').oninput=e=>{filters[collection].search=e.target.value;filters[collection].page=0;renderCatalog();};$('#catalog-tag').onchange=e=>{filters[collection].tag=e.target.value;filters[collection].page=0;renderCatalog();};$('#clear-filters').onclick=()=>{filters[collection]={search:'',tag:'',page:0};renderCatalog(true);};$('#catalog-prev').onclick=()=>{filters[collection].page--;renderCatalog();$('#catalog-grid').scrollTop=0;};$('#catalog-next').onclick=()=>{filters[collection].page++;renderCatalog();$('#catalog-grid').scrollTop=0;};
    $('#duration').onchange=e=>{const duration=Number(e.target.value);if(!Number.isFinite(duration)||duration<=0||duration>(schema.limits?.duration||600)){e.target.value=project.duration;return;}commit(p=>{p.duration=duration;time=Math.min(time,duration);},{properties:false});};$('#loop').onchange=e=>commit(p=>{p.loop=e.target.checked;},{properties:false});$('#playhead-time').onchange=e=>{time=bounded(num(e.target.value),0,project.duration);e.target.value=time;renderTimeline();drawScene();};
    $('#play-button').onclick=()=>nativeAction('play');$('#stop-button').onclick=()=>nativeAction('stop');$('#apply-button').onclick=()=>nativeAction(nativeStatus.preview?.enabled?'play':'apply');$('#clear-preview').onclick=()=>nativeAction('clear');$('#pause-button').onclick=()=>nativeAction(nativePaused?'resume':'pause');
    $('#connection-button').onclick=showConnection;$('#refresh-connection').onclick=()=>refreshStatus(true);$('#copy-bootstrap').onclick=()=>copyText($('#bootstrap-command').textContent,'Commande copiée. Collez-la dans la barre de commande de Studio.');$('#view-plan').onclick=()=>setViewport('plan');$('#view-native').onclick=()=>setViewport('native');$('#share-studio').onclick=startSharing;$('#start-native-preview').onclick=startNativePreview;$('#stop-sharing').onclick=stopNativePreview;$('#capture-snapshot').onclick=takeSnapshot;$('#video-zoom').oninput=e=>{for(const element of [$('#studio-video'),$('#native-frame')])element.style.transform=`scale(${e.target.value})`;};
    $('#animation-graph').onclick=openAnimationGraph;
    $('#recenter-button').onclick=()=>{cameraPan=[0,0];planScale=29;drawScene();};
    $('#camera-button').onclick=openCamera;$('#camera-front').onclick=()=>cameraFields({position:[0,2,14],target:[0,1,0],fov:50});$('#camera-perspective').onclick=()=>cameraFields({position:[10,6,12],target:[0,1,0],fov:50});$('#camera-apply').onclick=()=>{try{const camera={position:[],target:[],fov:Number($('#camera-fov').value)};for(const input of $$('[data-camera]'))camera[input.dataset.camera][Number(input.dataset.axis)]=Number(input.value);if([...camera.position,...camera.target,camera.fov].some(v=>!Number.isFinite(v))||camera.fov<1||camera.fov>120)throw new Error('Les coordonnées doivent être finies et le champ de vision entre 1 et 120.');if(camera.position.every((v,i)=>v===camera.target[i]))throw new Error('La caméra et sa cible doivent être distinctes.');commit(p=>{p.camera=camera;},{properties:false});$('#camera-dialog').close();message('Caméra conservée. Appliquez la composition pour actualiser Studio.');}catch(e){$('#camera-error').textContent=e.message;}};
    $('#sequence-add').onclick=()=>{const p=sequenceEdit.points;const sorted=[...p].sort((a,b)=>a.time-b.time);let biggest=[sorted[0],sorted[1]];for(let i=1;i<sorted.length;i++)if(sorted[i].time-sorted[i-1].time>biggest[1].time-biggest[0].time)biggest=[sorted[i-1],sorted[i]];const [a,b]=biggest;const value=Array.isArray(a.value)?a.value.map((v,i)=>(v+b.value[i])/2):(a.value+b.value)/2;p.push({time:round((a.time+b.time)/2),value,envelope:0});p.sort((a,b)=>a.time-b.time);renderSequenceEditor();};
    $('#sequence-apply').onclick=()=>{try{const points=validateSequence();const node=nodeById(sequenceEdit.node);if(!node)throw new Error('L’objet a été supprimé.');commit(()=>{node.properties[sequenceEdit.key]=sequenceArray(points,sequenceEdit.type);});$('#sequence-dialog').close();}catch(e){$('#sequence-error').textContent=e.message;}};
    $('#animation-apply').onclick=()=>{try{const keyframes=JSON.parse($('#animation-json').value);if(!Array.isArray(keyframes)||keyframes.length<2)throw new Error('Au moins deux points clés sont nécessaires.');const node=nodeById(animationNode);const property=$('#animation-property').value;const def=schema.classes[node.class].properties[property];const type=def.type;for(let i=0;i<keyframes.length;i++){const f=keyframes[i];if(!Number.isFinite(f.time)||f.time<0||f.time>project.duration||(i&&f.time<=keyframes[i-1].time))throw new Error('Les temps doivent être croissants, distincts, et dans la durée du projet.');if(['number','integer'].includes(type)){if(!Number.isFinite(f.value)||(type==='integer'&&!Number.isInteger(f.value)))throw new Error('Valeur numérique attendue.');}else if(type==='boolean'){if(typeof f.value!=='boolean')throw new Error('Valeur true ou false attendue.');}else if(type==='enum'){if(!(def.enum||def.values||[]).includes(f.value))throw new Error('Valeur attendue : '+(def.enum||def.values||[]).join(', '));}else{const size=['Vector2','NumberRange'].includes(type)?2:3;if(!Array.isArray(f.value)||f.value.length!==size||f.value.some(v=>!Number.isFinite(v)))throw new Error('Le point clé attend un vecteur de '+size+' nombres.');}}commit(p=>{p.animations=p.animations.filter(a=>!(a.node===animationNode&&a.property===property));p.animations.push({node:animationNode,property,keyframes});});$('#animation-dialog').close();}catch(e){$('#animation-error').textContent=e.message;}};
    $('#animation-remove').onclick=()=>{const property=$('#animation-property').value;commit(p=>{p.animations=p.animations.filter(a=>!(a.node===animationNode&&a.property===property));});$('#animation-dialog').close();};
    document.addEventListener('pointerdown',e=>{if(!$('#floating-menu').contains(e.target)&&!e.target.closest('#add-button,#export-button'))hideMenu();});
    document.addEventListener('keydown',e=>{const typing=e.target.closest('input,textarea,select,[contenteditable]');const modal=$$('dialog[open]').length>0;const mod=e.ctrlKey||e.metaKey;if(mod&&e.key.toLowerCase()==='s'){e.preventDefault();saveProject();return;}if(mod&&e.key.toLowerCase()==='z'&&!typing&&!modal){e.preventDefault();e.shiftKey?redo():undo();return;}if(mod&&e.key.toLowerCase()==='y'&&!typing&&!modal){e.preventDefault();redo();return;}if(mod&&e.key.toLowerCase()==='d'&&!typing&&!modal){e.preventDefault();duplicateNode();return;}if(!typing&&!modal){if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();removeNode();}if(e.key==='/'){e.preventDefault();$('#catalog-search').focus();}if(e.key==='Escape')hideMenu();}});
    window.addEventListener('resize',()=>{drawScene();renderTimeline();});window.addEventListener('beforeunload',()=>{persist();stopSharing(false);if(nativeStatus.preview?.enabled)fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'preview_stop'}),keepalive:true}).catch(()=>{});});attachCanvasEvents();
  }
  async function loadData() {
    await Promise.allSettled([
      (async()=>{try{const data=await api('/api/schema');if(!data.classes)throw new Error('Le schéma ne contient pas de classes.');schema=data;schemaOnline=true;$('#duration').max=schema.limits?.duration||600;try{localStorage.setItem(CACHE_SCHEMA,JSON.stringify(schema));}catch(_){}renderProperties();}catch(e){if(!schemaWarning){schemaWarning=true;message('Schéma local indisponible. Votre brouillon reste accessible; reconnectez le serveur avant l’export.','error');}}})(),
      (async()=>{try{const data=await api('/api/catalog');catalog={textures:data.textures||[],beams:data.beams||[],meshes:data.meshes||[]};catalogLoaded=true;renderCatalog(true);}catch(e){catalogFailed=true;renderCatalog(true);message('La bibliothèque n’a pas pu être chargée. Les modèles intégrés restent disponibles.','error');}})(),refreshStatus()
    ]);
  }
  if(!Array.isArray(project.animations))project.animations=[];
  bindEvents();renderAll();renderCatalog(true);renderNativeStatus();setViewport(viewportMode);persist();loadData();setInterval(()=>refreshStatus(),3500);setInterval(()=>pollNativeFrame(),250);
  // A compact public automation surface uses the same editor validation and commands.
  window.DatakyFX = Object.freeze({getProject:()=>clone(project),getSchema:()=>clone(schema),getStatus:()=>clone(nativeStatus),setProject:value=>{const next=validateProject(value);remember();project=next;selectedId=next.nodes[0]?.id||null;dirty=true;time=0;persist();renderAll();return clone(project);},save:()=>saveProject(),preview:action=>nativeAction(action),select:selectNode});
})();
