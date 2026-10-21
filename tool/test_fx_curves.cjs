'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const vm=require('node:vm');
const math=require(path.join(__dirname,'../editor/curves.js'));
const linear=()=>math.normalizeNumber([{time:0,value:0},{time:1,value:1}]);
const near=(a,b,epsilon=1e-6)=>assert.ok(Math.abs(a-b)<=epsilon,`${a} ≈ ${b}`);

test('linear interpolation remains linear and exports only two native endpoints',()=>{
  const curve=linear();for(let i=0;i<=20;i++)near(math.evaluate(curve,i/20),i/20);
  assert.deepEqual(math.bake(curve),[{time:0,value:0,envelope:0},{time:1,value:1,envelope:0}]);
});
test('ease presets evaluate cubic time, preserve endpoints, and change intermediate motion',()=>{
  const ease=math.preset(linear(),'EaseIn');near(math.evaluate(ease,0),0);near(math.evaluate(ease,1),1);
  assert.ok(math.evaluate(ease,.5)<.5);const out=math.preset(linear(),'EaseOut');assert.ok(math.evaluate(out,.5)>.5);
  near(math.evaluate(math.preset(linear(),'EaseInOut'),.5),.5);
});
test('adaptive sampling exports at most twenty finite ordered native-compatible points',()=>{
  const curve=math.preset(linear(),'EaseInOut');const baked=math.bake(curve,{tolerance:0});assert.equal(baked.length,20);
  assert.equal(baked[0].time,0);assert.equal(baked.at(-1).time,1);
  for(let i=0;i<baked.length;i++){assert.ok(Number.isFinite(baked[i].value));if(i)assert.ok(baked[i].time>baked[i-1].time);}
  for(let i=0;i<=200;i++){const t=i/200;near(math.linearAt(baked,t),math.evaluate(curve,t),.008);}
});
test('control handles cannot reverse time even when dragged past each other',()=>{
  const points=linear();points[0].out={x:.99,y:1};points[1].in={x:-.99,y:-1};const controls=math.segmentControls(...points);
  assert.ok(controls.x1<=controls.x2);let previous=-Infinity;
  for(let i=0;i<=100;i++){const x=math.bezier(controls.x0,controls.x1,controls.x2,controls.x3,i/100);assert.ok(x>=previous);previous=x;}
  for(let i=0;i<=100;i++)assert.ok(Number.isFinite(math.evaluate(points,i/100)));
});
test('definition bounds clamp Bezier handles and baked values while invalid endpoints fail',()=>{
  const curve=linear();curve[0].out.y=100;curve[1].in.y=-100;
  const baked=math.bake(curve,{definition:{min:0,max:1}});for(const point of baked)assert.ok(point.value>=0&&point.value<=1);
  assert.throws(()=>math.normalizeNumber([{time:0,value:-1},{time:1,value:1}],{definition:{min:0}}),/compris/);
});
test('envelopes interpolate without becoming negative',()=>{
  const curve=math.normalizeNumber([[0,1,.2],[.4,3,.8],[1,0,.1]]);const baked=math.bake(math.preset(curve,'EaseOut'));
  near(baked[0].envelope,.2);near(baked.at(-1).envelope,.1);assert.ok(baked.every(p=>p.envelope>=0));
  const exact=baked.find(p=>p.time===.4);assert.ok(exact);near(exact.envelope,.8);
});
test('normalization accepts both historical arrays and canonical objects, rejects unsafe numeric values',()=>{
  assert.equal(math.normalizeNumber([[0,1,0],[1,0,0]]).length,2);
  for(const value of [NaN,Infinity,-Infinity,'1',null])assert.throws(()=>math.normalizeNumber([{time:0,value},{time:1,value:1}]));
  assert.throws(()=>math.normalizeNumber([{time:0,value:1},{time:0,value:2}]),/distinct/);
  assert.throws(()=>math.normalizeNumber([{time:.1,value:1},{time:1,value:2}]),/bornes/);
  assert.throws(()=>math.normalizeNumber(Array.from({length:21},(_,i)=>({time:i/20,value:i}))),/20/);
});
test('color gradients validate normalized RGB and interpolate true color stops',()=>{
  const gradient=math.normalizeColor([[0,[1,0,0]],[.5,[0,1,0]],[1,[0,0,1]]]);
  assert.deepEqual(math.sampleColor(gradient,.25),[.5,.5,0]);assert.deepEqual(math.sampleColor(gradient,.75),[0,.5,.5]);
  assert.throws(()=>math.normalizeColor([[0,[255,0,0]],[1,[0,0,1]]]),/compris/);
  assert.throws(()=>math.normalizeColor([[.1,[1,0,0]],[1,[0,0,1]]]),/commence/);
});
test('vector animation samples all channels at shared seconds and extends constant domain edges',()=>{
  const input=[{time:.5,value:[0,1,2]},{time:2,value:[4,3,0]}];
  const model=math.normalizeAnimation(input,{duration:3});assert.equal(model.vector,true);assert.equal(model.curves.length,3);
  assert.equal(model.curves[0][0].time,0);assert.equal(model.curves[0].at(-1).time,1);
  model.curves[0]=math.preset(model.curves[0],'EaseInOut');
  const baked=math.bakeAnimation(model.curves,{duration:3,vector:true});
  assert.equal(baked[0].time,0);assert.equal(baked.at(-1).time,3);assert.deepEqual(baked[0].value,[0,1,2]);assert.deepEqual(baked.at(-1).value,[4,3,0]);
  assert.ok(baked.length<=20);for(const frame of baked)assert.equal(frame.value.length,3);
});
test('burst and fade are portable native recipes and pure helpers do not mutate inputs',()=>{
  const input=linear(),snapshot=JSON.stringify(input);const burst=math.preset(input,'Burst'),fade=math.preset(input,'Fade');
  assert.equal(JSON.stringify(input),snapshot);assert.ok(burst.some(p=>p.value===1));assert.equal(burst.at(-1).value,0);assert.equal(fade[0].value,1);assert.equal(fade.at(-1).value,0);
  for(const points of [burst,fade])assert.ok(math.bake(points).length<=20);
});
test('metadata signatures recognize historical and canonical points but invalidate changed recipes',()=>{
  const array=[[0,1,0],[1,0,.2]],canonical=[{time:0,value:1,envelope:0},{time:1,value:0,envelope:.2}];
  assert.equal(math.valueSignature(array,'NumberSequence'),math.valueSignature(canonical,'NumberSequence'));
  canonical[1].value=.1;assert.notEqual(math.valueSignature(array,'NumberSequence'),math.valueSignature(canonical,'NumberSequence'));
});
function componentHarness(){
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.dataset={};this.events={};this.selectors=new Map();this.hidden=false;this.open=false;this.value='';const classes=new Set();this.classList={toggle:(name,value)=>{const enabled=value??!classes.has(name);enabled?classes.add(name):classes.delete(name);},add:name=>classes.add(name),remove:name=>classes.delete(name)};this.style={setProperty(){}};}
    set innerHTML(html){this._html=html;this.children=[];if(this.tagName==='dialog')for(const match of html.matchAll(/<([a-z]+)([^>]*)>/g)){const node=new Element(match[1]);for(const attribute of match[2].matchAll(/([a-z-]+)="([^"]*)"/g)){node.attributes[attribute[1]]=attribute[2];if(attribute[1]==='class')for(const name of attribute[2].split(' '))this.selectors.set('.'+name,node);if(attribute[1]==='id')this.selectors.set('#'+attribute[2],node);}this.children.push(node);}}
    get innerHTML(){return this._html||'';}
    querySelector(selector){return this.selectors.get(selector)||null;}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=[...nodes];}
    setAttribute(key,value){this.attributes[key]=String(value);}
    removeAttribute(key){delete this.attributes[key];}
    addEventListener(name,fn){this.events[name]=fn;}
    showModal(){this.open=true;}
    close(){this.open=false;this.events.close?.();}
    focus(){}
    select(){}
  }
  const document={head:new Element('head'),body:new Element('body'),createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)};
  const window={};const sandbox={window,document,navigator:{clipboard:{writeText:async()=>{},readText:async()=>''}},setTimeout:()=>0,console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../editor/curves.js'),'utf8'),sandbox);
  return{api:window.DatakyCurves,document,get dialog(){return document.body.children[0];}};
}
test('component opens a numeric curve, applies a preset, emits portable value and restores metadata',()=>{
  const app=componentHarness();let emitted;const handle=app.api.open({type:'NumberSequence',value:[[0,0,0],[1,1,0]],onApply:result=>emitted=result,title:'Taille'});
  assert.equal(app.dialog.open,true);assert.equal(app.dialog.querySelector('#dc-title').textContent,'Taille');
  const presets=app.dialog.querySelector('.dc-presets').children;presets[1].onclick();
  assert.ok(handle.getValue().length>2);app.dialog.querySelector('.dc-apply').onclick();
  assert.ok(emitted.value.length<=20);assert.equal(emitted.editor.mode,'bezier');assert.equal(app.dialog.open,false);
  const restored=app.api.open({type:'NumberSequence',value:emitted.value,editor:emitted.editor});
  assert.deepEqual(JSON.parse(JSON.stringify(restored.getValue())),JSON.parse(JSON.stringify(emitted.value)));
  assert.match(app.dialog.querySelector('.dc-point-title').textContent,/Point 1 \/ 2/);
});
test('component rejects malformed color imports without replacing the existing gradient',()=>{
  const app=componentHarness();const handle=app.api.open({type:'ColorSequence',value:[[0,[1,0,0]],[1,[0,0,1]]]});const before=JSON.stringify(handle.getValue());
  app.dialog.querySelector('.dc-json').value='[{"time":0,"value":[255,0,0]},{"time":1,"value":[0,0,1]}]';app.dialog.querySelector('.dc-json-import').onclick();
  assert.match(app.dialog.querySelector('.dc-error').textContent,/compris/);assert.equal(JSON.stringify(handle.getValue()),before);assert.equal(app.dialog.open,true);
});
