"""Texture inventory in exported libraries stays outside recipe enumeration."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from .fx_export import export_library, library_textures
except ImportError:
    from fx_export import export_library, library_textures

LUAU = os.environ.get("DATAKY_LUAU") or shutil.which("luau")
TOOL = Path(__file__).resolve().parent
RECIPE = {
    "version": 1, "name": "Textures", "duration": 1,
    "nodes": [
        {"id": "root", "class": "Part", "properties": {}},
        {"id": "particles", "class": "ParticleEmitter", "parent": "root",
         "properties": {"Texture": "12"}},
        {"id": "beam", "class": "Beam", "parent": "root",
         "properties": {"Texture": "https://www.roblox.com/asset/?id=12"}},
        {"id": "trail", "class": "Trail", "parent": "root",
         "properties": {"Texture": "rbxassetid://34"}},
        {"id": "mesh", "class": "SpecialMesh", "parent": "root",
         "properties": {"TextureId": "rbxasset://textures/example.dds", "MeshId": "rbxassetid://999"}},
        {"id": "meshpart", "class": "MeshPart",
         "properties": {"TextureID": "https://roblox.com/asset?id=56", "MeshId": "rbxassetid://998"}},
        {"id": "empty", "class": "ParticleEmitter", "parent": "root", "properties": {"Texture": ""}},
        {"id": "implicit", "class": "ParticleEmitter", "parent": "root", "properties": {}},
    ],
}
EXPECTED = ["rbxasset://textures/example.dds", "rbxassetid://12", "rbxassetid://34", "rbxassetid://56"]


class LibraryTextureTests(unittest.TestCase):
    def run_luau(self, source):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "textures.luau"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run([LUAU, str(path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("TEXTURES_OK", result.stdout)

    def test_inventory_normalizes_deduplicates_and_excludes_mesh_ids_and_empty_textures(self):
        original = deepcopy(RECIPE)
        self.assertEqual(library_textures({"A": RECIPE, "B": RECIPE}), EXPECTED)
        self.assertEqual(RECIPE, original)

    def test_library_preserves_recipe_data_and_does_not_build_instances(self):
        source = export_library({"A": RECIPE, "B": RECIPE})
        self.assertIn("listTextures", source)
        self.assertNotIn("Instance.new", source)
        self.assertNotIn("PreloadAsync", source)
        self.assertIn('["Texture"]="12"', source, "inventory normalization must not rewrite recipes")

    @unittest.skipUnless(LUAU, "Luau CLI absent (DATAKY_LUAU)")
    def test_luau_inventory_is_non_enumerable_and_returns_a_defensive_copy(self):
        source = "local Recipes = (function()\n" + export_library({"A": RECIPE, "B": RECIPE}) + "\nend)()\n"
        source += '''
local count = 0
for key, recipe in pairs(Recipes) do
    assert((key == "A" or key == "B") and recipe.version == 1)
    count += 1
end
assert(count == 2)
local first = Recipes:listTextures()
assert(#first == 4 and first[2] == "rbxassetid://12")
first[2] = "corrupt"
local second = Recipes.listTextures()
assert(second[2] == "rbxassetid://12" and second ~= first)
assert(Recipes.A.nodes[2].properties.Texture == "12")
'''
        source += "local Collision = (function()\n" + export_library({"listTextures": RECIPE}) + "\nend)()\n"
        source += '''
assert(Collision.listTextures.version == 1)
assert(#getmetatable(Collision).listTextures() == 4)
print("TEXTURES_OK")
'''
        self.run_luau(source)

    @unittest.skipUnless(LUAU, "Luau CLI absent (DATAKY_LUAU)")
    def test_kit_preloads_and_plays_exported_library_with_all_schema_url_forms(self):
        recipes = {}
        for name, uri in {
            "http_plain": "http://roblox.com/asset?id=12",
            "http_www": "http://www.roblox.com/asset?id=12",
            "https_plain": "https://roblox.com/asset/?id=12",
            "https_www": "https://www.roblox.com/asset/?id=12",
        }.items():
            recipes[name] = deepcopy(RECIPE)
            recipes[name]["nodes"][1]["properties"]["Texture"] = uri
        source = (TOOL / "luau_roblox_mock.luau").read_text(encoding="utf-8")
        source += "\nlocal FX = (function()\n" + (TOOL / "fx_kit.lua").read_text(encoding="utf-8") + "\nend)()\n"
        source += "local Recipes = (function()\n" + export_library(recipes) + "\nend)()\n"
        source += '''
local expected, actual = Recipes:listTextures(), FX.preloadTextures(Recipes)
assert(#expected == 4 and #actual == #expected)
for i, uri in ipairs(expected) do assert(actual[i] == uri) end
local provider = game:GetService("ContentProvider")
assert(#provider.calls == 1 and #provider.calls[1] == 4)
for _, recipe in pairs(Recipes) do
    FX.preload(recipe)
    FX.prepare(recipe)
    local h = FX.play(recipe)
    assert(h:Part("particles").Texture == "rbxassetid://12")
    assert(h:Part("meshpart").TextureID == "rbxassetid://56")
    h:Stop()
end
print("TEXTURES_OK")
'''
        self.run_luau(source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
