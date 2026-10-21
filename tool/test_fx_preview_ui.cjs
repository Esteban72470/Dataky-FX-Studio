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
    constructor(selector){this.selector=selector;this.hidden=true;this.value='';this.checked=false;this.children=[];this.attributes={};this.dataset={};this.src='';this.textContent='';this.innerHTML='';this.locals=new Map();const classes=new Set();this.classList={add:(...names)=>names.forEach(n=>classes.add(n)),remove:(...names)=>names.forEach(n=>classes.delete(n)),contains:name=>classes.has(name),toggle:(name,value)=>{const enabled=value??!classes.has(name);enabled?classes.add(name):classes.delete(name);return enabled;}};}
    append(...items){this.children.push(...items);}
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
    if(url.startsWith('/api/project/'))return response({...plain(schemaFixture()),id:'loaded-project'});
    throw new Error('Unexpected integration request: '+url);
  };
  const filename=path.resolve(__dirname,'../editor/app.js');const original=fs.readFileSync(filename,'utf8');
  const marker='  if(!Array.isArray(project.animations))project.animations=[];';assert.equal(original.split(marker).length,2,'App startup marker is unique');
  const source=original.replace(marker,`
  renderAll=()=>{};renderTimeline=()=>{};drawScene=()=>{};
  globalThis.__PreviewTest={startNativePreview,pollNativeFrame,stopNativePreview,clearNativeFrame,openSequence,openAnimationGraph,loadProject,refreshStatus,validateProject,
    getProject:()=>clone(project),getNode:nodeById,getMeta:()=>clone(nativeFrameMeta),getSequence:()=>nativeFrameSequence,
    configure:settings=>{if(settings.project)project=clone(settings.project);if(settings.connected!==undefined)nativeStatus={connected:settings.connected};if(settings.status)nativeStatus=clone(settings.status);if(settings.mode)viewportMode=settings.mode;if(settings.animationNode)animationNode=settings.animationNode;},
    makeTemplate:template};
  return;
${marker}`);
  const captured=[];const window={DatakyCurves:{open:options=>{captured.push(options);return{};}}};
  const sandbox={window,document:{querySelector:get,querySelectorAll:()=>[],createElement:tag=>new Element(tag)},console,crypto,Blob,fetch,
    localStorage:{getItem:key=>cache.get(key)||null,setItem:(key,value)=>cache.set(key,value)},
    URL:{createObjectURL:blob=>{assert.ok(blob instanceof Blob);const url='blob:dataky-'+(created.length+1);created.push(url);return url;},revokeObjectURL:url=>revoked.push(url)},
    setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){},setInterval(){throw new Error('Unintercepted startup timer');},confirm:()=>true};
  vm.createContext(sandbox);vm.runInContext(source,sandbox,{filename,timeout:3000});const api=sandbox.__PreviewTest;assert.ok(api);const fixture=api.makeTemplate('impact');
  function schemaFixture(){return fixture;}
  api.configure({project:fixture,connected:true,mode:'native'});
  return{api,get,calls,timers,captured,created,revoked,cache,
    frame:value=>{frameState=value;},status:value=>{status=value;},deny:value=>{denyAction=value;},image:value=>{imageResponder=value;},response};
}

const freshFrame=(sequence=1,extra={})=>({enabled:true,error:null,frame:{sequence,age:.1,time:.75,width:960,height:540,...extra}});

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
