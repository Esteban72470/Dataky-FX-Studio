"""The three actual recipes export, move and clean up; no golden beauty scores."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from fx_export import _lua
from fx_rbxmx import export_rbxmx
from fx_schema import validate_project
from generate_artistry_demos import build_demos

TOOL = Path(__file__).resolve().parent
LUAU = os.environ.get('DATAKY_LUAU') or shutil.which('luau')


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demos = build_demos()

    def test_all_actual_layers_have_purposes_and_native_export_references_resolve(self):
        for demo in self.demos:
            project = validate_project(demo['project'])
            with self.subTest(project=project['id']):
                assigned = [node for layer in demo['brief']['layers'] for node in layer['nodes']]
                self.assertEqual(set(assigned), {n['id'] for n in project['nodes']})
                self.assertEqual(len(assigned), len(set(assigned)))
                root = ET.fromstring(export_rbxmx(project))
                referents = {item.get('referent') for item in root.iter('Item')}
                self.assertTrue(all(ref.text in referents | {'null','nil'} for ref in root.iter('Ref')))
                self.assertTrue(all(a.get('runtime') is True for a in project['animations'] if a['property'] in ('Position','Transparency') and next(n['class'] for n in project['nodes'] if n['id']==a['node']) in ('Part','MeshPart')))

    def test_actual_simulator_moves_every_demo_then_leaves_no_visible_geometry(self):
        script = r'''
const assert=require('node:assert/strict');const E=require('./editor/emulator.js');
const projects=JSON.parse(process.env.DATAKY_DEMO_TESTS);
for(const p of projects){const sim=E.createSimulation(p,{seed:1});
 const frames=[.1,p.duration*.4,p.duration*.65].map(t=>{sim.seek(t);return E.buildFrame(sim,p.camera)});
 assert.ok(frames.some(f=>f.parts.length>0||f.vertices>0),p.name+' must have visible geometry');
 sim.seek(p.duration);const last=E.buildFrame(sim,p.camera);
 assert.equal(last.parts.length,0,p.name+' parts expire');assert.equal(last.lights.length,0,p.name+' lights expire');
 assert.equal(last.vertices,0,p.name+' particles/beams/trails expire');
 assert.equal(last.placeholders.length,0,p.name+' cannot depend on missing meshes');
}
'''
        result = subprocess.run(['node','-e',script], cwd=TOOL.parent,
                                env={**os.environ,'DATAKY_DEMO_TESTS':json.dumps([d['project'] for d in self.demos])},
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(LUAU, 'Luau CLI absent (DATAKY_LUAU)')
    def test_real_luau_kit_plays_rotated_instances_and_cleans_all_three_demos(self):
        source = (TOOL/'luau_roblox_mock.luau').read_text(encoding='utf-8')
        source += '\nlocal FX=(function()\n'+(TOOL/'fx_kit.lua').read_text(encoding='utf-8')+'\nend)()\n'
        source += 'local recipes='+_lua({str(i): d['project'] for i,d in enumerate(self.demos)})+'\n'
        source += '''
for _,recipe in pairs(recipes) do
 local a=FX.play(recipe,CFrame.new(10,2,3)*CFrame.fromOrientation(0,.8,0),{quality="High"})
 local b=FX.play(recipe,CFrame.new(-4,1,0),{quality="Low",scale=.7})
 assert(a.root~=b.root)
 for i=1,45 do Step(1/60) end
 assert(not a.stopped and not b.stopped)
 for i=1,240 do Step(1/60) end
 assert(a.stopped and b.stopped,"temporary instances must be cleaned")
end
for _,line in ipairs(EVENTS) do assert(not line:match("^WARN"),line) end
print("DEMOS_OK")
'''
        with tempfile.NamedTemporaryFile('w',suffix='.luau',delete=False,encoding='utf-8') as f:
            f.write(source)
            path=Path(f.name)
        try:
            result=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=60)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('DEMOS_OK',result.stdout)


if __name__=='__main__':
    unittest.main()
