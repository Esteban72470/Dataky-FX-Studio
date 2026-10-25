"""Verify the three authored effects using the actual exporters and runtimes.

Missing recipes are reported as skipped while the effects are being authored.
Once a recipe exists its missing captures or invalid content is a failure.
There are no visual-quality scores. Luau uses the shared Roblox stand-ins, not
Roblox Studio; JavaScript executes the actual Dataky emulator without WebGL.

    python -m unittest tool.test_pro_vfx -v
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import unittest
import xml.etree.ElementTree as ET

if __package__:
    from .fx_schema import validate_project
    from .fx_export import export_library, export_project
    from .fx_rbxmx import export_rbxmx
    from .fx_artistry import create_plan
    from .test_fx_rbxmx import attributes
    from . import test_fx_kit as _kit
else:
    from fx_schema import validate_project
    from fx_export import export_library, export_project
    from fx_rbxmx import export_rbxmx
    from fx_artistry import create_plan
    from test_fx_rbxmx import attributes
    import test_fx_kit as _kit

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("CelestialRiftSlash", "SolarSpear", "PhantomBloom")
SWITCHES = {"ParticleEmitter", "Beam", "Trail", "PointLight", "SpotLight", "SurfaceLight"}
DEPRECATED_MESHES = {"Prism", "Pyramid", "ParallelRamp", "RightAngleRamp", "CornerWedge"}


def recipe_path(name):
    return ROOT / "editor" / "projects" / (name + ".json")


def asset_ids(project):
    """Explicit numeric assets, excluding Roblox's built-in content URIs."""
    found = set()
    for node in project["nodes"]:
        for prop in ("Texture", "TextureId", "TextureID", "MeshId"):
            value = str(node["properties"].get(prop, ""))
            match = re.fullmatch(r"(?:rbxassetid://)?(\d+)", value) or re.search(r"[?&]id=(\d+)$", value)
            if match:
                found.add(match.group(1))
    return found


def sample_track(project, node, prop, time):
    track = next((t for t in project["animations"] if t["node"] == node["id"] and t["property"] == prop), None)
    value = deepcopy(node["properties"].get(prop, [0, 0, 0]))
    if track is None or (prop in ("Position", "Transparency") and node["class"] in ("Part", "MeshPart") and track.get("runtime") is not True):
        return value
    keys = track["keyframes"]
    if time <= keys[0]["time"]:
        return keys[0]["value"]
    for first, last in zip(keys, keys[1:]):
        if time < last["time"]:
            alpha = (time - first["time"]) / (last["time"] - first["time"])
            if isinstance(first["value"], list):
                return [a + (b-a)*alpha for a, b in zip(first["value"], last["value"])]
            return first["value"] + (last["value"]-first["value"])*alpha
    return keys[-1]["value"]


class ProEffectsTests(unittest.TestCase):
    def require_recipe(self, name):
        path = recipe_path(name)
        if not path.is_file():
            self.skipTest(name + " is not authored yet")
        original = json.loads(path.read_text(encoding="utf-8-sig"))
        return original, validate_project(original)

    def check_schema(self, name):
        original, project = self.require_recipe(name)
        self.assertEqual(validate_project(project), project, "Normalization must be stable")
        self.assertEqual(json.loads(recipe_path(name).read_text(encoding="utf-8-sig")), original,
                         "Validation must leave the saved recipe untouched")
        self.assertFalse(project["loop"], "These three one-shot effects must terminate")
        self.assertGreater(len(project["nodes"]), 0)
        for node in project["nodes"]:
            if node["class"] == "SpecialMesh":
                self.assertNotIn(node["properties"].get("MeshType"), DEPRECATED_MESHES)
            if node["class"] in ("Part", "MeshPart"):
                self.assertEqual(node["properties"].get("Transparency", 0), 1,
                                 node["id"] + " is a carrier, not a visible primitive")
        for track in project["animations"]:
            node = next(n for n in project["nodes"] if n["id"] == track["node"])
            if node["class"] in ("Part", "MeshPart") and track["property"] in ("Position", "Transparency"):
                self.assertIs(track.get("runtime"), True, track["node"] + "." + track["property"])
            if node["class"] in ("Part", "MeshPart") and track["property"] == "Transparency":
                self.assertTrue(all(k["value"] == 1 for k in track["keyframes"]), "Carriers stay invisible")
        spatial_beams = [n for n in project["nodes"] if n["class"] == "Beam"
                         and n["properties"].get("FaceCamera") is False and n["properties"].get("Texture")]
        self.assertTrue(spatial_beams, "The authored volume requires at least one textured beam in a fixed plane")

    def check_assets(self, name):
        _, project = self.require_recipe(name)
        assets = asset_ids(project)
        self.assertGreaterEqual(len(assets), 2, "The effect must use distinct explicit assets")
        for ident in assets:
            candidates = [ROOT / folder / (ident + ".png") for folder in
                          ("images", "beams/images", "beams/previews", "meshes/images", "meshes/previews")]
            self.assertTrue(any(path.is_file() for path in candidates), "No local preview for asset " + ident)

    def check_art_direction(self, name):
        _, project = self.require_recipe(name)
        path = ROOT / "editor" / "artistry" / "plans" / (name + ".json")
        self.assertTrue(path.is_file(), "The authored effect needs its saved direction plan")
        plan = json.loads(path.read_text(encoding="utf-8-sig"))
        checked = create_plan(project, {**plan["brief"], "phases": plan["phases"],
                                        "layers": plan["layers"], "budget": plan["budget"]})
        assigned = [ident for layer in checked["layers"] for ident in layer["nodes"]]
        self.assertEqual(set(assigned), {n["id"] for n in project["nodes"]})
        self.assertEqual(len(assigned), len(set(assigned)), "One artistic role per object")
        self.assertTrue(any(layer["role"] == "primary" for layer in checked["layers"]))

    def check_exports(self, name):
        original, project = self.require_recipe(name)
        root = ET.fromstring(export_rbxmx(project))
        items = list(root.iter("Item"))
        referents = {item.get("referent"): item for item in items}
        self.assertEqual(len(referents), len(items), "XML referents must be unique")
        by_node = {}
        for item in items:
            blob = item.find("Properties/BinaryString[@name='AttributesSerialize']")
            if blob is not None:
                by_node[attributes(blob.text)["DatakyFXNodeId"]] = item
        self.assertEqual(set(by_node), {n["id"] for n in project["nodes"]})
        for ref in root.iter("Ref"):
            if ref.text not in ("null", "nil", None):
                self.assertIn(ref.text, referents)
                self.assertEqual(referents[ref.text].get("class"), "Attachment")
        for node in project["nodes"]:
            if node["parent"] is not None:
                self.assertIn(by_node[node["id"]], list(by_node[node["parent"]]), "XML hierarchy: " + node["id"])
        player = root.find(".//ProtectedString[@name='Source']").text
        self.assertIn("Runtime.adopt(Project, script.Parent", player)
        lua = export_project(project)
        library = export_library({name: project})
        self.assertIn("function Effect.build", lua)
        self.assertIn('["' + name + '"]=', library)
        if any(t.get("runtime") is True for t in project["animations"]):
            for source in (player, lua, library):
                self.assertIn('["runtime"]=true', source)
        self.assertEqual(json.loads(recipe_path(name).read_text(encoding="utf-8-sig")), original)

    def check_captures(self, name):
        _, project = self.require_recipe(name)
        folder = ROOT / "rendus" / "pro" / name
        candidates = list(folder.glob("manifest*.json"))
        self.assertTrue(candidates, "Capture manifest not written yet: " + str(folder))
        manifest_path = max(candidates, key=lambda p: p.stat().st_mtime_ns)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(manifest.get("effect"), name)
        jobs = manifest.get("jobs", [])
        self.assertTrue(jobs, "The manifest must record the renderer's actual jobs")
        for job in jobs:
            self.assertTrue(job.get("projects"))
            self.assertEqual(validate_project(job["projects"][-1]), project,
                             "The captures must correspond to the current recipe")
        rendered = manifest.get("renders", {})
        self.assertTrue(rendered.get("jobs"), "The requested captures must have renderer results")
        times, images = set(), set()

        def walk(value, key=None):
            if isinstance(value, dict):
                for child_key, child in value.items():
                    if child_key != "projects":
                        walk(child, child_key)
            elif isinstance(value, list):
                for child in value:
                    walk(child, key)
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and key in ("time", "times"):
                self.assertTrue(math.isfinite(value) and 0 <= value <= project["duration"])
                times.add(round(value, 6))
            elif isinstance(value, str) and value.lower().endswith(".png"):
                path = Path(value)
                if not path.is_absolute():
                    path = folder / path if (folder / path).is_file() else ROOT / path
                images.add(path.resolve())

        # Count only actual renderer-reported times, never recipe keyframes or
        # planned times. Existence of every reported PNG is checked below.
        walk(rendered)
        self.assertGreaterEqual(len(times), 5, "At least five distinct captured times must be recorded")
        self.assertTrue(images, "The manifest must reference rendered PNGs")
        for path in images:
            self.assertTrue(path.is_file(), "Missing capture: " + str(path))
            blob = path.read_bytes()
            self.assertGreater(len(blob), 24)
            self.assertEqual(blob[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", blob[16:24])
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
        stage = manifest.get("stage")
        self.assertTrue(any(path.name == "hero-" + str(stage) + ".png" for path in images),
                        "The rendered hero contact sheet must be present")

    def check_emulator_cleanup(self, name):
        self.require_recipe(name)
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable")
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const E = require(process.argv[2]);
const recipe = JSON.parse(fs.readFileSync(process.argv[1], 'utf8').replace(/^\uFEFF/, ''));
const sim = E.createSimulation(recipe, {seed: 37});
let seen = false;
for (let i=0; i<40; i++) {
  sim.seek(recipe.duration * i / 40);
  const frame = E.buildFrame(sim, recipe.camera);
  assert.equal(frame.placeholders.length, 0, 'unsupported mesh cannot stand in for the visible effect');
  assert.ok(frame.data.every(Number.isFinite), 'finite geometry throughout the effect');
  seen ||= frame.vertices > 0 || frame.parts.length > 0;
}
assert.ok(seen, 'the actual emulator must produce visible effect geometry');
sim.seek(recipe.duration);
assert.equal(sim.ended, true);
assert.equal(sim.alive, false, 'particles and trail histories must finish by the declared end');
assert.equal(sim.stats().particles, 0);
assert.equal(sim.stats().trailPoints, 0);
for (const n of sim.nodes.filter(n => /^(ParticleEmitter|Beam|Trail|PointLight|SpotLight|SurfaceLight)$/.test(n.class)))
  assert.equal(sim.isEnabled(n.id), false, n.id + ' must be disabled');
const final = E.buildFrame(sim, recipe.camera);
assert.equal(final.vertices, 0, 'no lingering ribbon or particle geometry');
assert.equal(final.parts.length, 0, 'no visible carrier at the declared end');
sim.seek(recipe.duration + 2);
assert.equal(sim.alive, false, 'no restart after completion');
sim.seek(recipe.duration * .45); sim.stop();
assert.equal(sim.alive, false, 'Stop clears existing particle and trail history');
console.log('PRO_EMULATOR_OK');
"""
        result = subprocess.run([node, "-e", script, str(recipe_path(name)), str(ROOT / "editor" / "emulator.js")],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PRO_EMULATOR_OK", result.stdout)

    def check_luau_instances_and_cleanup(self, name):
        _, project = self.require_recipe(name)
        if not _kit.LUAU:
            self.skipTest("Luau CLI absent (set DATAKY_LUAU)")
        carrier = next(n for n in project["nodes"] if n["class"] in ("Part", "MeshPart"))
        time = project["duration"] * .35
        initial = sample_track(project, carrier, "Position", 0)
        later = sample_track(project, carrier, "Position", time)
        attachment_positions = {n["id"]: sample_track(project, n, "Position", time)
                                for n in project["nodes"] if n["class"] == "Attachment"}
        max_tail = max([0] + [
            max(n["properties"].get("Lifetime", [5, 10])) / max(n["properties"].get("TimeScale", 1), .001)
            if n["class"] == "ParticleEmitter" else n["properties"].get("Lifetime", 2)
            for n in project["nodes"] if n["class"] in ("ParticleEmitter", "Trail")])
        drain = project["duration"] + max_tail + 1
        checks = r"""
local function vnear(actual, x,y,z) near(actual.X,x); near(actual.Y,y); near(actual.Z,z) end
local function under(object, root)
    local current = object
    while current do if current == root then return true end; current=current.Parent end
    return false
end
local finishedA,finishedB = 0,0
FX.preload(R); FX.prepare(R)
local cf = CFrame.new(10,4,7) * CFrame.fromOrientation(0,math.pi/2,0)
local a = FX.play(R,cf,{scale=2,onFinished=function() finishedA+=1 end})
local b = FX.play(R,CFrame.new(-10,0,0),{onFinished=function() finishedB+=1 end})
assert(a.root ~= b.root)
for _,node in ipairs(R.nodes) do
    local left, right = a:Part(node.id), b:Part(node.id)
    assert(left and right and left ~= right and under(left,a.root) and under(right,b.root))
    if node.class == 'Part' or node.class == 'MeshPart' then
        near(left.Transparency,1); near(right.Transparency,1)
        near(left.Size.X,right.Size.X*2); near(left.Size.Y,right.Size.Y*2); near(left.Size.Z,right.Size.Z*2)
    elseif node.class == 'Attachment' then
        vnear(left.Position,right.Position.X*2,right.Position.Y*2,right.Position.Z*2)
    elseif node.class == 'Beam' or node.class == 'Trail' then
        assert(left.Attachment0 ~= right.Attachment0 and left.Attachment1 ~= right.Attachment1)
        assert(under(left.Attachment0,a.root) and under(left.Attachment1,a.root))
    end
end
vnear(a:Part(CARRIER).Position, 10+2*INITIAL[3],4+2*INITIAL[2],7-2*INITIAL[1])
vnear(b:Part(CARRIER).Position, -10+INITIAL[1],INITIAL[2],INITIAL[3])
local remaining = TEST_TIME
while remaining > .000001 do local dt=math.min(.025,remaining); Step(dt); remaining-=dt end
assert(not a.stopped and not b.stopped)
vnear(a:Part(CARRIER).Position,10+2*LATER[3],4+2*LATER[2],7-2*LATER[1])
vnear(b:Part(CARRIER).Position,-10+LATER[1],LATER[2],LATER[3])
for id,localPosition in pairs(ATTACHMENT_POSITIONS) do
    vnear(a:Part(id).Position,2*localPosition[1],2*localPosition[2],2*localPosition[3])
    vnear(b:Part(id).Position,localPosition[1],localPosition[2],localPosition[3])
end
a:Move(CFrame.new(30,0,0))
vnear(a:Part(CARRIER).Position,30+2*LATER[1],2*LATER[2],2*LATER[3])
a:Stop(); FlushDeferred()
assert(a.stopped and a.root.Parent==nil and not b.stopped and b.root.Parent~=nil and finishedA==1)
b:Release({hideParts=true})
for _,node in ipairs(R.nodes) do
    if node.class == 'Part' or node.class == 'MeshPart' then near(b:Part(node.id).Transparency,1)
    elseif node.class == 'ParticleEmitter' or node.class == 'Beam' or node.class == 'Trail' or node.class:match('Light$') then
        assert(not b:Part(node.id).Enabled)
    end
end
for _=1,math.ceil(DRAIN/.05) do Step(.05) end
assert(b.stopped and b.root.Parent==nil and finishedB==1)
local natural=FX.play(R,CFrame.new(3,0,0))
for _=1,math.ceil(DRAIN/.025) do Step(.025) end
assert(natural.stopped and natural.root.Parent==nil,'natural cleanup')
a:Stop(); b:Stop(); FlushDeferred(); assert(finishedA==1 and finishedB==1)
assert(workspace:FindFirstChild('DatakyFX')==nil,'kit-owned folder cleanup')
"""
        # Use the project's existing real-Luau runner and shared Roblox mock.
        if __package__:
            from .fx_export import _lua
        else:
            from fx_export import _lua
        prefix = "local CARRIER=" + _lua(carrier["id"]) + "\nlocal INITIAL=" + _lua(initial)
        prefix += "\nlocal LATER=" + _lua(later) + "\nlocal TEST_TIME=" + repr(time) + "\nlocal DRAIN=" + repr(drain) + "\n"
        prefix += "local ATTACHMENT_POSITIONS=" + _lua(attachment_positions) + "\n"
        _kit.KitLuauTests.run_luau(self, prefix + checks, recipe=project)

    def test_three_asset_palettes_are_distinct(self):
        recipes = []
        for name in NAMES:
            _, recipe = self.require_recipe(name)
            recipes.append(recipe)
        sets = [asset_ids(recipe) for recipe in recipes]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                self.assertNotEqual(sets[i], sets[j], NAMES[i] + " and " + NAMES[j] + " must not reuse exactly the same asset palette")


# Separate tests ensure an absent later effect never hides an earlier effect's
# failures and appears explicitly as a skip in the test report.
def _bind(name, check):
    def test(self):
        getattr(self, check)(name)
    test.__doc__ = name + ": " + check.removeprefix("check_").replace("_", " ")
    return test


for _name in NAMES:
    for _check in ("check_schema", "check_assets", "check_art_direction", "check_exports", "check_captures",
                   "check_emulator_cleanup", "check_luau_instances_and_cleanup"):
        setattr(ProEffectsTests, "test_" + _name + "_" + _check.removeprefix("check_"), _bind(_name, _check))


if __name__ == "__main__":
    unittest.main()
