'use strict';

// Integration tests of the actual app.js closures. Browser startup is intercepted;
// only the unrelated full-layout renderer is replaced with a no-op. Preview,
// transport, frame invalidation, persistence and graph callbacks stay unchanged.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const curves=require('../editor/curves.js');
const schema=JSON.parse(execFileSync(process.env.DATAKY_TEST_PYTHON||'python',['-c','import json; from fx_schema import SCHEMA; print(json.dumps(SCHEMA))'],{cwd:__dirname,encoding:'utf8'}));
const plain=value=>JSON.parse(JSON.stringify(value));

function editorHarness(){
  const nodes=new Map();
  class Element{
    constructor(selector){this.selector=selector;this.hidden=true;this.value='';this.checked=false;this.children=[];this.attributes={};this.dataset={};this.src='';this.textContent='';this.innerHTML='';this.locals=new Map();this.style={};const classes=new Set();this.classList={add:(...names)=>names.forEach(n=>classes.add(n)),remove:(...names)=>names.forEach(n=>classes.delete(n)),contains:name=>classes.has(name),toggle:(name,value)=>{const enabled=value??!classes.has(name);enabled?classes.add(name):classes.delete(name);return enabled;}};}
    append(...items){this.children.push(...items);}
    replaceChildren(...items){this.children=[...items];}
    get options(){return this.children;}
    focus(){this.focused=true;}
    click(){this.clicked=true;this.onclick?.({currentTarget:this});}
    remove(){this.removed=true;}
    removeAttribute(key){delete this.attributes[key];if(key==='src')this.src='';}
    setAttribute(key,value){this.attributes[key]=String(value);}
    querySelector(selector){if(!this.locals.has(selector))this.locals.set(selector,new Element(this.selector+' '+selector));return this.locals.get(selector);}
    querySelectorAll(){return[];}
    close(){this.open=false;}
    showModal(){this.open=true;}
  }
  const get=selector=>{if(!nodes.has(selector))nodes.set(selector,new Element(selector));return nodes.get(selector);};
  const cache=new Map([['dataky-fx-studio.schema.v1',JSON.stringify(schema)]]);
  const calls=[],timers=[],revoked=[],created=[];let frameState={enabled:false,frame:null};let status={connected:true,studio:'QA Studio'};let denyAction=null;let imageResponder=null;
  const response=(body,ok=true)=>({ok,status:ok?200:400,statusText:ok?'OK':'Rejected',json:async()=>body,blob:async()=>new Blob(['native-viewport-png'],{type:'image/png'})});
  const fetch=async(url,options={})=>{const body=options.body?JSON.parse(options.body):undefined;calls.push({url,method:options.method||'GET',body});
    if(url==='/api/status')return response(status);
    if(url==='/api/preview'){if(denyAction===body.action)return response({error:'Capture refusée par Studio'},false);return response({queued:true,id:'queued-'+calls.length});}
    if(url==='/api/preview/frame')return response(frameState);
    if(url.startsWith('/api/preview/frame.png'))return imageResponder?imageResponder():response(null);
    if(url==='/api/runtime')return response({bootstrap_command:'local bridge = true'});
    if(url==='/api/project')return response({...body,id:'saved-project'});
    if(url.startsWith('/api/project/'))return response({...plain(schemaFixture()),id:'loaded-project'});
    if(url.startsWith('/api/export/'))return denyAction==='export'?response({error:'MeshPart local : renseigner un MeshId Roblox avant export.'},false):response(null);
    throw new Error('Unexpected integration request: '+url);
  };
  const filename=path.resolve(__dirname,'../editor/app.js');const original=fs.readFileSync(filename,'utf8');
  const marker='  if(!Array.isArray(project.animations))project.animations=[];';assert.equal(original.split(marker).length,2,'App startup marker is unique');
  const source=original.replace(marker,`
  const actualRenderTimeline=renderTimeline;renderAll=()=>{};renderTimeline=()=>{};drawScene=()=>{};
  globalThis.__PreviewTest={startNativePreview,pollNativeFrame,stopNativePreview,clearNativeFrame,openSequence,openAnimationGraph,loadProject,refreshStatus,validateProject,emulatorView,syncEmulator,
    setPreviewMode,emitPreview,clearPreviewParticles,setNodeEnabled,toggleSelectionEnabled,enabledValue,previewProject,setPreviewParam,renderParams,renderTree,renderProperties,actualRenderTimeline,
    handleKeyDown,selectNode,copySelection,pasteSelection,transport,scheduleNativePreview,
    getPreview:()=>({mode:previewMode,enabled:clone(previewEnabled),params:clone(previewParamValues),selectedId,time,selection:[...selectionIds]}),
    getProject:()=>clone(project),getNode:nodeById,getMeta:()=>clone(nativeFrameMeta),getSequence:()=>nativeFrameSequence,
    configure:settings=>{if(settings.project){resetPreviewState();project=clone(settings.project);}if(settings.connected!==undefined)nativeStatus={connected:settings.connected};if(settings.status)nativeStatus=clone(settings.status);if(settings.mode)viewportMode=settings.mode;if(settings.animationNode)animationNode=settings.animationNode;if(settings.selectedId)selectedId=settings.selectedId;},
    makeTemplate:template};
  return;
${marker}`);
  const emulatorCalls=[],clipboard={text:''};
  const captured=[];const window={DatakyCurves:{open:options=>{captured.push(options);return{};}},DatakyEmulator:{validatePreviewMesh:require('../editor/emulator.js').validatePreviewMesh,createView:(canvas,options)=>{emulatorCalls.push({action:'createView',options});const view={mode:'timeline',playing:false,camera:{position:[10,6,12],target:[0,1,0]},setProject:project=>{emulatorCalls.push({action:'setProject',project:plain(project)});return true;},updateProject:project=>{emulatorCalls.push({action:'updateProject',project:plain(project)});return true;},resetPreviewState:()=>emulatorCalls.push({action:'resetPreviewState'}),setMode:mode=>{view.mode=mode;emulatorCalls.push({action:'setMode',mode});},setEnabled:(id,value)=>emulatorCalls.push({action:'setEnabled',id,value}),emit:(id,count)=>emulatorCalls.push({action:'emit',id,count}),clearParticles:()=>emulatorCalls.push({action:'clearParticles'}),frameEffect:ids=>emulatorCalls.push({action:'frameEffect',ids}),setView:value=>emulatorCalls.push({action:'setView',value}),draw(){}};for(const name of ['play','resume','pause','stop','seek'])view[name]=value=>{emulatorCalls.push({action:name,value});view.playing=['play','resume'].includes(name);};return view;}}};
  const sandbox={window,document:{querySelector:get,querySelectorAll:selector=>selector==='dialog[open]'?[...nodes.values()].filter(node=>node.open):[],createElement:tag=>new Element(tag),body:get('body')},console,crypto,Blob,fetch,
    Option:class extends Element{constructor(label,value){super('option');this.textContent=label;this.value=value;}},getComputedStyle:()=>({gridTemplateColumns:'134px 1fr'}),
    navigator:{clipboard:{writeText:async text=>{clipboard.text=text;},readText:async()=>clipboard.text}},
    localStorage:{getItem:key=>cache.get(key)||null,setItem:(key,value)=>cache.set(key,value)},
    URL:{createObjectURL:blob=>{assert.ok(blob instanceof Blob);const url='blob:dataky-'+(created.length+1);created.push(url);return url;},revokeObjectURL:url=>revoked.push(url)},
    setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){},setInterval(){throw new Error('Unintercepted startup timer');},confirm:()=>true};
  vm.createContext(sandbox);vm.runInContext(source,sandbox,{filename,timeout:3000});const api=sandbox.__PreviewTest;assert.ok(api);const fixture=api.makeTemplate('impact');
  function schemaFixture(){return fixture;}
  api.configure({project:fixture,connected:true,mode:'native'});
  return{api,get,calls,timers,captured,created,revoked,cache,emulatorCalls,clipboard,
    frame:value=>{frameState=value;},status:value=>{status=value;},deny:value=>{denyAction=value;},image:value=>{imageResponder=value;},response};
}

const freshFrame=(sequence=1,extra={})=>({enabled:true,error:null,frame:{sequence,age:.1,time:.75,width:960,height:540,...extra}});

test('editor uses the recipe background by default and retains an explicitly chosen preset',()=>{
  const html=fs.readFileSync(path.resolve(__dirname,'../editor/index.html'),'utf8');
  const menu=html.match(/<select id="emu-background"[^>]*>([\s\S]*?)<\/select>/)[1];
  assert.match(menu,/^<option value="">Fond de la recette<\/option>/);
  assert.match(menu,/<option value="roblox">/);
  for(const preset of ['', 'roblox']){
    const app=editorHarness();app.get('#emu-background').value=preset;app.api.configure({mode:'emu'});app.api.syncEmulator();
    assert.equal(app.emulatorCalls[0].options.background,preset||undefined);
    assert.equal(app.emulatorCalls[1].project.environment.background,'#191522');
    assert.equal(app.api.getProject().environment.background,'#191522','the preview preset never edits the recipe');
  }
});

const keyEvent=(key,extra={})=>({key,ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,target:{closest:()=>null},preventDefault(){this.prevented=true;},...extra});
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
test('free preview toggles Enabled without changing the recipe, while timeline changes persist and grey the track',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter');app.api.configure({mode:'emu',selectedId:emitter.id});
  app.api.setPreviewMode('free');app.api.setNodeEnabled([emitter.id],false);
  assert.equal(app.api.getProject().nodes.find(node=>node.id===emitter.id).properties.Enabled,true);
  assert.equal(app.api.getPreview().enabled[emitter.id],false);assert.ok(app.emulatorCalls.some(call=>call.action==='setEnabled'&&call.id===emitter.id&&call.value===false));
  const treeRow=app.get('#node-tree').children.find(row=>row.dataset.id===emitter.id);assert.equal(treeRow.children[0].attributes['aria-pressed'],'false');
  app.api.setPreviewMode('timeline');app.api.setNodeEnabled([emitter.id],false);assert.equal(app.api.getProject().nodes.find(node=>node.id===emitter.id).properties.Enabled,false);
  app.api.actualRenderTimeline();const row=app.get('#timeline').children.find(item=>item.className?.startsWith('timeline-row'));assert.match(row.querySelector('.track-surface').children[0].className,/disabled/);
});
test('manual Emit uses per-emitter quantities and selection descendants; Emit all uses only bursts with their authored count',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter'),source=recipe.nodes.find(node=>node.class==='Part');
  recipe.nodes.push({...plain(emitter),id:'continuous',timing:{start:0,duration:1,mode:'continuous',count:9}});app.api.configure({project:recipe,mode:'emu',selectedId:source.id});app.api.setPreviewMode('free');
  app.api.emitPreview('selection');let calls=app.emulatorCalls.filter(call=>call.action==='emit');assert.deepEqual(calls.map(call=>[call.id,call.count]),[[emitter.id,35],['continuous',9]]);
  app.api.selectNode(emitter.id);const quantity=app.get('#properties').children.find(node=>node.className==='emitter-preview-tools').children[1];quantity.value='12';quantity.oninput();app.api.emitPreview('selection');assert.equal(app.emulatorCalls.filter(call=>call.action==='emit').at(-1).count,12);
  app.api.emitPreview('all');calls=app.emulatorCalls.filter(call=>call.action==='emit');assert.deepEqual(calls.at(-1),{action:'emit',id:emitter.id,count:35});assert.equal(calls.filter(call=>call.id==='continuous').length,1);
  app.api.clearPreviewParticles();assert.equal(app.emulatorCalls.at(-1).action,'clearParticles');
});
test('native sandbox commands use counts and Enabled maps, and free edits update without replaying',async()=>{
  const app=editorHarness(),emitter=app.api.getProject().nodes.find(node=>node.class==='ParticleEmitter');app.api.configure({selectedId:emitter.id});app.api.setPreviewMode('free');await flush();
  app.api.setNodeEnabled([emitter.id],false);await flush();await app.api.emitPreview('all');await app.api.clearPreviewParticles();
  const commands=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body);assert.equal(commands[0].action,'sandbox');assert.equal(commands[0].mode,'free');assert.equal(commands[0].project.nodes.find(node=>node.id===emitter.id).properties.Enabled,true);
  assert.deepEqual(commands[1],{action:'enabled',enabled:{[emitter.id]:false}});assert.deepEqual(commands[2],{action:'emit',counts:{[emitter.id]:35}});assert.deepEqual(commands[3],{action:'clear_particles'});
  app.api.configure({status:{connected:true,preview:{enabled:true}}});app.api.scheduleNativePreview();assert.equal(app.timers.at(-1).ms,100);await app.timers.at(-1).fn();assert.equal(app.calls.at(-1).body.action,'update');assert.ok(!app.calls.some(call=>call.body?.action==='play'));
});
test('native free controls reinitialize sandbox after Stop and then retain live updates',async()=>{
  const app=editorHarness(),emitter=app.api.getProject().nodes.find(node=>node.class==='ParticleEmitter');
  app.api.setPreviewMode('free');await flush();await app.api.transport('stop');
  app.api.setNodeEnabled([emitter.id],false);await flush();
  let commands=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body);
  assert.deepEqual(commands.map(command=>command.action),['sandbox','stop','sandbox','enabled']);
  assert.equal(commands[2].mode,'free');assert.equal(commands[2].enabled[emitter.id],false);
  app.api.configure({status:{connected:true,preview:{enabled:true}}});app.api.scheduleNativePreview();await app.timers.at(-1).fn();
  commands=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body);
  assert.equal(commands.at(-1).action,'update');assert.equal(commands.filter(command=>command.action==='sandbox').length,2);
});
test('the first native free property edit initializes sandbox once when mode was selected in the emulator',async()=>{
  const app=editorHarness();app.api.configure({mode:'emu'});app.api.setPreviewMode('free');
  app.api.configure({mode:'native',status:{connected:true,preview:{enabled:true}}});
  app.api.scheduleNativePreview();await app.timers.at(-1).fn();
  let actions=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body.action);
  assert.deepEqual(actions,['sandbox'],'initial properties are already applied by sandbox');
  app.api.scheduleNativePreview();await app.timers.at(-1).fn();
  actions=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body.action);
  assert.deepEqual(actions,['sandbox','update'],'later edits retain the native simulation');
});
test('opening another project explicitly resets emulator preview state even with identical node IDs',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter');
  app.api.configure({mode:'emu'});app.api.setPreviewMode('free');app.api.setNodeEnabled([emitter.id],false);app.api.emitPreview('all');
  app.api.configure({project:{...recipe,name:'Another project'}});app.api.syncEmulator();
  assert.equal(app.emulatorCalls.filter(call=>call.action==='resetPreviewState').length,1);
  assert.deepEqual(plain(app.api.getPreview().enabled),{});
  assert.equal(app.api.enabledValue(app.api.getNode(emitter.id)),true);
});
test('an applied timeline preview is reinitialized as free before a direct Enabled command',async()=>{
  const app=editorHarness(),emitter=app.api.getProject().nodes.find(node=>node.class==='ParticleEmitter');
  app.api.configure({mode:'emu'});app.api.setPreviewMode('free');await app.api.startNativePreview();
  app.api.setNodeEnabled([emitter.id],false);await flush();
  const actions=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body.action);
  assert.deepEqual(actions,['apply','preview_start','sandbox','enabled']);
});
test('Emit retains an explicit emulator pause and starts the clock again after Stop',()=>{
  const app=editorHarness(),emitter=app.api.getProject().nodes.find(node=>node.class==='ParticleEmitter');
  app.api.configure({mode:'emu',selectedId:emitter.id});app.api.setPreviewMode('free');app.api.transport('toggle');
  assert.equal(app.emulatorCalls.at(-1).action,'pause');const before=app.emulatorCalls.length;
  app.api.handleKeyDown(keyEvent('e'));
  assert.ok(app.emulatorCalls.slice(before).some(call=>call.action==='emit'));
  assert.ok(!app.emulatorCalls.slice(before).some(call=>call.action==='resume'),'Emit does not cancel an explicit pause');
  app.api.transport('stop');app.api.handleKeyDown(keyEvent('e'));
  assert.equal(app.emulatorCalls.at(-1).action,'resume','Emit after Stop starts the free clock');
});
test('Emit retains an explicit native pause without replaying or resuming',async()=>{
  const app=editorHarness(),emitter=app.api.getProject().nodes.find(node=>node.class==='ParticleEmitter');
  app.api.configure({selectedId:emitter.id});app.api.setPreviewMode('free');await flush();await app.api.transport('toggle');
  app.api.handleKeyDown(keyEvent('e'));await flush();
  const actions=app.calls.filter(call=>call.url==='/api/preview').map(call=>call.body.action);
  assert.deepEqual(actions,['sandbox','pause','emit']);
});
test('parameter sliders transform marked preview values and animation envelopes, retaining the authored recipe',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter');recipe.params={radius:{default:16,min:4,max:48,step:1}};emitter.scaleWith={Size:'radius',Speed:'radius'};recipe.animations=[{node:emitter.id,property:'Speed',keyframes:[{time:0,value:[2,4]},{time:1,value:[4,8]}]}];app.api.configure({project:recipe,mode:'emu'});
  app.api.renderParams();const range=app.get('#preview-params').children[0].children[1];assert.equal(range.min,4);assert.equal(range.max,48);range.value=32;range.oninput();
  const result=app.api.previewProject(),scaled=result.nodes.find(node=>node.id===emitter.id);assert.deepEqual(plain(scaled.properties.Speed),plain(emitter.properties.Speed.map(value=>value*2)));assert.equal(scaled.properties.Size[0].value,emitter.properties.Size[0].value*2);assert.equal(scaled.scaleWith,undefined);
  assert.deepEqual(plain(result.animations[0].keyframes[1].value),[8,16]);assert.deepEqual(plain(app.api.getProject()),plain(recipe));assert.equal(app.get('#preview-params').children[0].children[1],range,'the live slider is retained throughout a drag');
});
test('keyboard shortcuts never trigger in fields or open dialogs, except the preserved Ctrl+S behavior',()=>{
  const app=editorHarness();for(const key of [' ','e','t','Tab','c','ArrowLeft','Home','[','l','f','g','m','1','ArrowUp','?']){const event=keyEvent(key,{target:{closest:()=>({})}});assert.equal(app.api.handleKeyDown(event),false,key);assert.equal(event.prevented,undefined);}
  app.get('#json-dialog').showModal();for(const key of [' ','e','Tab','?'])assert.equal(app.api.handleKeyDown(keyEvent(key)),false);app.get('#json-dialog').close();
  const blocked=keyEvent('e',{ctrlKey:true,target:{closest:()=>({})}});assert.equal(app.api.handleKeyDown(blocked),false);assert.equal(blocked.prevented,undefined);
});
test('keyboard transport, mode, emit, clearing and timeline navigation use their real actions',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter');recipe.nodes.push({...plain(emitter),id:'later',timing:{start:.7,duration:.1,mode:'burst',count:3}});app.api.configure({project:recipe,mode:'emu',selectedId:emitter.id});
  app.api.handleKeyDown(keyEvent('Tab'));assert.equal(app.api.getPreview().mode,'free');app.api.handleKeyDown(keyEvent('e'));assert.equal(app.emulatorCalls.filter(call=>call.action==='emit').at(-1).id,emitter.id);
  app.api.handleKeyDown(keyEvent('E',{shiftKey:true}));assert.equal(app.emulatorCalls.filter(call=>call.action==='emit').at(-1).id,'later');app.api.handleKeyDown(keyEvent('c'));assert.equal(app.emulatorCalls.at(-1).action,'clearParticles');
  app.api.handleKeyDown(keyEvent(' '));assert.equal(app.emulatorCalls.at(-1).action,'pause');app.api.handleKeyDown(keyEvent(' ',{shiftKey:true}));assert.equal(app.emulatorCalls.at(-1).action,'stop');
  app.api.handleKeyDown(keyEvent('ArrowRight'));assert.ok(Math.abs(app.api.getPreview().time-1/30)<1e-9);app.api.handleKeyDown(keyEvent('ArrowRight',{shiftKey:true}));assert.ok(Math.abs(app.api.getPreview().time-(1/30+.1))<1e-9);
  app.api.handleKeyDown(keyEvent('Home'));assert.equal(app.api.getPreview().time,0);app.api.handleKeyDown(keyEvent(']'));assert.equal(app.api.getPreview().time,.7);app.api.handleKeyDown(keyEvent('['));assert.equal(app.api.getPreview().time,0);app.api.handleKeyDown(keyEvent('End'));assert.equal(app.api.getPreview().time,recipe.duration);
});
test('keyboard selection, framing, view toggles, background presets, looping and help use real state',()=>{
  const app=editorHarness(),recipe=app.api.getProject(),emitter=recipe.nodes.find(node=>node.class==='ParticleEmitter');app.api.configure({mode:'emu',selectedId:emitter.id});
  app.api.handleKeyDown(keyEvent('ArrowUp',{altKey:true}));assert.equal(app.api.getPreview().selectedId,emitter.parent);app.api.handleKeyDown(keyEvent('ArrowDown'));assert.equal(app.api.getPreview().selectedId,emitter.id);app.api.handleKeyDown(keyEvent('ArrowUp'));assert.equal(app.api.getPreview().selectedId,emitter.parent);
  app.api.handleKeyDown(keyEvent('f'));assert.ok(app.emulatorCalls.at(-1).ids.includes(emitter.id));app.api.handleKeyDown(keyEvent('F',{shiftKey:true}));assert.equal(app.emulatorCalls.at(-1).ids,undefined);
  app.api.handleKeyDown(keyEvent('g'));assert.equal(app.get('#emu-ground').checked,true);app.api.handleKeyDown(keyEvent('m'));assert.equal(app.get('#emu-dummy').checked,true);
  for(const key of ['1','2','3','4','5'])app.api.handleKeyDown(keyEvent(key));assert.equal(app.get('#emu-background').value,'roblox');assert.deepEqual(plain(app.emulatorCalls.at(-1).value),{background:'roblox'});
  app.api.handleKeyDown(keyEvent('l'));assert.equal(app.api.getProject().loop,true);app.api.handleKeyDown(keyEvent('?'));assert.equal(app.get('#shortcuts-dialog').open,true);assert.equal(app.get('#shortcuts-list').children.length,12);
});
test('clipboard JSON copies descendants and animation tracks, then remaps IDs when pasted into another project',async()=>{
  const app=editorHarness(),source=app.api.makeTemplate('trail');app.api.configure({project:source,mode:'emu',selectedId:source.nodes[0].id});await app.api.copySelection();const copied=JSON.parse(app.clipboard.text);assert.equal(copied.nodes.length,source.nodes.length);assert.equal(copied.animations.length,1);
  const target=app.api.makeTemplate('empty');app.api.configure({project:target});await app.api.pasteSelection();const result=app.api.getProject();assert.equal(result.nodes.length,source.nodes.length);assert.equal(result.animations.length,1);assert.ok(result.nodes.every(node=>!source.nodes.some(old=>old.id===node.id)));assert.ok(result.nodes.some(node=>node.id===result.animations[0].node));assert.deepEqual(plain(app.api.validateProject(result)),plain(result));
});
test('clipboard keeps Beam attachment references and safely remaps conflicting parameter names across projects',async()=>{
  const app=editorHarness(),recipe=app.api.makeTemplate('beam'),beam=recipe.nodes.find(node=>node.class==='Beam');app.api.configure({project:recipe,mode:'emu',selectedId:beam.id});await app.api.copySelection();app.api.configure({project:app.api.makeTemplate('empty')});await app.api.pasteSelection();
  let result=app.api.getProject(),copy=result.nodes.find(node=>node.class==='Beam');for(const property of ['Attachment0','Attachment1'])assert.equal(result.nodes.find(node=>node.id===copy.properties[property]).class,'Attachment');
  const effect=app.api.makeTemplate('impact'),emitter=effect.nodes.find(node=>node.class==='ParticleEmitter');effect.params={radius:{default:16}};emitter.scaleWith={Size:'radius'};app.api.configure({project:effect,selectedId:effect.nodes[0].id});await app.api.copySelection();const target=app.api.makeTemplate('empty');target.params={radius:{default:3}};app.api.configure({project:target});await app.api.pasteSelection();result=app.api.getProject();copy=result.nodes.find(node=>node.class==='ParticleEmitter');assert.equal(copy.scaleWith.Size,'radius_copie1');assert.equal(result.params.radius.default,3);assert.equal(result.params.radius_copie1.default,16);
});
test('Ctrl shortcuts preserve save, duplicate and history, and export the requested Roblox file format',async()=>{
  const app=editorHarness(),recipe=app.api.getProject();app.api.configure({mode:'emu',selectedId:recipe.nodes[0].id});
  app.api.handleKeyDown(keyEvent('d',{ctrlKey:true}));assert.equal(app.api.getProject().nodes.length,recipe.nodes.length*2);app.api.handleKeyDown(keyEvent('z',{ctrlKey:true}));assert.equal(app.api.getProject().nodes.length,recipe.nodes.length);app.api.handleKeyDown(keyEvent('z',{ctrlKey:true,shiftKey:true}));assert.equal(app.api.getProject().nodes.length,recipe.nodes.length*2);
  app.api.handleKeyDown(keyEvent('z',{ctrlKey:true}));app.api.handleKeyDown(keyEvent('y',{ctrlKey:true}));assert.equal(app.api.getProject().nodes.length,recipe.nodes.length*2);
  app.api.handleKeyDown(keyEvent('s',{ctrlKey:true,target:{closest:()=>({})}}));await flush();assert.ok(app.calls.some(call=>call.url==='/api/project'));
  for(const shiftKey of [false,true]){app.api.handleKeyDown(keyEvent('e',{ctrlKey:true,shiftKey}));await flush();await flush();const link=app.get('body').children.at(-1);assert.ok(link,app.get('#status-text').textContent);assert.ok(link.clicked);assert.match(link.href,/^blob:/);assert.match(link.download,shiftKey?/\.lua$/:/\.rbxmx$/);}
});

function localMeshRecipe(){
  const mesh={version:1,positions:[-.5,-.5,0,.5,-.5,0,0,.5,0],normals:[0,0,1,0,0,1,0,0,1],uvs:[0,1,1,1,.5,0],indices:[0,1,2],source:{name:'slash.obj',format:'obj',sha256:'a'.repeat(64),dimensions:[2,2,0]}};
  return {version:1,name:'OBJ editor',duration:1,nodes:[{id:'slash',class:'MeshPart',parent:null,name:'Slash',properties:{Size:[2,2,.001],Transparency:0,MeshId:''}}],animations:[],
    editor:{version:1,meshes:{slash:mesh},curves:{'slash::Size':{version:1,mode:'linear',note:'authored curve'}}}};
}

test('OBJ editor metadata follows duplicate/delete/undo and clipboard ID remapping across projects',async()=>{
  const app=editorHarness(),original=localMeshRecipe();app.api.configure({project:original,mode:'emu',selectedId:'slash'});
  app.api.handleKeyDown(keyEvent('d',{ctrlKey:true}));let result=plain(app.api.getProject());const copy=result.nodes.find(node=>node.id!=='slash');
  assert.equal(Object.keys(result.editor.meshes).length,2);assert.deepEqual(result.editor.meshes[copy.id],original.editor.meshes.slash);
  assert.ok(result.editor.curves[copy.id+'::Size']);assert.ok(result.editor.curves['slash::Size']);
  app.api.handleKeyDown(keyEvent('Delete'));result=plain(app.api.getProject());assert.equal(result.nodes.length,1);assert.deepEqual(Object.keys(result.editor.meshes),['slash']);assert.deepEqual(Object.keys(result.editor.curves),['slash::Size']);
  app.api.handleKeyDown(keyEvent('z',{ctrlKey:true}));assert.equal(Object.keys(plain(app.api.getProject()).editor.meshes).length,2);
  app.api.configure({project:original,selectedId:'slash'});await app.api.copySelection();const payload=JSON.parse(app.clipboard.text);assert.deepEqual(payload.editor.meshes.slash,original.editor.meshes.slash);
  app.api.configure({project:app.api.makeTemplate('empty')});await app.api.pasteSelection();result=plain(app.api.getProject());const pasted=result.nodes[0];assert.notEqual(pasted.id,'slash');assert.deepEqual(Object.keys(result.editor.meshes),[pasted.id]);assert.ok(result.editor.curves[pasted.id+'::Size']);
  app.api.handleKeyDown(keyEvent('s',{ctrlKey:true}));await flush();const saved=app.calls.filter(call=>call.url==='/api/project').at(-1).body;
  assert.deepEqual(saved.editor.meshes,result.editor.meshes,'JSON save preserves preview geometry');
  const malformed=JSON.parse(app.clipboard.text);malformed.editor.meshes.slash.indices[0]=99;app.clipboard.text=JSON.stringify(malformed);const before=plain(app.api.getProject());await app.api.pasteSelection();assert.deepEqual(plain(app.api.getProject()),before);assert.match(app.get('#status-text').textContent,/Indices/);
});

test('a refused native export shows its reason and never downloads an error as a Roblox file',async()=>{
  const app=editorHarness();app.deny('export');app.api.configure({mode:'emu'});app.api.handleKeyDown(keyEvent('e',{ctrlKey:true}));await flush();await flush();
  assert.match(app.get('#status-text').textContent,/MeshId Roblox/);assert.equal(app.created.length,0);assert.equal(app.get('body').children.length,0);
});
test('native focus warning requires an explicit inactive viewport signal while playback is active',async()=>{
  const app=editorHarness();app.api.configure({status:{connected:true,last_result:{playing:true}}});
  for(const [signal,hidden]of [[false,false],[true,true],[undefined,true]]){app.frame({...freshFrame(),...(signal===undefined?{}:{window_focused:signal})});await app.api.pollNativeFrame();assert.equal(app.get('#native-focus-warning').hidden,hidden);}
  app.api.configure({status:{connected:true,last_result:{playing:false}}});app.frame({...freshFrame(),window_focused:false});await app.api.pollNativeFrame();assert.equal(app.get('#native-focus-warning').hidden,true,'an inactive paused/stopped preview does not warn');
  app.api.configure({status:{connected:true,last_result:{playing:true}}});app.frame({enabled:false,window_focused:false,frame:null});await app.api.pollNativeFrame();assert.equal(app.get('#native-focus-warning').hidden,true,'capture must be enabled');
});

test('native activation applies the effect before requesting capture, so permission cannot consume its lifetime',async()=>{
  const app=editorHarness();await app.api.startNativePreview();
  assert.deepEqual(app.calls.filter(c=>c.url==='/api/preview').map(c=>c.body.action),['apply','preview_start']);
  const apply=app.calls.find(c=>c.body?.action==='apply');assert.ok(apply.body.project.nodes.some(n=>n.class==='ParticleEmitter'));assert.equal(apply.body.time,undefined);
  assert.ok(!app.get('#native-view').classList.contains('hidden'));assert.match(app.get('#native-preview-message').textContent,/capture/);
  assert.ok(app.timers.some(t=>t.ms===400),'Frame polling is scheduled after activation');
});
test('legacy bridge opens upgrade guidance without applying or enqueueing unsupported capture actions',async()=>{
  const app=editorHarness();const status={connected:true,studio:'QA Studio',bridge_update_required:true,bridge_version:'1'};app.status(status);app.api.configure({status});await app.api.startNativePreview();
  assert.equal(app.calls.filter(c=>c.url==='/api/preview').length,0,'An incompatible bridge must never receive apply or preview_start');
  assert.equal(app.get('#connection-dialog').open,true);assert.match(app.get('#native-preview-message').textContent,/ancien|Redémarrez|Dataky FX/i);
  assert.ok(app.calls.some(c=>c.url==='/api/runtime'),'The real connection drawer loads current bootstrap guidance');
});
test('temporary command-bar bridge without capture permission guides plugin connection without native commands',async()=>{
  const app=editorHarness();const status={connected:true,studio:'QA Studio',bridge_update_required:false,bridge_version:'2',bridge_capabilities:{capture_context:'command_bar'},preview:{permission:false}};app.status(status);app.api.configure({status});await app.api.startNativePreview();
  assert.equal(app.calls.filter(c=>c.url==='/api/preview').length,0,'A temporary connection cannot request permission through an unsupported context');
  assert.equal(app.get('#connection-dialog').open,true);assert.match(app.get('#native-preview-message').textContent,/temporaire|plugin Dataky FX|bouton Connexion/i);
  assert.ok(app.calls.some(c=>c.url==='/api/runtime'));
});
test('temporary bridge with an existing capture grant remains usable',async()=>{
  const app=editorHarness();app.api.configure({status:{connected:true,bridge_update_required:false,bridge_capabilities:{capture_context:'command_bar'},preview:{permission:true}}});await app.api.startNativePreview();
  assert.deepEqual(app.calls.filter(c=>c.url==='/api/preview').map(c=>c.body.action),['apply','preview_start']);assert.notEqual(app.get('#connection-dialog').open,true);
});
test('a fresh frame fetches the matching PNG and updates native image, class, tools and caption',async()=>{
  const app=editorHarness();app.frame(freshFrame(7));await app.api.pollNativeFrame();
  assert.equal(app.get('#native-frame').src,'blob:dataky-1');assert.equal(app.get('#native-frame').hidden,false);assert.equal(app.get('#studio-video').hidden,true);
  assert.ok(app.get('#native-view').classList.contains('has-native-frame'));assert.ok(!app.get('#video-tools').classList.contains('hidden'));
  assert.match(app.get('#native-frame-status').textContent,/Roblox · 0\.75 s · 960 × 540/);assert.equal(app.api.getSequence(),7);
  const before=app.calls.length;await app.api.pollNativeFrame();assert.equal(app.calls.length,before+1,'Same sequence only refreshes metadata; PNG is reused');
  app.frame(freshFrame(8));await app.api.pollNativeFrame();app.get('#native-frame').onload();assert.ok(app.revoked.includes('blob:dataky-1'),'Previous image is released after replacement loads');
});
test('capture refusal clears any previous native frame and exposes the Studio error',async()=>{
  const app=editorHarness();app.frame(freshFrame());await app.api.pollNativeFrame();app.frame({enabled:false,error:'Capture refusée par Studio',frame:null});await app.api.pollNativeFrame();
  assert.equal(app.get('#native-frame').hidden,true);assert.equal(app.get('#native-frame').src,'');assert.ok(!app.get('#native-view').classList.contains('has-native-frame'));
  assert.equal(app.api.getMeta(),null);assert.match(app.get('#native-preview-message').textContent,/refusée/);assert.ok(app.revoked.includes('blob:dataky-1'));
});
test('enabled capture without a frame clears the previous native image',async()=>{
  const app=editorHarness();app.frame(freshFrame());await app.api.pollNativeFrame();app.frame({enabled:true,frame:null});await app.api.pollNativeFrame();
  assert.equal(app.get('#native-frame').hidden,true);assert.equal(app.api.getSequence(),null);assert.equal(app.api.getMeta(),null);
});
test('stale capture clears the previous display and identifies the inactive viewport',async()=>{
  const app=editorHarness();app.frame(freshFrame());await app.api.pollNativeFrame();app.frame(freshFrame(2,{age:4.1}));await app.api.pollNativeFrame();
  assert.equal(app.get('#native-frame').hidden,true,'A stale bitmap must not look like an active native preview');assert.equal(app.api.getMeta(),null);assert.match(app.get('#native-preview-message').textContent,/viewport actif|attente/i);
});
test('stopping native preview clears display and sends preview_stop without a project payload',async()=>{
  const app=editorHarness();app.frame(freshFrame());await app.api.pollNativeFrame();await app.api.stopNativePreview();
  assert.equal(app.get('#native-frame').hidden,true);const stop=app.calls.find(c=>c.body?.action==='preview_stop');assert.ok(stop);assert.equal(stop.body.project,undefined);assert.match(app.get('#native-preview-message').textContent,/arrêté/);
});
test('a frame fetch completing after clear cannot repopulate the removed preview',async()=>{
  const app=editorHarness();let resolve;app.image(()=>new Promise(r=>resolve=r));app.frame(freshFrame());const polling=app.api.pollNativeFrame();
  for(let i=0;i<10&&!resolve;i++)await Promise.resolve();assert.equal(typeof resolve,'function');app.api.clearNativeFrame();resolve(app.response(null));await polling;
  assert.equal(app.get('#native-frame').hidden,true);assert.equal(app.get('#native-frame').src,'');assert.equal(app.created.length,0);
});
test('a refused start does not enqueue capture after a rejected apply command',async()=>{
  const app=editorHarness();app.deny('apply');await app.api.startNativePreview();assert.deepEqual(app.calls.filter(c=>c.url==='/api/preview').map(c=>c.body.action),['apply']);assert.match(app.get('#native-preview-message').textContent,/refusée/);
});
test('permission acknowledgement replays the effect once, after capture becomes available',async()=>{
  const app=editorHarness();await app.api.startNativePreview();app.frame({enabled:true,permission:false,frame:null});await app.api.pollNativeFrame();
  assert.equal(app.calls.filter(c=>c.body?.action==='play').length,0,'Permission pending must not start the short effect');
  app.frame({...freshFrame(),permission:true});await app.api.pollNativeFrame();assert.equal(app.calls.filter(c=>c.body?.action==='play').length,1);
  await app.api.pollNativeFrame();await app.api.pollNativeFrame();assert.equal(app.calls.filter(c=>c.body?.action==='play').length,1,'Repeated frame acknowledgements never restart the effect again');assert.equal(app.get('#native-frame').hidden,false);
});
test('stopping or denying capture cancels the deferred playback intent',async()=>{
  for(const kind of ['stop','deny']){const app=editorHarness();await app.api.startNativePreview();if(kind==='stop')await app.api.stopNativePreview();else{app.frame({enabled:false,permission:false,error:'Capture refusée',frame:null});await app.api.pollNativeFrame();}
    app.frame({...freshFrame(),permission:true});await app.api.pollNativeFrame();assert.equal(app.calls.filter(c=>c.body?.action==='play').length,0,kind+': old activation must not trigger a later replay');}
});
test('numeric graph integration commits the actual baked sequence and matching editor metadata',()=>{
  const app=editorHarness();const project=app.api.getProject(),emitter=app.api.getNode(project.nodes.find(n=>n.class==='ParticleEmitter').id);
  app.api.openSequence(emitter,'Size','NumberSequence',emitter.properties.Size);assert.equal(app.captured.length,1);const options=app.captured[0];assert.equal(options.type,'NumberSequence');assert.equal(options.title,'Size');
  const authored=curves.preset(curves.normalizeNumber([{time:0,value:0},{time:1,value:1}]),'EaseOut');const value=curves.bake(authored);const editor={version:1,mode:'bezier',duration:1,curves:[authored],valueSignature:curves.valueSignature(value,'NumberSequence')};
  options.onApply({value,editor});const saved=plain(app.api.getProject());
  assert.deepEqual(saved.nodes.find(n=>n.id===emitter.id).properties.Size,value);assert.deepEqual(saved.editor.curves[emitter.id+'::Size'],plain(editor));assert.ok(saved.editor.curves[emitter.id+'::Size'].valueSignature);
  assert.doesNotThrow(()=>JSON.parse(JSON.stringify(saved)));assert.ok(app.cache.get('dataky-fx-studio.project.v1'));
});
test('animation graph integration replaces one track with shared baked seconds and persists metadata',()=>{
  const app=editorHarness();const project=app.api.makeTemplate('trail');app.api.configure({project,animationNode:project.animations[0].node});app.get('#animation-property').value='Position';app.get('#animation-json').value=JSON.stringify(project.animations[0].keyframes);
  app.api.openAnimationGraph();const options=app.captured[0];assert.equal(options.type,'animation');assert.equal(options.duration,project.duration);
  const authored=curves.normalizeAnimation(options.value,{duration:project.duration});authored.curves[0]=curves.preset(authored.curves[0],'EaseInOut');const value=curves.bakeAnimation(authored.curves,{duration:project.duration,vector:true});
  const editor={version:1,mode:'bezier',duration:project.duration,curves:authored.curves,valueSignature:curves.valueSignature(value,'animation',project.duration)};options.onApply({value,editor});const saved=plain(app.api.getProject());
  assert.equal(saved.animations.length,1);assert.deepEqual(saved.animations[0].keyframes,value);assert.deepEqual(saved.editor.curves[project.animations[0].node+'::Position'],plain(editor));assert.deepEqual(plain(app.api.validateProject(saved)),saved);
});
