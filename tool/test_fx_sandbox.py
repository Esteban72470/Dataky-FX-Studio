"""Preview-only runtime controls and version-1 parameter compatibility."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from fx_schema import validate_project, ValidationError
from fx_export import _lua
from test_fx_server import project

TOOL = Path(__file__).resolve().parent


class ParameterTests(unittest.TestCase):
    def test_parameter_markers_survive_normalization_without_mutation(self):
        data = project()
        data["params"] = {"radius": {"default": 16, "min": 0, "max": 64, "step": 1}}
        data["nodes"][-1]["scaleWith"] = {"Size": "radius"}
        before = deepcopy(data)
        clean = validate_project(data)
        self.assertEqual(data, before)
        self.assertEqual(clean["params"], data["params"])
        self.assertEqual(clean["nodes"][-1]["scaleWith"], {"Size": "radius"})
        self.assertEqual(clean, validate_project(clean))

    def test_invalid_parameter_definitions_and_markers_fail(self):
        good = project()
        good["params"] = {"radius": {"default": 16}}
        good["nodes"][-1]["scaleWith"] = {"Size": "radius"}
        for change in (
            lambda d: d["params"]["radius"].update(default=0),
            lambda d: d["params"]["radius"].update(default=float("nan")),
            lambda d: d["params"]["radius"].update(min=20),
            lambda d: d["params"]["radius"].update(step=0),
            lambda d: d["nodes"][-1].update(scaleWith={"Size": "absent"}),
            lambda d: d["nodes"][-1].update(scaleWith={"Enabled": "radius"}),
            lambda d: d["nodes"][0].update(scaleWith={"Position": "radius"}),
        ):
            data = deepcopy(good)
            change(data)
            with self.assertRaises(ValidationError):
                validate_project(data)


@unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent")
class SandboxTests(unittest.TestCase):
    def test_live_controls_preserve_recipe_and_timeline(self):
        data = validate_project(project())
        data["nodes"][-1]["properties"].update(TimeScale=1, Rate=12)
        stream = deepcopy(data["nodes"][-1])
        stream["id"] = "stream"
        stream["timing"] = {"start": 2, "duration": 1, "mode": "continuous", "count": 0}
        data["nodes"].append(stream)
        updated = deepcopy(data)
        updated["nodes"][-2]["properties"]["Rate"] = 80
        source = (TOOL / "luau_roblox_mock.luau").read_text(encoding="utf-8")
        source += "\nlocal Runtime=(function()\n" + (TOOL / "fx_runtime.lua").read_text(encoding="utf-8") + "\nend)()\n"
        source += "local recipe=" + _lua(data) + "\nlocal changed=" + _lua(updated) + "\n"
        source += '''
local root = MakeInstance("Model", "Sandbox")
root.Parent = workspace
local objects = {}
for _, node in ipairs(recipe.nodes) do
    local object = MakeInstance(node.class, node.id)
    object:SetAttribute("DatakyFXNodeId", node.id)
    object.Parent = root
    objects[node.id] = object
end
objects.emitter.TimeScale = 1
Runtime.adopt(recipe, root)
Runtime.sandbox(nil, {beam=false})
Step(10)
assert(Runtime.status().time == 10 and Runtime.status().playing, "free clock never ends")
assert(objects.beam.Enabled == false and objects.emitter.Enabled == false, "burst never emits at Rate")
assert(objects.stream.Enabled, "continuous ignores its timeline window in free mode")
for _, line in ipairs(EVENTS) do assert(not line:find("^EMIT"), "no automatic burst") end
Runtime.emit({emitter=7})
local emitted = false
for _, line in ipairs(EVENTS) do if line:find("^EMIT emitter .* 7$") then emitted = true end end
assert(emitted, "manual Emit count")
Runtime.enabled({beam=true, emitter=true})
assert(objects.beam.Enabled and not objects.emitter.Enabled)
Runtime.update(changed)
assert(objects.emitter.Rate == 80 and Runtime.status().time == 10, "live update preserves clock")
Runtime.pause()
Step(1)
assert(Runtime.status().time == 10 and objects.emitter.TimeScale == 0)
Runtime.resume()
assert(objects.emitter.TimeScale == 1)
Runtime.clearParticles()
assert(Runtime.status().time == 10 and objects.beam.Enabled, "Clear preserves switches and clock")
Runtime.stop()
assert(Runtime.status().time == 0 and not Runtime.status().playing)
assert(recipe.nodes[5].properties.Rate == 12 and recipe.nodes[4].properties.Enabled == nil, "preview never mutates recipe")
Runtime.play()
Step(.3)
assert(Runtime.status().mode == "timeline", "legacy timeline restored")
Runtime.stop()
'''
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as handle:
            handle.write(source)
        try:
            result = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), handle.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
