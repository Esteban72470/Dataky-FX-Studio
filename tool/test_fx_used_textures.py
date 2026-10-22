"""Real bridge scanner and directly reusable exclusion files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from .fx_used_textures import save_used_textures
    from .fx_tools import excluded_ids
    from .fx_schema import ValidationError
except ImportError:
    from fx_used_textures import save_used_textures
    from fx_tools import excluded_ids
    from fx_schema import ValidationError

TOOL = Path(__file__).resolve().parent
LUAU = os.environ.get("DATAKY_LUAU") or shutil.which("luau")


class UsedTextureFileTests(unittest.TestCase):
    def test_scan_is_deduplicated_numeric_sorted_and_directly_reusable(self):
        with tempfile.TemporaryDirectory() as folder:
            result = save_used_textures(folder, "Ma place", ["100", "2", "100", "0002"])
            target = Path(result["path"])
            self.assertEqual(target.relative_to(Path(folder).resolve()).as_posix(), "tool/used_textures/Ma place.txt")
            self.assertEqual(target.read_text(), "2\n100\n")
            self.assertEqual(result["count"], 2)
            self.assertEqual(excluded_ids(exclude_file=target), {"2", "100"})

    def test_windows_names_are_confined_and_invalid_ids_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("../../escape", "C:\\Windows\\file", "NUL", "CON.txt", "...", "AUX "):
                path = Path(save_used_textures(folder, name, ["42"])["path"])
                self.assertEqual(path.parent, Path(folder).resolve() / "tool" / "used_textures")
            path = Path(save_used_textures(folder, "Place", ["42"])["path"])
            for ids in (["rbxassetid://1"], [1], ["0"], ["1\n2"], ["x"], None):
                with self.assertRaises(ValidationError):
                    save_used_textures(folder, "Place", ids)
                self.assertEqual(path.read_text(), "42\n")

    @unittest.skipUnless(LUAU, "Luau CLI absent")
    def test_actual_plugin_scans_instances_and_literal_modules_without_execution(self):
        source = (TOOL / "fx_plugin.lua").read_text(encoding="utf-8")
        scanner = source.split("-- BEGIN USED TEXTURE SCAN", 1)[1].split("-- END USED TEXTURE SCAN", 1)[0]
        scanner = "-- BEGIN USED TEXTURE SCAN" + scanner
        # json.dumps strings are also valid Luau literals for these ASCII samples.
        module = '''return {version=1,nodes={
            {properties={["Texture"]="rbxassetid://333", Texture='444'}},
            {properties={Texture=555, TextureID="666", TextureId="https://www.roblox.com/asset/?id=777"}},
            {properties={Texture=dynamicTexture}},
            {properties={Texture=123..'456'}},
        }}'''
        checks = '''
local function object(class, texture, source)
    return {Texture=texture, Source=source, IsA=function(_, name) return class == name end}
end
local unreadable = setmetatable({IsA=function(_, name) return name == "ModuleScript" end}, {__index=function() error("source denied") end})
local place = {GetDescendants=function() return {
    object("ParticleEmitter", "rbxassetid://111"), object("Beam", "111"),
    object("Trail", "http://www.roblox.com/asset?id=222"),
    object("ParticleEmitter", "rbxasset://textures/particles/smoke_main.dds"),
    object("ModuleScript", nil, MODULE), unreadable,
    object("ModuleScript", nil, "error('must not execute'); return {Texture='999'}"),
} end}
local ids, unreadableCount, dynamicCount = collectUsedTextures(place)
assert(table.concat(ids, ",") == "111,222,333,444,555,666,777", table.concat(ids, ","))
assert(unreadableCount == 1 and dynamicCount == 2)
print("SCAN_OK")
'''.replace("MODULE", json.dumps(module))
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "scan.luau"
            script.write_text(scanner + checks, encoding="utf-8")
            result = subprocess.run([LUAU, str(script)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SCAN_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
