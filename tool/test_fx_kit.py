"""Independent gameplay kit: execute real Luau against the shared Roblox mock."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from .fx_export import _lua, export_library, write_library
except ImportError:
    from fx_export import _lua, export_library, write_library

TOOL = Path(__file__).resolve().parent
LUAU = os.environ.get("DATAKY_LUAU") or shutil.which("luau")


def sequence(value):
    return [{"time": 0, "value": value, "envelope": 0}, {"time": 1, "value": value, "envelope": 0}]


RECIPE = {
    "version": 1, "name": "Kit", "duration": 0.5,
    "nodes": [
        {"id": "part", "class": "Part", "properties": {"Position": [2, 0, 0], "Size": [2, 1, 1]}},
        {"id": "att", "class": "Attachment", "parent": "part", "properties": {"Position": [0, 1, 0]}},
        {"id": "burst", "class": "ParticleEmitter", "parent": "att",
         "properties": {"Size": sequence(2), "Speed": [4, 6], "Acceleration": [1, 0, 0], "Lifetime": [0.1, 0.2]},
         "timing": {"start": 0, "duration": 0, "mode": "burst", "count": 10}},
        {"id": "stream", "class": "ParticleEmitter", "parent": "att",
         "properties": {"Rate": 20, "Lifetime": [0.1, 0.2]},
         "timing": {"start": 0.1, "duration": 0.2, "mode": "continuous", "count": 1}},
        {"id": "light", "class": "PointLight", "parent": "att", "properties": {"Range": 6, "Brightness": 0},
         "timing": {"start": 0, "duration": 0.4, "mode": "continuous", "count": 1}},
    ],
    "animations": [{"node": "light", "property": "Brightness", "keyframes": [{"time": 0, "value": 0}, {"time": 0.5, "value": 10}]}],
}


class LibraryTests(unittest.TestCase):
    def test_data_library_contains_named_recipes_and_separate_kit(self):
        original = deepcopy(RECIPE)
        with tempfile.TemporaryDirectory() as folder:
            path, kit = write_library({"Muzzle": RECIPE, "Nom à espace": RECIPE}, Path(folder) / "MesEffets.lua")
            source = path.read_text(encoding="utf-8")
            self.assertIn('["Muzzle"]=', source)
            self.assertIn('["Nom à espace"]=', source)
            self.assertEqual(kit.name, "DatakyFXKit.lua")
            self.assertIn("function FX.play", kit.read_text(encoding="utf-8"))
            self.assertNotIn("Instance.new", source)
        self.assertEqual(RECIPE, original)

    def test_empty_names_and_overwriting_kit_are_rejected(self):
        for recipes in ({}, {"": RECIPE}):
            with self.assertRaises(ValueError):
                export_library(recipes)
        with self.assertRaises(ValueError):
            write_library({"A": RECIPE}, "DatakyFXKit.lua")


@unittest.skipUnless(LUAU, "Luau CLI absent (DATAKY_LUAU)")
class KitLuauTests(unittest.TestCase):
    def run_luau(self, checks, recipe=None):
        source = (TOOL / "luau_roblox_mock.luau").read_text(encoding="utf-8")
        source += '\nlocal FX = (function()\n' + (TOOL / "fx_kit.lua").read_text(encoding="utf-8") + '\nend)()\n'
        source += "local R = " + _lua(recipe or RECIPE) + "\n"
        source += "local function near(a,b) assert(math.abs(a-b)<0.00001, tostring(a)..' ~= '..tostring(b)) end\n"
        source += checks + '\nfor _,line in ipairs(EVENTS) do assert(not line:match("^WARN"), line) end\nprint("KIT_OK")\n'
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as handle:
            handle.write(source)
        try:
            result = subprocess.run([LUAU, handle.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("KIT_OK", result.stdout)

    def test_two_instances_rotation_scale_and_move_are_independent(self):
        self.run_luau('''
local h = FX.play(R, CFrame.new(10,0,0) * CFrame.fromOrientation(0,math.pi/2,0), {scale=2, quality="High"})
local other = FX.play(R, CFrame.new(-10,0,0))
local part = h:Part("part")
near(part.Position.X,10); near(part.Position.Z,-4)
near(part.Size.X,4); near(h:Part("att").Position.Y,2)
near(h:Part("burst").Size.Keypoints[1].Value,4)
near(h:Part("burst").Speed.Max,12)
near(h:Part("burst").Acceleration.Z,-2)
near(h:Part("light").Range,12)
h:Move(CFrame.new(30,0,0))
near(part.Position.X,34); near(other:Part("part").Position.X,-8)
h:Stop(); assert(other:Part("part") ~= nil)
other:Stop(); assert(workspace:FindFirstChild("DatakyFX") == nil)
''')

    def test_timeline_animations_and_quality_counts(self):
        self.run_luau('''
local h = FX.play(R, CFrame.new(), {quality="Low", speed=2})
local count = 0
for _,line in ipairs(EVENTS) do if line:match("^EMIT burst") then assert(line:match(" 6$")); count+=1 end end
assert(count == 1)
Step(0.1); assert(h:Part("stream").Enabled); near(h:Part("light").Brightness,4)
Step(0.1); assert(not h:Part("stream").Enabled)
for _=1,10 do Step(0.1) end
assert(h.stopped and h.root.Parent == nil)
''')

    def test_part_orientation_animation_composes_with_move_frame(self):
        recipe = deepcopy(RECIPE)
        recipe["animations"].append({"node": "part", "property": "Orientation", "keyframes": [
            {"time": 0, "value": [0, 0, 0]}, {"time": 0.5, "value": [0, 90, 0]}]})
        self.run_luau('''
local h = FX.play(R,CFrame.fromOrientation(0,math.pi/2,0))
Step(0.25)
local v = h:Part("part").CFrame:VectorToWorldSpace(Vector3.new(1,0,0))
near(v.X,-math.sqrt(0.5)); near(v.Z,-math.sqrt(0.5))
h:Move(CFrame.new(10,0,0))
v = h:Part("part").CFrame:VectorToWorldSpace(Vector3.new(1,0,0))
near(v.X,math.sqrt(0.5)); near(v.Z,-math.sqrt(0.5))
h:Stop()
''', recipe)

    def test_timeline_speed_does_not_shorten_native_particle_lifetime(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"] = recipe["nodes"][:3]
        recipe["nodes"][2]["properties"]["Lifetime"] = [1, 1]
        recipe["animations"] = []
        self.run_luau('''
local h = FX.play(R,CFrame.new(),{speed=10})
Step(0.1); assert(not h.stopped)
Step(0.5); assert(not h.stopped)
Step(0.41); assert(h.stopped)
''', recipe)

    def test_auto_quality_reads_saved_client_quality(self):
        self.run_luau('''
UserSettings = function() return {GameSettings={SavedQualityLevel={Value=3}}} end
local h = FX.play(R,CFrame.new(),{quality="Auto"})
local emitted=false
for _,line in ipairs(EVENTS) do if line:match("^EMIT burst") then assert(line:match(" 6$")); emitted=true end end
assert(emitted); h:Stop()
UserSettings = function() return {GameSettings={SavedQualityLevel={Value=0}}} end
local automatic = FX.play(R,CFrame.new(),{quality="Auto"})
for _,line in ipairs(EVENTS) do if line:match("^EMIT burst") then assert(line:match(" 6$")) end end
automatic:Stop()
''')

    def test_hold_on_burst_only_recipe_does_not_prevent_cleanup(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"] = recipe["nodes"][:3]
        recipe["animations"] = []
        self.run_luau('''
local h = FX.play(R,CFrame.new(),{hold=true})
Step(0.1); assert(not h.stopped)
Step(0.5); assert(h.stopped)
assert(workspace:FindFirstChild("DatakyFX") == nil)
''', recipe)

    def test_release_while_frozen_never_reenables_continuous_and_restores_particle_time_scale(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][3]["properties"]["TimeScale"] = 0.5
        self.run_luau('''
local h = FX.play(R,CFrame.new(),{hold=true})
Step(0.2); assert(h:Part("stream").Enabled)
FX.freeze(); h:Release()
Step(10); assert(not h.stopped)
FX.unfreeze(); assert(not h:Part("stream").Enabled)
near(h:Part("stream").TimeScale,0.5)
Step(0.21); assert(not h.stopped)
Step(0.2); assert(h.stopped)
''', recipe)

    def test_hold_does_not_leak_when_all_continuous_layers_finish_disabled(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][4]["properties"]["Enabled"] = False
        recipe["animations"].append({"node": "stream", "property": "Enabled", "keyframes": [
            {"time": 0, "value": True}, {"time": 0.4, "value": False}]})
        self.run_luau('''
local h = FX.play(R,CFrame.new(),{hold=true})
Step(0.2); assert(h:Part("stream").Enabled)
Step(0.2); assert(not h:Part("stream").Enabled)
Step(0.3); assert(h.stopped)
''', recipe)

    def test_instance_errors_are_isolated_and_stop_during_freeze_releases_ownership(self):
        self.run_luau('''
local failed = FX.play(R,CFrame.new(),{follow=function() error("follow failed") end})
local safe = FX.play(R,CFrame.new(),{hold=true})
local warnings = {}
warn = function(message) table.insert(warnings,message) end
Step(0.1); assert(failed.stopped and not safe.stopped)
assert(#warnings==1 and warnings[1]:match("follow failed"))
FX.freeze(); safe:Stop(); FX.unfreeze()
assert(workspace:FindFirstChild("DatakyFX") == nil)
''')

    def test_hold_release_waits_for_live_particles_and_cancels_future_bursts(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][2]["timing"]["start"] = 0.45
        self.run_luau('''
local h = FX.play(R, CFrame.new(), {hold=true})
Step(0.2); assert(h:Part("stream").Enabled)
h:Release(); assert(not h:Part("stream").Enabled)
Step(0.1); assert(not h.stopped)
Step(0.11); assert(h.stopped)
for _,line in ipairs(EVENTS) do assert(not line:match("^EMIT burst")) end
local held = FX.play(R, CFrame.new(), {hold=true})
Step(2); assert(held:Part("stream").Enabled and not held.stopped)
held:Release(); Step(0.21); assert(held.stopped)
''', recipe)

    def test_freeze_preserves_authored_time_scale_and_delays_cleanup(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][2]["properties"]["TimeScale"] = 0.5
        self.run_luau('''
local h = FX.play(R, CFrame.new())
Step(0.2); local t = h.time
FX.freeze(); near(h:Part("burst").TimeScale,0)
Step(5); near(h.time,t); assert(not h.stopped)
FX.unfreeze(); near(h:Part("burst").TimeScale,0.5)
Step(1); Step(1); assert(h.stopped)
''', recipe)

    def test_follow_uses_bone_attachment_and_basepart_and_play_does_not_call_callback(self):
        self.run_luau('''
local calls = 0
local h = FX.play(R, CFrame.new(), {hold=true, follow=function() calls+=1; return CFrame.new(20,0,0) end})
assert(calls == 0, "play must not invoke a potentially yielding follow callback")
Step(0.1); assert(calls==1); near(h:Part("part").Position.X,22)
h:Stop()
for _,class in ipairs({"Part", "Attachment", "Bone"}) do
    local target = MakeInstance(class,"Follow",{},workspace)
    target.CFrame, target.WorldCFrame, target.TransformedWorldCFrame = CFrame.new(30,0,0), CFrame.new(40,0,0), CFrame.new(50,0,0)
    local x = class=="Part" and 32 or class=="Attachment" and 42 or 52
    local handle = FX.play(R,CFrame.new(),{hold=true,follow=target})
    Step(0.1); near(handle:Part("part").Position.X,x)
    target:Destroy(); Step(0.1); assert(handle.released)
    Step(0.3); assert(handle.stopped)
end
''')

    def test_params_scale_only_marked_properties_including_animation(self):
        recipe = deepcopy(RECIPE)
        recipe["params"] = {"radius": {"default": 16}}
        recipe["nodes"][2]["scaleWith"] = {"Size": "radius", "Speed": "radius"}
        recipe["nodes"][4]["scaleWith"] = {"Range": "radius"}
        recipe["animations"].append({"node": "light", "property": "Range", "keyframes": [{"time": 0, "value": 6}, {"time": 0.5, "value": 10}]})
        self.run_luau('''
local h = FX.play(R,CFrame.new(),{scale=2,params={radius=32}})
near(h:Part("burst").Size.Keypoints[1].Value,8)
near(h:Part("burst").Speed.Max,24)
near(h:Part("burst").Acceleration.X,2)
Step(0.25); near(h:Part("light").Range,32)
near(h:Part("part").Size.X,4)
h:Stop()
local ok = pcall(FX.play,R,CFrame.new(),{params={unknown=1}})
assert(not ok)
''', recipe)

    def test_meshpart_requires_explicit_preload_and_can_then_play_without_yield(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][0]["class"] = "MeshPart"
        recipe["nodes"][0]["properties"]["MeshId"] = "rbxassetid://123"
        self.run_luau('''
local ok,message = pcall(FX.play,R,CFrame.new())
assert(not ok and tostring(message):match("preload"))
assert(workspace:FindFirstChild("DatakyFX") == nil)
FX.preload(R)
game:GetService("AssetService").CreateMeshPartAsync = function() error("play must not load a mesh") end
local h = FX.play(R,CFrame.new())
assert(h:Part("part").MeshId == "rbxassetid://123")
h:Stop()
''', recipe)

    def test_disabled_layers_never_emit_and_preview_carrier_tracks_are_ignored(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][2]["properties"]["Enabled"] = False
        recipe["nodes"][3]["properties"]["Enabled"] = False
        recipe["animations"] += [
            {"node": "part", "property": "Position", "keyframes": [{"time": 0, "value": [100, 0, 0]}]},
            {"node": "part", "property": "Transparency", "keyframes": [{"time": 0, "value": 0}]},
        ]
        self.run_luau('''
local h = FX.play(R,CFrame.new())
Step(0.2); assert(not h:Part("stream").Enabled)
near(h:Part("part").Position.X,2); near(h:Part("part").Transparency,1)
for _,line in ipairs(EVENTS) do assert(not line:match("^EMIT")) end
h:Stop()
''', recipe)

    def test_prepare_and_warm_play_clone_without_validation_or_decoding(self):
        self.run_luau('''
local parent = Instance.new("Folder"); parent.Parent = workspace
FX.prepare(R)
local before = MOCK_STATS.newCalls
local oldSequence = NumberSequence.new
NumberSequence.new = function() error("a prepared recipe must not decode again") end
local a = FX.play(R,CFrame.new(10,0,0),{parent=parent,hold=true})
assert(MOCK_STATS.newCalls==before)
local clones = MOCK_STATS.cloneCalls
local b = FX.play(R,CFrame.new(-10,0,0),{parent=parent})
assert(MOCK_STATS.newCalls==before and MOCK_STATS.cloneCalls==clones+1)
assert(a:Part("att").Parent == a:Part("part"))
assert(b:Part("att").Parent == b:Part("part"))
assert(a:Part("att") ~= b:Part("att"))
near(a:Part("part").Position.X,12); near(b:Part("part").Position.X,-8)
a:Stop(); b:Stop(); NumberSequence.new=oldSequence
-- Cached input is a snapshot. Mutating the used table is deliberately unsupported.
R.nodes[1].properties.Size={200,200,200}
local c=FX.play(R,CFrame.new(),{parent=parent})
near(c:Part("part").Size.X,2); c:Stop()
-- A copied recipe is a new cache key and receives the new values.
local fresh=table.clone(R); fresh.nodes=table.clone(R.nodes)
local d=FX.play(fresh,CFrame.new(),{parent=parent})
near(d:Part("part").Size.X,200); d:Stop()
''')

    def test_prepared_scaling_params_and_tracks_do_not_mutate_template(self):
        recipe = deepcopy(RECIPE)
        recipe["params"] = {"radius": {"default": 2}}
        recipe["nodes"][2]["scaleWith"] = {"Size": "radius", "Speed": "radius"}
        self.run_luau('''
FX.prepare(R)
local a=FX.play(R,CFrame.new(),{scale=3,params={radius=4},hold=true})
local b=FX.play(R,CFrame.new(),{scale=1,params={radius=1}})
near(a:Part("burst").Size.Keypoints[1].Value,12)
near(b:Part("burst").Size.Keypoints[1].Value,1)
near(a:Part("stream").Size.Keypoints[1].Value,3)
Step(0.25); near(a:Part("light").Brightness,5); near(b:Part("light").Brightness,5)
a:Release(); b:Stop(); Step(0.3); assert(a.stopped)
local c=FX.play(R,CFrame.new())
near(c:Part("burst").Size.Keypoints[1].Value,2)
near(c:Part("part").Size.X,2); c:Stop()
''', recipe)

    def test_prepared_beam_and_trail_references_target_the_clone(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"] += [
            {"id": "end", "class": "Attachment", "parent": "part", "properties": {"Position": [0, 2, 0]}},
            {"id": "beam", "class": "Beam", "parent": "part", "properties": {"Attachment0": "att", "Attachment1": "end"}},
            {"id": "trail", "class": "Trail", "parent": "part", "properties": {"Attachment0": "att", "Attachment1": "end"}},
        ]
        self.run_luau('''
FX.prepare(R)
local a,b=FX.play(R),FX.play(R)
for _,h in ipairs({a,b}) do
    assert(h:Part("beam").Attachment0 == h:Part("att"))
    assert(h:Part("trail").Attachment1 == h:Part("end"))
end
assert(a:Part("beam").Attachment0 ~= b:Part("beam").Attachment0)
a:Stop(); b:Stop()
''', recipe)

    def test_release_hides_all_visible_parts_but_preserves_particles_and_follow_stops(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][0]["properties"]["Transparency"] = 0
        recipe["nodes"] += [{"id": "berry2", "class": "Part", "properties": {"Transparency": 0.2}}]
        self.run_luau('''
local calls=0
local h=FX.play(R,CFrame.new(),{hold=true,follow=function() calls+=1; return CFrame.new(10,0,0) end})
Step(0.2); local particle=h:Part("burst"); local part=h:Part("part"); local x=part.Position.X
h:Release({hideParts=true})
near(part.Transparency,1); near(h:Part("berry2").Transparency,1)
assert(not h.stopped and h:Part("burst")==particle and not particle._destroyed)
assert(not h:Part("stream").Enabled and h.follow==nil)
local before=calls; Step(0.1); assert(calls==before); near(part.Position.X,x)
h:Release({hideParts=true}); Step(0.11); assert(h.stopped)
''', recipe)

    def test_set_follow_supports_switch_and_detach_without_calling_user_code(self):
        self.run_luau('''
local h=FX.play(R,CFrame.new(),{hold=true})
local calls=0
assert(h:SetFollow(function() calls+=1; return CFrame.new(10,0,0) end)==h)
assert(calls==0); Step(0.1); near(h:Part("part").Position.X,12)
local target=MakeInstance("Attachment","Target",{},workspace); target.WorldCFrame=CFrame.new(20,0,0)
h:SetFollow(target); Step(0.1); near(h:Part("part").Position.X,22)
h:SetFollow(nil); target.WorldCFrame=CFrame.new(30,0,0)
Step(0.1); near(h:Part("part").Position.X,22)
assert(not pcall(function() h:SetFollow({}) end))
h:Release(); h:SetFollow(function() error("released handle must not follow") end)
Step(0.3); assert(h.stopped)
''')

    def test_on_finished_once_after_cleanup_for_natural_release_stop_and_external_removal(self):
        self.run_luau('''
for _,mode in ipairs({"natural","release","stop","external"}) do
    local calls=0
    local h=FX.play(R,CFrame.new(),{hold=mode=="release",onFinished=function(done)
        calls+=1; assert(done.stopped and done.root.Parent==nil)
        assert(done:Part("part")==nil)
    end})
    if mode=="release" then h:Release(); Step(2)
    elseif mode=="stop" then h:Stop(); FlushDeferred()
    elseif mode=="external" then h.root:Destroy(); Step(0.1)
    else Step(2); Step(2) end
    assert(calls==1,mode)
    h:Stop(); h:Release(); Step(2); assert(calls==1)
end
''')

    def test_on_finished_failure_or_yield_never_blocks_play_or_other_handles(self):
        self.run_luau('''
local callbackRan=false
local h=FX.play(R,CFrame.new(),{onFinished=function() callbackRan=true; coroutine.yield() end})
local co=coroutine.create(function() h:Stop(); return "done" end)
local ok,result=coroutine.resume(co)
assert(ok and result=="done" and coroutine.status(co)=="dead" and not callbackRan)
FlushDeferred(); assert(callbackRan)
local warnings={}; warn=function(message) table.insert(warnings,message) end
local failed=FX.play(R,CFrame.new(),{onFinished=function() error("callback failed") end})
local safe=FX.play(R,CFrame.new(),{hold=true})
failed:Stop(); FlushDeferred()
assert(#warnings==1 and warnings[1]:match("callback failed") and not safe.stopped)
safe:Stop()
assert(not pcall(FX.play,R,nil,{onFinished=true}))
''')

    def test_preload_textures_old_library_deduplicates_normalizes_and_may_yield(self):
        recipe = deepcopy(RECIPE)
        recipe["nodes"][2]["properties"]["Texture"] = "123"
        recipe["nodes"][3]["properties"]["Texture"] = "https://www.roblox.com/asset/?id=123"
        self.run_luau('''
local provider=game:GetService("ContentProvider")
local list=FX.preloadTextures({OldExport=R,OtherKey=R,version=R,nodes=R})
assert(#list==1 and list[1]=="rbxassetid://123")
assert(#provider.calls==1 and #provider.calls[1]==1)
list[1]="mutated"; assert(FX.listTextures(R)[1]=="rbxassetid://123")
provider.PreloadAsync=function(self,uris) assert(uris[1]=="rbxassetid://123"); coroutine.yield("preloading") end
local thread=coroutine.create(function() FX.preloadTextures(R); return "done" end)
local ok,value=coroutine.resume(thread); assert(ok and value=="preloading")
assert(coroutine.resume(thread)); assert(coroutine.status(thread)=="dead")
-- Once primed, play cannot call the yielding loader or a user follow callback.
FX.prepare(R)
local play=coroutine.create(function()
    local h=FX.play(R,CFrame.new(),{follow=function() coroutine.yield("forbidden") end}); h:Stop(); return "done"
end)
local good,done=coroutine.resume(play); assert(good and done=="done" and coroutine.status(play)=="dead")
''', recipe)

    def test_all_blueberrinni_fixtures_can_prepare_and_play(self):
        for path in sorted((TOOL / "fixtures" / "blueberrinni").glob("*.json")):
            recipe = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(recipe, dict) or "nodes" not in recipe:
                continue
            with self.subTest(recipe=path.name):
                self.run_luau('''
FX.preloadTextures(R); FX.prepare(R)
local h=FX.play(R,CFrame.new(5,2,1)*CFrame.fromOrientation(0,0.5,0),{scale=0.75,speed=1.2})
Step(0.1); h:Release({hideParts=true}); Step(20); assert(h.stopped)
''', recipe)

    def test_warm_play_benchmark_exceeds_three_times_on_real_recipes(self):
        try:
            from .benchmark_fx_kit import benchmark
        except ImportError:
            from benchmark_fx_kit import benchmark
        for name, result in benchmark(TOOL / "fx_kit.lua", samples=180)["recipes"].items():
            with self.subTest(recipe=name):
                self.assertGreaterEqual(result["speedup"], 3, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
