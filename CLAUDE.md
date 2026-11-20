# Dataky FX Studio guide for Claude

For character auras, Blessings, Shiny variants, and Beam interaction rings for NPCs or zones, use the four-layer workflow, Studio-verified Beam math, and Python texture generation in the [Auras & Blessings skill](./skills/datakyfx-auras/SKILL.md). It covers `--bloom`, `--tex-map`, `recolor`, and `prewarm`.

## Plan and review an effect

Start with `artistry_schema`, then use `plan_effect` to plan layers and phases. Use `animate_procedural` and `edit_effect_batch` to create reusable native tracks. `search_art_assets` searches verified observations. Treat visual attributes without evidence as unknown.

Start with `start_visual_review` and use `capture_visual_review` to attach two views and two backgrounds. Inspect the images before calling `submit_visual_review` with the nine criteria and an approve or revise decision. Ask for a human review if you cannot inspect images. Metrics alone cannot assess artistic quality. Resume with the get or list visual review tools. Preserve `runtime:true` on Part Position and Transparency tracks intended for the kit.

The repository represents Roblox VFX as JSON recipes, previews them in the browser emulator, and exports them to Roblox. Follow the user's VFX guidance for timing, colour, and readability. Use the tools below to build and check that direction.

## Workflow

1. **Inspect textures before choosing.** `python tool/fx.py textures --tag Slash --kind flipbook` lists assets and writes a PNG contact sheet with IDs. Find its path in `"sheet"` and open the image. Useful tags include Impact, Slash, Crescent, Smoke, Fire, Flare, Circle, Lightning, Swirl, Star, Wind, Water, and Ground. Use `--collection beams` for Beam textures, `--collection meshes` for meshes, or `--query anneau` and `--query 15268066299` for a name or ID. Flipbook entries include `FlipbookLayout` and mark inferred grids as `estimated`.
2. **Compose from blocks when useful.** `python tool/fx.py blocks` lists flash, sparks, shockwave, smoke, slash, arc, swipe, fire, charge, and orb. Settings include `at`, `position`, `scale`, `intensity`, `color`, `color2`, and block-specific options. Write a plan and run `python tool/fx.py compose plan.json --out recette.json`.

   ```json
   {"name": "Ice strike", "blocks": [
     {"block": "charge", "at": 0, "duration": 0.6, "color": [0.6, 0.85, 1]},
     {"block": "flash", "at": 0.6, "color": [0.7, 0.9, 1]},
     {"block": "sparks", "at": 0.6, "color": [0.6, 0.9, 1]},
     {"block": "shockwave", "at": 0.63, "scale": 1.3},
     {"block": "smoke", "at": 0.65, "color": [0.8, 0.9, 1]}]}
   ```

   Edit the resulting recipe's properties, textures, and timings directly. Add `--base ID` to insert blocks into an existing project.
3. **Inspect the result.** `python tool/fx.py render recette.json --times 0,0.1,0.25,0.5,1` writes a contact sheet to `rendus/`. By default, it keeps the recipe camera and shows a five-stud Roblox dummy for scale. `--auto-camera` frames the full extent of the effect. Open the sheet and check readability, timing, scale, colour, and how each layer ends.
4. **Compare variants.** `python tool/fx.py render a.json b.json c.json --times 0.1,0.3` renders one row per variant with matching camera and times. The same recipe, seed, and time produce the same emulator image.
5. **Validate, save, and export.** Run `python tool/fx.py validate recette.json`, then `python tool/fx.py save recette.json` to make the project visible in the editor. Run `python tool/fx.py export recette.json --format rbxmx` and drag the result into Studio. For a model named `MyEffect`, call `require(workspace.MyEffect.DatakyFX).play()` to play it. `--format lua` produces a standalone ModuleScript that builds the effect itself.

A recipe can be a JSON file or the ID of a saved project in `editor/projects/`. Claude Code discovers the same MCP tools through `.mcp.json`, which runs `python tool/fx_mcp.py`. For Claude Desktop, use **INSTALLER_CLAUDE_DESKTOP.bat**.

## Test manually in Free mode

Select **Timeline / Libre** (Free) or press **Tab**. In Free mode, the clock keeps running, continuous emitters follow their Rate, and bursts wait for **Emit**. The ParticleEmitter panel uses the timing count or defaults to 30. **Emit sélection** includes descendants, **Emit tout** triggers all bursts at their respective counts, and **Vider** clears particles. Enabled toggles in the hierarchy and properties affect only the preview in Free mode. In Timeline mode they change the recipe and grey out a disabled track. Property edits in Free mode still change the recipe and appear immediately. Update the native bridge to use these commands.

Shortcuts are inactive in inputs and dialogs. **Space** plays or pauses, **Shift+Space** stops, **E / Shift+E** emits from the selection / all, **T** toggles Enabled, **Tab** switches modes, and **C** clears. **← / →** steps one frame, **Shift+← / →** steps 0.1 seconds, **Home / End** moves to the start or end, and **[ / ]** jumps between events. **L** loops, **F / Shift+F** frames the selection / whole effect, **G** toggles ground, **M** toggles the dummy, and **1–5** changes backgrounds. **↑ / ↓** selects in the hierarchy and **Alt+↑** selects the parent. **Ctrl+C / Ctrl+V** copies or pastes JSON with descendants between projects. **Ctrl+E** exports `.rbxmx` and **Ctrl+Shift+E** exports `.lua`. Press **?** for the full list. Scrubbing reconstructs emulator history. Restart native playback from zero to reconstruct its history.

## Play multiple instances in your game

`python tool/fx.py export A1_Muzzle.json A2_Impact.json --format library --out exports/MesEffets.lua` writes a recipe module keyed by filename without extension and a separate **DatakyFXKit.lua**. Install them as sibling ModuleScripts.

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MesEffets)
FX.preloadTextures(Recipes) -- Run at startup. This may yield.
FX.prepare(Recipes.A1_Muzzle) -- Optional. Prepares the template ahead of playback.
local h = FX.play(Recipes.A1_Muzzle, muzzle.WorldCFrame, {
    scale=1, speed=1, follow=muzzle, hold=false,
    params={radius=24}, quality="Auto", parent=workspace,
})
-- h:Release({hideParts=true}) hides Parts and lets particles expire.
-- h:Stop() destroys immediately. Use h:Move(cf) or h:Part("node_id").
-- h:SetFollow(autreAttachment) changes the target. h:SetFollow(nil) stops following.
-- FX.freeze() and FX.unfreeze() control particles and the timeline for captures.
```

Each handle is independent and respects the CFrame's rotation. `follow` accepts a function returning a CFrame, an Attachment, a Bone via TransformedWorldCFrame, or a BasePart. `quality="Low"` reduces bursts to 60%. Auto reads the client's SavedQualityLevel when available. The kit cleans up its folder after Release and lets the remaining particles expire. Part Position and Transparency tracks are preview-only unless marked `runtime:true`. Other tracks play normally. Call **FX.preload(recipe)** before playing a recipe with MeshParts. Preloading can yield. `play` remains immediate. Native Trails cannot freeze their history.

The kit caches validation and decoding per recipe table with weak keys. Treat the recipe as immutable after `prepare`, `preload`, `preloadTextures`, `listTextures`, or the first `play`. Make a deep copy to edit a variant. `table.clone` does not copy nested nodes. The first `play` builds a template and subsequent calls clone it. `FX.prepare(recipe)` builds it ahead of time without yielding. For MeshParts, call `FX.preload(recipe)` before preparing.

`h:Release()` stops following permanently and cuts continuous emission. `hideParts=true` immediately hides every Part and MeshPart owned by the handle and lets particles finish. `h:SetFollow(fnOrInstance)` replaces the target. Pass `nil` to stop following. This call has no effect after Release or Stop. `onFinished=function(handle) ... end` runs once after natural completion, Release and particle expiry, or Stop. It runs after cleanup through `task.defer`. Callback errors and yields do not block `play`.

`FX.preloadTextures(recipeOrLibrary)` passes unique explicit particle, Beam, Trail, and mesh texture URIs to `ContentProvider:PreloadAsync`. Call it at startup. It may yield. `FX.listTextures(recipeOrLibrary)` lists the same URIs without loading them. New libraries also provide `Recipes:listTextures()`, which returns a copy. `pairs(Recipes)` still enumerates only recipes. Use `FX.listTextures(Recipes)` if a recipe is named `listTextures`. The kit also accepts libraries exported before this API.

The legacy **`--format lua`** player handles one world-aligned effect at a time and applies an origin translation. Its API and `fx_runtime.lua` remain available. Use the library and kit for multiple animated units.

## Authoring and search tools

`tool/fx_builder.py` exports **Recipe**, **NS**, **CS**, and **NR**. Available methods include `part`, `att`, `em`, `trail`, `light`, `anim`, `flip`, `merge`, and `save`.

```python
from tool.fx_builder import Recipe, NS, CS, NR
fx = Recipe("Muzzle", 1)
fx.part("root")
fx.att("tip", "root", (0, 0, -1))
fx.em("sparks", "tip", "rbxassetid://123", count=12,
      Lifetime=NR(.2, .4), Size=NS((0, .3), (1, 0)),
      Transparency=NS((0, 0), (1, 1)))
fx.save("Muzzle.json")
```

A compose plan can include another recipe by file, ID, or unique short project name.

```json
{"blocks": [{"include":"A1_Muzzle.json","at":0.44,"position":[0,1,-4],"orientation":[0,90,0],"scale":1,
  "positionKeys":[{"time":0,"value":[0,0,0]},{"time":1,"value":[0,0,-10]}]}]}
```

CLI include paths are relative to the plan. `positionKeys` adds an animated translation with times local to the included recipe. The composer prefixes IDs, references, animations, and parameters to avoid collisions. Rotation uses YXZ. Orientations are exact at the keys, but Euler interpolation can change between composed keys. Add intermediate keys for full rotations.

Use `python tool/fx.py textures --query star --compact --no-sheet --exclude-file used.txt` for a compact search. `--exclude-ids 123 456` accepts a direct list. The exclusions apply before pagination and total counts. `python tool/fx.py sheet 123 456 --exclude-file used.txt --out rendus/choix.png` draws grids and marks **USED** while retaining explicitly requested IDs. In MCP, `search_assets` accepts `compact`, `exclude_ids`, and `exclude_file`. `texture_sheet` builds the contact sheet.

Install the regenerated plugin and connect in Edit mode. **Dataky FX → Exporter les textures utilisées** (Export used textures) writes `tool/used_textures/<place name>.txt` for `--exclude-file`. The scan covers ParticleEmitters, Beams, and Trails in the place and literal texture fields in recipe ModuleScripts, without executing modules. It flags unreadable sources and dynamic expressions for manual follow-up. Call the bridge with `POST /api/preview` and `{"action":"export_used_textures"}`, or use `_G.DatakyFXBridge.exportUsedTextures()` for a session.

## Targeted and batch renders

`python tool/fx.py render recette.json --fit NODE_ID --times 0.02,0.06` frames the union of particles alive at the requested times, including their half-size. A ParticleEmitter includes its own particles and its descendants. A Part includes all descendant emitters. The default 90th percentile of distances from the centroid excludes outlying centres before accounting for particle size. `--fit-percentile 100` includes all particles at the selected times. `--fit-all` restores framing across the full simulated duration. With no live particles, the renderer falls back to the containing Part and its Attachments and prints a warning.

Framing transforms the alpha outline of each visible texture cell with the billboard's size, Squash, and rotation. By default, it preserves 90% of each cell's contrast energy (`alpha²`), normalised per cell so pale textures remain included. `--fit-percentile` controls the outline and rejection of isolated particle centres. At 100, every alpha extent and particle is included. With an unavailable thumbnail, the whole quad counts. The camera directly frames visible points without adding billboard depth and recalculates billboards after recentering to account for camera-facing rotation. This changes framing only. Pixel rendering and warning calculations use their existing rules.

`--focus 0,1,-4 --radius 3` frames a sphere of radius 3 along the current camera direction. Its silhouette fills 87.5% of the smaller image dimension. The calculation uses the sphere directly. `--background roblox` selects the light preset. `--background dark` uses a night sky `[0.035,0.045,0.08]` and dark grey ground `[0.16,0.16,0.17]` in RGB 0–1 to approximate `vfx.rbxl`. Without a preset, the renderer uses the recipe background.

`--backgrounds roblox,dark` renders one row per recipe and background with the same camera, times, and seed. It is mutually exclusive with `--background`. Python and MCP accept `backgrounds=["roblox","dark"]` or `"roblox,dark"`. Batch jobs use `backgrounds` too. The renderer and Python accept up to eight presets or `#RRGGBB` colours. MCP lists the presets. JSON provides `rows` for each recipe and background and `sheet` for the dimensions. Individual frames have distinct prefixes for each row.

`python tool/fx.py render-batch jobs.json` uses one Chromium session for multiple views. For example, save a manifest with these jobs.

```json
{"jobs":[
  {"projects":["A1_Muzzle.json"],"out":"rendus/face.png","times":[0,0.1,0.3],"camera":[10,6,12,0,1,0],"fit":"root"},
  {"projects":["A1_Muzzle.json","A2_Impact.json"],"out":"rendus/profil.png","times":[0.1,0.3],"camera":[12,2,0,0,1,0],"focus":[0,1,0],"radius":3}
]}
```

Recipe paths are relative to the manifest. Output paths are relative to the repository. Job options use camelCase, including `autoCamera`, `framesDir`, `fitPercentile`, and `fitAll`. Use `fx_tools.render_batch(jobs)` in Python. `fx_tools.render` and the MCP `render_effect` accept `fit_percentile` and `fit_all`. Playwright and Chromium are required. Geometry and real Chromium tests are available. If Playwright is inaccessible in the sandbox, the real render tests report it.

Single renders, batches, and MCP use the same camera rules. `camera` sets six exact values. `fit` or `focus` frames from the specified direction. Without framing, the recipe camera is used. `autoCamera: true` or `--auto-camera` requests global framing. An explicit camera retains priority. `--no-auto-camera` is still accepted.

## Recipe format

Run `python -c "import sys; sys.path.insert(0,'tool'); from fx_schema import SCHEMA; import json; print(json.dumps(SCHEMA, ensure_ascii=False))"` or use MCP `get_schema` for supported classes, properties, types, and limits.

- `nodes` contains `{id, class, name, parent, properties, timing?}`. Place a ParticleEmitter under a Part or Attachment. A Beam or Trail connects `Attachment0` and `Attachment1`.
- `timing` for emitters, Beams, Trails, and lights is `{start, duration, mode: "burst" | "continuous", count}`. A burst calls `Emit(count)` once at `start`. All timing endpoints must fit within the recipe's `duration`.
- `animations` contains `[{node, property, keyframes: [{time, value}]}]`. Times are in seconds. Values interpolate linearly, while Booleans and enums hold the keyframe value.
- `NumberSequence` uses `[{time, value, envelope}]` and `ColorSequence` uses `[{time, value: [r,g,b]}]`. Normalised time runs from 0 to 1 with up to 20 points.
- Define recipe parameters with `params: {"radius": {"default": 16, "min": 0, "max": 64, "step": 1}}`. Use `scaleWith: {"Size": "radius", "Speed": "radius"}` on a ParticleEmitter. Declare the numeric property explicitly. In addition to the effect scale, the kit applies `options.params.radius / default` to marked properties and their tracks. Editor sliders affect preview only.

## Roblox behaviour and diagnostics

- **Beam curves.** Control points follow Attachment0's **+X** and Attachment1's **−X**. `CurveSize` does not bend a Beam when the unrotated Attachments are aligned. Rotate them with `Orientation` or set `Axis` and `SecondaryAxis`.
- **Beam width without FaceCamera.** Width follows the Attachments' Y axis (UpVector).
- **Beam or Trail texture.** The vertical image axis follows the ribbon's length and the horizontal axis follows its width.
- **Flat ground ring.** Use `Orientation: VelocityPerpendicular`, `Speed` of 0.01, and `EmissionDirection: Top`.
- **Stretched sparks.** With `Orientation: VelocityParallel` and `Rotation: 0`, Roblox measurements showed negative `Squash` stretches along velocity and positive `Squash` across it. Use `Rotation: 90` and positive Squash for a vertical streak. Non-square textures are fitted to a square quad. FacingCamera remains an unmeasured approximation.
- **Particle endings.** `abrupt_transparency` requires both final Transparency below **0.95** and final Size above the greater of 0.05 studs or 5% of peak Size. Shrinking close to zero also gives a clean ending, even with final Transparency of 0.4. The warning combines residual size and opacity.
- **Ground layers.** `flat_layer_negative_zoffset` flags `VelocityPerpendicular` with `EmissionDirection: Top` and `ZOffset < 0`, which may bury a layer below the ground.
- **Dark background contrast.** `dark_ground_contrast` flags emitters with LightEmission below 0.2 and maximum RGB luminance below 0.15 when no bright layer covers their potential presence. A supporting layer needs LightEmission of at least 0.2, maximum luminance of at least 0.45, maximum opacity of at least 0.05, and maximum Size above 0.05 studs. Availability windows use timing, Count or Rate, Enabled and its tracks, Lifetime, and TimeScale. Their union must cover the whole period. `THRESHOLDS` defines the cutoffs. The heuristic does not measure spatial coverage, textures, or native lighting. Other animated properties, envelopes, and emission probabilities remain approximate. An intentionally dark layer may trigger it. Compare `--backgrounds roblox,dark` and check in Studio.
- **Flipbooks with nearly empty first frames.** In Play, OneShot “Upwards flame pillar” `70418763522849` was invisible at Lifetime 0.2–0.45 s despite a clear catalogue preview. Check the first frames, extend Lifetime, or change the texture. `validate` reports the short-lifetime risk, small visible area, saturated additive colour, positive parallel Squash, and abrupt curve endings. Warnings do not invalidate a recipe or change its exit code.
- **Visible area.** `tool/fx_warnings.py::THRESHOLDS` defines all thresholds. Mean equivalent opaque area integrates `alpha × Size² × (1 - Transparency)` over a normalised lifetime from 0 to 1. The threshold is **0.01 stud²**. The integration follows curve points and OneShot cells. Other modes use mean cell alpha. Opaque pixels contribute in full, preserving 1–5 stud pixel dust observed in Play despite low cell coverage. Empty-start risk is separate and requires a first-quarter mean alpha below 0.08 and maximum Lifetime of at most 0.5 s. Colour, background, envelopes, and cumulative particles are outside this heuristic.
- **Estimated grids.** Informational results are hidden by default and reported once per texture in a recipe. `python tool/fx.py validate recette.json --infos` or `--verbose` shows their separate counts and details. After visually confirming a grid, run `python tool/fx.py grid-confirm 11844402871 4` to write the override to `tool/grid_overrides.json`. The corresponding information entry is removed, and search uses the override. Supported square grids are 2, 4, and 8. MCP takes `include_infos: true` on `validate_effect` and `id` and `grid` on `grid_confirm`. Play observations never confirm a grid automatically.
- **Alpha cache.** Local thumbnail statistics are stored in `tool/texture_frames.json` with SHA-256 fingerprints. The catalogue stays intact. The first `validate` computes them on demand. Run `python tool/fx_texture_cache.py [IDs…]` to prefill selected IDs, or omit IDs for the whole catalogue. Mean opacity is an estimate, and native OneShot sequencing requires a Play check. Interlaced PNGs produce a diagnostic. CLI output groups codes with detailed warnings and optional information. MCP also provides `warning_counts`, `infos`, and `info_counts`.
- **`LightEmission: 1`** uses additive blending. Zero uses normal blending for smoke or dust. `Brightness` has an effect only when `LightInfluence` is below 1.
- **`SpreadAngle [180, 180]`** emits in all directions. `Drag` halves emission speed every `1/Drag` seconds without damping acceleration.
- **Attachment axes.** `Orientation` and `Axis` / `SecondaryAxis` are mutually exclusive.
- **Emitter placement.** A ParticleEmitter under an Attachment emits from a point. Under a Part, it uses the Part's dimensions and its own `Shape` (Box, Sphere, Cylinder, or Disc).
- **`VelocityInheritance`** has no effect here because Parts are anchored and moved by property.

## Emulation limits

The library uses 420 × 420 thumbnails. MeshParts and FileMeshes without imported local geometry appear as wireframe boxes. Squash, SpreadAngle distribution, lighting, and bloom are approximations. Ask the user to perform the final visual check in **◉ Roblox Studio** before publishing.

Native Trails do not retain their history in a frozen capture. The bridge relays focus events for the main viewport when it receives them, and the editor warns during native playback on an explicit `window_focused=false`. The initial state is unknown. Event delivery in Edit mode has yet to be measured in this plugin. These events describe the main viewport and cannot guarantee focus detection for the entire Studio window. [Roblox focus event reference](https://create.roblox.com/docs/reference/engine/classes/UserInputService#WindowFocused).

## Development

- Start the editor with `python tool/fx_server.py` on port 48754. The interface lives in `editor/`. The emulator is `editor/emulator.js`. Headless rendering uses Node and Playwright through `tool/fx_render.cjs`.
- Run `node tool/test_fx_frontend.cjs`, `node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs`, and `cd tool && python -m unittest test_fx_server test_fx_templates test_macro test_fx_rbxmx test_fx_tools`. Set `DATAKY_LUAU` to the Luau executable to have `test_fx_rbxmx` run the embedded player in Luau.
- After editing `tool/fx_runtime.lua`, regenerate the plugin with `python tool/fx_package.py`.
- For additional coverage, add `tool/test_fx_render.cjs tool/test_fx_texture_bounds.cjs` to `node --test` and add `test_fx_sandbox test_fx_kit test_fx_builder test_fx_warnings` to unittest. Run `python -m unittest discover -s tool -p 'test_*.py'` for the full Python suite. Luau tests use the extended mock. Native behaviour still needs Studio verification.
- `rendus/` and `exports/` are local outputs ignored by Git.
