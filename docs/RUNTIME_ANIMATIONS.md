# Motion tracks in Roblox exports

`DatakyFXKit` plays `Position` and `Transparency` tracks on `Part` and `MeshPart` nodes when the optional Boolean `animations[].runtime` is set to `true`.

```json
{
  "node": "orb",
  "property": "Position",
  "runtime": true,
  "keyframes": [
    {"time": 0, "value": [2, 0, 0]},
    {"time": 0.5, "value": [3, 2, 0]},
    {"time": 1, "value": [4, 0, 0]}
  ]
}
```

`Position` is absolute in recipe coordinates, like `nodes[].properties.Position`. The kit applies `options.scale`, then the translation and rotation of the `CFrame` passed to `FX.play`. An animated `Orientation` on the same object is composed with that `CFrame`. `h:Move(cf)` and `follow` use the calculated local motion, so the animated effect follows its gameplay attachment point. Each handle maintains its own position and rotation state. Recipes and prepared templates stay immutable.

A `Transparency` track with `runtime: true` plays normally in the kit. Property tracks stop updating after `h:Release()`. Calling `h:Release({hideParts=true})` keeps Parts invisible while the remaining particles expire.

## Compatibility

- When `runtime` is omitted or `false`, the kit keeps its original behaviour and ignores `Position` and `Transparency` tracks on Parts and MeshParts.
- Other tracks, including `Attachment.Position`, `Part.Size`, and `Part.Orientation`, continue to play without a flag. Setting `runtime: false` does not disable them.
- The validator accepts only Boolean values for `runtime` and preserves an explicit `false`. JSON, Lua library, and `.rbxmx` exports and `merge_recipes` all preserve the field.
- The legacy Lua and `.rbxmx` players already play every track and place the effect using the translation of the origin. Use the library export and kit to compose rotations and follow gameplay objects.
- `MeshPart` nodes still require `FX.preload(recipe)` before `FX.play`.
- The existing limits still apply: 1,000 keyframes per track, one track per object and property pair, and linear interpolation for vectors. Procedural generators must bake their keyframes within those limits.

## Verification

`tool/test_fx_kit.py` runs the Luau code with the shared Roblox mock. It checks legacy behaviour, `runtime: false`, invalid values, Part and MeshPart movement, scaling, translation, rotation, following, `Move`, independent handles, and Position and Orientation track order. The schema, merge, Lua library, and `.rbxmx` tests verify that the flag is preserved. Luau also runs the embedded `.rbxmx` player on instances rebuilt from the exported file.

```powershell
$env:DATAKY_LUAU = 'C:\chemin\vers\luau.exe'
python -m unittest tool.test_fx_kit tool.test_fx_rbxmx tool.test_fx_server.SchemaTests tool.test_fx_builder
```
