"""The .rbxmx export: serialization checked statically, then the embedded player is run
under Luau (DATAKY_LUAU or `luau` on PATH) against the instances read back from the file."""
from __future__ import annotations

import base64
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

try:
    from .fx_rbxmx import ENUMS, export_rbxmx
except ImportError:
    from fx_rbxmx import ENUMS, export_rbxmx

TOOL = Path(__file__).resolve().parent


def seq(value):
    return [{"time": 0, "value": value, "envelope": 0}, {"time": 1, "value": value, "envelope": 0}]


PROJECT = {
    "version": 1, "id": "rbxmx-test", "name": "Test <export> & co", "duration": 1, "loop": False,
    "nodes": [
        {"id": "support", "class": "Part", "name": "Support", "parent": None,
         "properties": {"Position": [0, 1, 0], "Orientation": [0, 90, 0], "Size": [2, 1, 3], "Transparency": 1, "Color": [1, 0.5, 0],
                        "Shape": "Ball", "Material": "Neon"}},
        {"id": "a0", "class": "Attachment", "name": "A0", "parent": "support", "properties": {"Position": [0, 0, -2]}},
        {"id": "a1", "class": "Attachment", "name": "A1", "parent": "support", "properties": {"Position": [0, 0, 2], "Axis": [0, 1, 0], "SecondaryAxis": [-1, 0, 0]}},
        {"id": "burst", "class": "ParticleEmitter", "name": "Burst", "parent": "a0",
         "properties": {"Texture": "rbxassetid://123", "Rate": 0, "Lifetime": [0.2, 0.4], "Size": seq(1), "Orientation": "VelocityParallel", "Shape": "Disc"},
         "timing": {"start": 0.2, "duration": 0.05, "mode": "burst", "count": 7}},
        {"id": "stream", "class": "ParticleEmitter", "name": "Stream", "parent": "a0", "properties": {"Rate": 30, "Color": [{"time": 0, "value": [1, 0, 0]}, {"time": 1, "value": [0, 0, 1]}]},
         "timing": {"start": 0.3, "duration": 0.3, "mode": "continuous"}},
        {"id": "light", "class": "PointLight", "name": "Light", "parent": "a0", "properties": {"Brightness": 4, "Color": [1, 1, 0.5], "Range": 12},
         "timing": {"start": 0, "duration": 0.1, "mode": "continuous"}},
        {"id": "beam", "class": "Beam", "name": "Beam", "parent": "support", "properties": {"Attachment0": "a0", "Attachment1": "a1", "Texture": "", "Segments": 12}},
    ],
    "animations": [{"node": "support", "property": "Position", "keyframes": [{"time": 0, "value": [0, 1, 0]}, {"time": 1, "value": [4, 1, 0]}]}],
}


def attributes(blob: str) -> dict[str, str]:
    data, out, offset = base64.b64decode(blob), {}, 4
    for _ in range(struct.unpack_from("<I", data)[0]):
        length = struct.unpack_from("<I", data, offset)[0]; offset += 4
        key = data[offset:offset + length].decode(); offset += length
        assert data[offset] == 0x02; offset += 1
        length = struct.unpack_from("<I", data, offset)[0]; offset += 4
        out[key] = data[offset:offset + length].decode(); offset += length
    return out


class RbxmxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xml = export_rbxmx(PROJECT)
        cls.root = ET.fromstring(cls.xml)
        cls.items = {}
        for item in cls.root.iter("Item"):
            props = item.find("Properties")
            blob = props.find("BinaryString[@name='AttributesSerialize']")
            key = attributes(blob.text)["DatakyFXNodeId"] if blob is not None else item.get("class")
            cls.items[key] = item

    def prop(self, ident, kind, name):
        node = self.items[ident].find(f"Properties/{kind}[@name='{name}']")
        self.assertIsNotNone(node, f"{ident}.{name} ({kind})")
        return node

    def test_model_hierarchy_attributes_and_player(self):
        model = self.root.find("Item")
        self.assertEqual(model.get("class"), "Model")
        self.assertEqual(model.find("Properties/string[@name='Name']").text, "Test <export> & co")
        self.assertIsNotNone(model.find("Properties/OptionalCoordinateFrame[@name='WorldPivotData']/CFrame"))
        self.assertEqual([child.get("class") for child in model.findall("Item")], ["Part", "ModuleScript"])
        self.assertEqual({child.get("class") for child in self.items["a0"].findall("Item")}, {"ParticleEmitter", "PointLight"})
        source = self.items["ModuleScript"].find("Properties/ProtectedString[@name='Source']").text
        self.assertIn("Runtime.adopt(Project, script.Parent", source)
        self.assertEqual(len({item.get("referent") for item in self.root.iter("Item")}), len(list(self.root.iter("Item"))))

    def test_base_part_serialized_names_and_frames(self):
        cframe = [float(v.text) for v in self.prop("support", "CoordinateFrame", "CFrame")]
        self.assertEqual(cframe[:3], [0, 1, 0])
        self.assertAlmostEqual(cframe[3 + 2], 1, places=6, msg="yaw 90: R02 = 1")
        self.assertAlmostEqual(cframe[3 + 6], -1, places=6, msg="yaw 90: R20 = -1")
        self.assertEqual([float(v.text) for v in self.prop("support", "Vector3", "size")], [2, 1, 3])
        self.assertEqual(self.prop("support", "token", "shape").text, str(ENUMS["PartType"]["Ball"]))
        self.assertEqual(self.prop("support", "token", "Material").text, "288")
        self.assertEqual(int(self.prop("support", "Color3uint8", "Color3uint8").text), 0xFFFF8000)
        self.assertIsNone(self.items["support"].find("Properties/*[@name='Position']"))
        axis = [float(v.text) for v in self.prop("a1", "CoordinateFrame", "CFrame")][3:]
        self.assertEqual([round(axis[i], 6) for i in (0, 3, 6)], [0, 1, 0], "RightVector = Axis")
        self.assertEqual([round(axis[i], 6) for i in (1, 4, 7)], [-1, 0, 0], "UpVector = SecondaryAxis")

    def test_effect_properties_types_references_and_timed_switches(self):
        self.assertEqual(self.prop("burst", "Content", "TextureContent").find("uri").text, "rbxassetid://123")
        self.assertIsNotNone(self.prop("beam", "Content", "TextureContent").find("null"))
        self.assertEqual(self.prop("burst", "token", "Orientation").text, "2")
        self.assertEqual(self.prop("burst", "token", "Shape").text, "3", "ParticleEmitter.Shape keeps its name")
        self.assertEqual(self.prop("burst", "NumberRange", "Lifetime").text.split(), ["0.2", "0.4"])
        self.assertEqual(self.prop("stream", "ColorSequence", "Color").text.split(), "0 1 0 0 0 1 0 0 1 0".split())
        self.assertEqual(self.prop("light", "Color3", "Color").find("B").text, "0.5")
        self.assertEqual(self.prop("beam", "int", "Segments").text, "12")
        self.assertEqual(self.prop("beam", "Ref", "Attachment1").text, self.items["a1"].get("referent"))
        for ident in ("burst", "stream", "light"):
            self.assertEqual(self.prop(ident, "bool", "Enabled").text, "false")
        self.assertIsNone(self.items["beam"].find("Properties/bool[@name='Enabled']"), "untimed switches keep their recipe value")

    @unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent (DATAKY_LUAU)")
    def test_player_runs_the_timeline_on_the_file_instances(self):
        lines = [(TOOL / "luau_roblox_mock.luau").read_text(encoding="utf-8")]
        names = {}

        def build(item, parent):
            var = f"i{len(names)}"
            names[item.get("referent")] = var
            props = item.find("Properties")
            blob = props.find("BinaryString[@name='AttributesSerialize']")
            attrs = attributes(blob.text) if blob is not None else {}
            name = props.find("string[@name='Name']").text.replace('"', '\\"')
            attr = "{" + ",".join(f'{k}="{v}"' for k, v in attrs.items()) + "}"
            lines.append(f'local {var} = MakeInstance("{item.get("class")}", "{name}", {attr}, {parent})')
            for child in item.findall("Item"):
                build(child, var)
            return var

        model = build(self.root.find("Item"), "workspace")
        source = self.items["ModuleScript"].find("Properties/ProtectedString[@name='Source']").text
        lines += [f'rawset({model}, "_pivot", CFrame.new(10, 0, 0))', f"script = {{Parent = {model}}}",
                  "local Effect = (function()\n" + source + "\nend)()",
                  "Effect.play()", "for _ = 1, 66 do Step(1 / 60) end", "Dump()"]
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        try:
            result = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), handle.name], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        events = [line.split() for line in result.stdout.splitlines()]
        self.assertFalse([e for e in events if e[0] == "WARN"], result.stdout)
        emits = [e for e in events if e[0] == "EMIT"]
        self.assertEqual(len(emits), 1)
        self.assertEqual(emits[0][1], "burst"); self.assertEqual(emits[0][3], "7")
        self.assertAlmostEqual(float(emits[0][2]), 0.2, delta=0.02)
        switches = {(e[1], e[3]): float(e[2]) for e in events if e[0] == "ENABLED"}
        self.assertAlmostEqual(switches[("stream", "true")], 0.3, delta=0.02)
        self.assertAlmostEqual(switches[("stream", "false")], 0.6, delta=0.02)
        self.assertAlmostEqual(switches[("light", "false")], 0.1, delta=0.02)
        positions = {round(float(e[2]), 2): [float(v) for v in e[3:]] for e in events if e[0] == "POSITION" and e[1] == "support"}
        x = positions[min(positions, key=lambda t: abs(t - 0.5))][0]
        self.assertTrue(math.isclose(x, 12, abs_tol=0.1), f"animation follows the moved pivot: {x}")


class PluginHintTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent (DATAKY_LUAU)")
    def test_connection_hint_only_once_in_edit_never_in_play(self):
        source = (TOOL / "fx_plugin.lua").read_text(encoding="utf-8")
        hint = source[source.index("if RunService:IsEdit() and not RunService:IsRunning() and not _G.DatakyFXConnectionHintShown then"):source.rindex("return session.status()")]
        script = '''local running, editing, printed = true, true, 0
local RunService = {IsRunning=function() return running end, IsEdit=function() return editing end}
local _G = {}
local isPlugin, BASE = true, "local"
local print = function() printed += 1 end
local function loadHint()
''' + hint + '''\nend
loadHint(); loadHint(); assert(printed == 0, "Play must stay silent even when IsEdit is true")
running, editing = false, false
loadHint(); assert(printed == 0, "A paused non-Edit DataModel stays silent")
running, editing = false, true
loadHint(); loadHint(); assert(printed == 1, "Edit hint must appear once")
running = true
loadHint(); assert(printed == 1, "Play after Edit must stay silent")
'''
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as handle:
            handle.write(script)
        try:
            result = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), handle.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
