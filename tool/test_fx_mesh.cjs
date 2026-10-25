'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const E = require('../editor/emulator.js');
const R = require('./fx_render.cjs');

function recipe() {
  const mesh = {version:1, positions:[-.5,-.5,0,.5,-.5,0,.5,.5,0,-.5,.5,0], normals:[0,0,1,0,0,1,0,0,1,0,0,1],
    uvs:[0,1,1,1,1,0,0,0], indices:[0,1,2,0,2,3], source:{name:'square.obj',format:'obj',sha256:'a'.repeat(64),dimensions:[4,4,0]}};
  return {version:1,name:'Mesh probe',duration:1,environment:{background:'#000000'},camera:{position:[0,0,6],target:[0,0,0],fov:50},
    nodes:[{id:'mesh',class:'MeshPart',properties:{Position:[0,0,0],Orientation:[0,0,0],Size:[4,4,.001],Color:[1,0,0],Material:'Neon',Transparency:0,DoubleSided:false,MeshId:''}}],
    animations:[],editor:{version:1,meshes:{mesh}}};
}

test('transparent imported mesh picking uses triangles rather than the empty bounds', () => {
  const project=recipe();project.nodes[0].properties.Transparency=1;
  project.editor.meshes.mesh.indices=[0,1,3];
  const sim=E.createSimulation(project);
  assert.equal(E.pickPart(sim,project.camera,270,290,640,480),'mesh');
  assert.equal(E.pickPart(sim,project.camera,370,190,640,480),null,'empty half of the mesh bounds remains clickable through');
});

test('real WebGL loads authored local PNG pixels and alpha bounds, without replacing them by a procedural dot', {timeout:30000}, async t=>{
  let playwright;try{playwright=R.loadPlaywright();}catch(error){return t.skip(error.message);}
  const browser=await playwright.chromium.launch({args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try{
    const page=await browser.newPage(),requests=[];let png;
    await page.route('http://texture.test/**',route=>{
      const pathname=new URL(route.request().url()).pathname;requests.push(pathname);
      if(pathname==='/')return route.fulfill({contentType:'text/html',body:'<canvas id="c" width="128" height="128"></canvas>'});
      if(pathname==='/library/source/vfx/enuma-elish/textures/mask.png')return route.fulfill({contentType:'image/png',body:png});
      return route.fulfill({status:404,body:''});
    });
    await page.goto('http://texture.test/');await page.addScriptTag({path:path.resolve(__dirname,'../editor/emulator.js')});
    const data=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=32;const ctx=c.getContext('2d');ctx.fillStyle='#ff0000';ctx.fillRect(0,0,16,32);return c.toDataURL('image/png').split(',')[1];});png=Buffer.from(data,'base64');
    const result=await page.evaluate(async input=>{
      const E=window.DatakyEmulator,uri='rbxasset://textures/dataky-local/enuma-elish/mask.png';
      const project=structuredClone(input);project.nodes[0].properties.Color=[1,1,1];project.nodes[0].properties.TextureID=uri;
      const renderer=E.createRenderer(document.getElementById('c'),{preserveDrawingBuffer:true});await renderer.preload(project);renderer.render(E.createSimulation(project),project.camera,{ground:false});
      const pixel=x=>{const p=new Uint8Array(4);renderer.gl.readPixels(x,64,1,1,renderer.gl.RGBA,renderer.gl.UNSIGNED_BYTE,p);return [...p];};const left=pixel(40),right=pixel(88);
      const bounds=await E.textureAlphaBounds([{nodes:[{class:'ParticleEmitter',properties:{Texture:uri}}]}]);
      project.nodes[0].properties.TextureID='rbxasset://textures/dataky-local/enuma-elish/missing.png';await renderer.preload(project);renderer.render(E.createSimulation(project),project.camera,{ground:false});
      return{left,right,bounds:bounds(uri,[[0,0],[1,0],[0,1],[1,1]]),missing:pixel(64),warnings:[...renderer.warnings]};
    },recipe());
    assert.deepEqual(result.left.slice(0,3),[255,0,0]);assert.deepEqual(result.right.slice(0,3),[0,0,0]);
    assert.ok(result.bounds.max[0]<.6);assert.deepEqual(result.missing.slice(0,3),[0,0,0]);assert.ok(result.warnings.some(w=>w.includes('n’est pas affichée')));
    assert.ok(requests.includes('/library/source/vfx/enuma-elish/textures/mask.png'));
  }finally{await browser.close();}
});

test('real WebGL selection reveals transparent box, sphere, cylinder and imported mesh only in editor overlay', {timeout:45000}, async t => {
  let playwright;try{playwright=R.loadPlaywright();}catch(error){return t.skip(error.message);}
  const browser=await playwright.chromium.launch({args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try {
    const page=await browser.newPage({viewport:{width:500,height:400}});
    await page.setContent('<canvas id="c" width="128" height="128" style="width:128px;height:128px"></canvas>');
    await page.addScriptTag({path:path.resolve(__dirname,'../editor/emulator.js')});
    const result=await page.evaluate(async meshRecipe=>{
      const E=window.DatakyEmulator,canvas=document.getElementById('c'),renderer=E.createRenderer(canvas,{preserveDrawingBuffer:true});
      const count=()=>{const pixels=new Uint8Array(128*128*4);renderer.gl.readPixels(0,0,128,128,renderer.gl.RGBA,renderer.gl.UNSIGNED_BYTE,pixels);let cyan=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i+1]>160&&pixels[i+2]>130&&pixels[i]<130)cyan++;return cyan;};
      const counts={};
      for(const shape of ['Block','Ball','Cylinder','ImportedMesh']) {
        const project=shape==='ImportedMesh'?structuredClone(meshRecipe):{version:1,name:shape,duration:1,environment:{background:'#000000'},camera:{position:[0,0,6],target:[0,0,0],fov:50},nodes:[{id:'p',class:'Part',properties:{Size:[4,4,4],Transparency:1,Shape:shape}}],animations:[]};
        project.nodes[0].properties.Transparency=1;
        const before=JSON.stringify(project),sim=E.createSimulation(project),id=project.nodes[0].id;
        renderer.render(sim,project.camera,{ground:false});const hidden=count();
        renderer.render(sim,project.camera,{ground:false,selectedIds:[id]});const selected=count();
        renderer.render(sim,project.camera,{ground:false,selectedIds:[]});const cleared=count();
        counts[shape]={hidden,selected,cleared,unchanged:JSON.stringify(project)===before};
      }
      canvas.remove();const interactive=document.createElement('canvas');interactive.style='width:128px;height:128px';document.body.append(interactive);
      window.selectionLog=[];window.selectionView=E.createView(interactive,{ground:false,onSelect:(id,details)=>{selectionLog.push({id,...details});selectionView.setSelection(id?[id]:[]);}});
      const project={version:1,name:'Click hidden part',duration:1,environment:{background:'#000000'},camera:{position:[0,0,6],target:[0,0,0],fov:50},nodes:[{id:'hidden',class:'Part',properties:{Size:[2,2,2],Transparency:1}}],animations:[]};
      selectionView.setProject(project);window.interactiveCanvas=interactive;
      return counts;
    },recipe());
    for(const [shape,value]of Object.entries(result)){assert.equal(value.hidden,0,shape);assert.ok(value.selected>70,shape+' outline visible');assert.equal(value.cleared,0,shape+' outline clears');assert.ok(value.unchanged,shape+' project preserved');}
    await page.locator('canvas').click({position:{x:64,y:64}});
    const exported=await page.evaluate(async()=>{
      const plain=selectionView.snapshot(),overlay=selectionView.snapshot('image/png',{includeSelection:true});
      async function cyan(src){const image=new Image();image.src=src;await image.decode();const c=document.createElement('canvas');c.width=c.height=128;const ctx=c.getContext('2d');ctx.drawImage(image,0,0);const p=ctx.getImageData(0,0,128,128).data;let n=0;for(let i=0;i<p.length;i+=4)if(p[i+1]>160&&p[i+2]>130&&p[i]<130)n++;return n;}
      return{log:selectionLog,plain:await cyan(plain),overlay:await cyan(overlay)};
    });
    assert.equal(exported.log[0].id,'hidden');assert.equal(exported.plain,0,'export snapshot excludes selection');assert.ok(exported.overlay>70);
    await page.locator('canvas').click({position:{x:2,y:2}});
    assert.equal(await page.evaluate(()=>selectionLog.at(-1).id),null,'clicking empty space clears selection');
  }finally{await browser.close();}
});

test('imported geometry becomes a real solid with animated transform, colour and opacity', () => {
  const project = recipe();
  project.animations = [{node:'mesh',property:'Position',runtime:true,keyframes:[{time:0,value:[0,0,0]},{time:1,value:[3,2,1]}]},
    {node:'mesh',property:'Transparency',runtime:true,keyframes:[{time:0,value:0},{time:1,value:.8}]}];
  const sim = E.createSimulation(project); sim.seek(.5);
  const frame = E.buildFrame(sim, project.camera);
  assert.equal(frame.placeholders.length,0); assert.equal(frame.parts.length,1);
  assert.equal(frame.parts[0].geometry.indices.length,6);
  assert.deepEqual(frame.parts[0].p,[1.5,1,.5]); assert.ok(Math.abs(frame.parts[0].alpha-.6)<1e-8);
  assert.deepEqual(frame.parts[0].size,[4,4,.001]);
  const invalid = recipe(); invalid.editor.meshes.mesh.indices[0]=99;
  assert.throws(()=>E.createSimulation(invalid),/Indices/);
});

test('PingPong flipbook blends adjacent ending frames when reversing', () => {
  const project = recipe(); project.nodes[0].properties.Transparency=1;
  project.nodes.push({id:'e',class:'ParticleEmitter',parent:'mesh',properties:{Lifetime:[2,2],Speed:[0,0],Size:[{time:0,value:1},{time:1,value:1}],
    FlipbookLayout:'Grid2x2',FlipbookMode:'PingPong',FlipbookFramerate:[10,10],Transparency:[{time:0,value:0},{time:1,value:0}]},timing:{start:0,mode:'burst',count:1}});
  const sim = E.createSimulation(project); sim.seek(.35);
  const frame=E.buildFrame(sim,project.camera);
  assert.deepEqual(Array.from(frame.data.slice(3,5)),[0,.5]);
  assert.deepEqual(Array.from(frame.data.slice(5,7)),[.5,.5]);
  assert.ok(Math.abs(frame.data[11]-.5)<1e-6);
});

test('real WebGL mesh pixels verify silhouette, depth, transparency, culling, UV and texture alpha', {timeout:90000}, async t => {
  let playwright;
  try { playwright=R.loadPlaywright(); }
  catch(error) { return t.skip(error.message); }
  const browser=await playwright.chromium.launch({args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
  try {
    const page=await browser.newPage();
    await page.setContent('<canvas id="c" width="128" height="128"></canvas>');
    await page.addScriptTag({path:path.resolve(__dirname,'../editor/emulator.js')});
    const result=await page.evaluate(async original=>{
      const E=window.DatakyEmulator, canvas=document.getElementById('c');
      const tex=document.createElement('canvas');tex.width=tex.height=64;const ctx=tex.getContext('2d');ctx.fillStyle='#00ff00';ctx.fillRect(0,0,32,64);ctx.fillStyle='#ffff00';ctx.fillRect(32,0,32,64);
      const renderer=E.createRenderer(canvas,{preserveDrawingBuffer:true,resolveTexture:()=>[tex.toDataURL()]});
      function draw(project){const sim=E.createSimulation(project);renderer.render(sim,project.camera,{ground:false});const pixel=(x=64,y=64)=>{const out=new Uint8Array(4);renderer.gl.readPixels(x,y,1,1,renderer.gl.RGBA,renderer.gl.UNSIGNED_BYTE,out);return Array.from(out);};return {center:pixel(),left:pixel(40),right:pixel(88),corners:pixel(5,5)};}
      const copy=()=>JSON.parse(JSON.stringify(original));
      const solid=draw(copy());
      const transparent=copy();transparent.nodes[0].properties.Transparency=.5;const alpha=draw(transparent);
      const reversed=copy();reversed.nodes[0].properties.Orientation=[0,180,0];const culled=draw(reversed);reversed.nodes[0].properties.DoubleSided=true;const doubleSided=draw(reversed);
      const occluded=copy();occluded.nodes.push({id:'front',class:'Part',properties:{Position:[0,0,1],Size:[2,2,.1],Material:'Neon',Color:[0,0,1],Transparency:0}});const depth=draw(occluded);
      const textured=copy();textured.nodes[0].properties.Color=[1,1,1];textured.nodes[0].properties.TextureID='rbxassetid://1';await renderer.preload(textured);const uv=draw(textured);
      // An opaque textured mesh must write depth and occlude later particle draws.
      textured.nodes.push({id:'back',class:'Part',properties:{Position:[0,0,-1],Size:[.001,.001,.001],Transparency:1}},
        {id:'e',class:'ParticleEmitter',parent:'back',properties:{Lifetime:[2,2],Speed:[0,0],Texture:'',Size:[{time:0,value:4},{time:1,value:4}],Color:[{time:0,value:[1,0,1]},{time:1,value:[1,0,1]}],Transparency:[{time:0,value:0},{time:1,value:0}]},timing:{start:0,mode:'burst',count:1}});
      const textureDepth=draw(textured);
      const moved=copy();moved.nodes[0].properties.Position=[5,0,0];const translated=draw(moved);
      return {solid,alpha,culled,doubleSided,depth,uv,textureDepth,translated};
    }, recipe());
    const near=(actual,expected)=>expected.forEach((v,i)=>assert.ok(Math.abs(actual[i]-v)<=3,`${actual} expected ${expected}`));
    near(result.solid.center,[255,0,0]); near(result.solid.corners,[0,0,0]);
    near(result.alpha.center,[128,0,0]); near(result.culled.center,[0,0,0]); near(result.doubleSided.center,[255,0,0]);
    near(result.depth.center,[0,0,255]); near(result.uv.left,[0,255,0]); near(result.uv.right,[255,255,0]);
    near(result.textureDepth.left,[0,255,0]);near(result.textureDepth.right,[255,255,0]);near(result.translated.center,[0,0,0]);
  } finally { await browser.close(); }
});
