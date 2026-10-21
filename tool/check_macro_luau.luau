local luau = require("@lune/luau")
local fs = require("@lune/fs")
local root = "tool/"
local harvest = fs.readFile(root .. "harvest_ui.lua")
local bridge = fs.readFile(root .. "bridge.lua")
local source = "(function()\n" .. harvest .. "\nend)()\n" .. bridge
luau.load(source)
print("Macro bootstrap Luau compilation passed (not executed)")
