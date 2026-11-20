# Dataky FX Studio

Dataky FX Studio is a local editor for making Roblox effects by hand or from a JSON recipe. The browser emulates ParticleEmitters, Beams, Trails, lights, and Parts, so you can play, pause, and scrub an effect without opening Roblox Studio. Check the result with native objects in Studio, then export it to your game.

## Open the editor

1. Double-click **DATAKY_FX_STUDIO.bat**. Python 3 is sufficient. The editor requires no AI service or API key.
2. Open **http://127.0.0.1:48754/** or the next free address printed by the launcher. Keep its server window open while you work.
3. Create an effect and play it in **✦ Émulation** (Emulation) directly in the editor.
4. To check the effect in-engine, open your place in Roblox Studio in Edit mode. Click **Studio déconnecté** (Studio disconnected) in the editor, then copy the displayed command to the Studio Command Bar and run it. The connection lasts for that session.

To install the bridge as a local plugin and use the integrated preview, run **INSTALLER_LE_PONT.bat** and restart Studio. On Studio's Plugins tab, the **Dataky FX** toolbar offers **Connexion** (Connect) and **Aperçu** (Preview). Click **Connexion** in the Studio window you want to use. The plugin starts disconnected so you can choose the right window. A Command Bar connection can still edit and play effects. Viewport capture permission requires the installed plugin.

## Create an effect by hand

Start with an **Impact**, **Fumée** (Smoke), **Beam**, or **Trail** template, or with an empty project.

- **Hiérarchie → Ajouter → Briques** (Hierarchy → Add → Blocks) inserts a ready-to-use block at the playhead. Blocks include flash, sparks, shockwave, smoke, slash, arc, trail, fire, charge, and orb. Their objects can be edited like any others.
- Add individual objects with **Hiérarchie → Ajouter**. A ParticleEmitter can go under a Part or an Attachment. Roblox applies volume or point emission accordingly.
- Transparent Parts remain selectable. The viewport shows their outline when selected without changing their exported transparency.
- Select an object to edit its properties. Names and values follow Roblox classes. Curves change size, colour, or transparency over a particle's lifetime.
- Click a curve to open the graph editor. Drag points and Bézier handles, double-click to add a point, and choose linear, ease-in, ease-out, impact, or fade. The start and end points retain their times. Colour gradients have draggable stops and a colour picker. Numeric and XYZ animations also offer **Éditeur graphique** (Graph editor).
- The smooth line is the editable curve. The dotted line shows the sampled approximation exported to Roblox, with up to 20 points. Handles are stored in `editor.curves` so the graph opens as before. Playback uses the samples. Editing the JSON values invalidates the previous handles.
- Apply a texture, beam texture, or mesh by choosing it in the library. The thumbnails help you choose. Studio loads the native asset by ID and applies its usual permissions.
- For a Beam or Trail, set **Attachment0** and **Attachment1** to two points in the effect. A resource from the Beams collection supplies the texture for the ribbon. The Beam or Trail properties control its other settings.
- Set start time, duration, and particle count in the timeline. Property animation keyframe times are in seconds.
- **Appliquer à Studio** (Apply to Studio) builds the composition. **Lire** (Play) starts native playback. **Arrêter** (Stop) cuts emission and clears existing particles. **Fermer l’aperçu** (Close preview) removes the temporary container and restores the scene camera.

Preview effects live on a station away from your place content under `Workspace.__DatakyFXPreview`. The bridge operates within that container. Close the preview before publishing the place.

## Browser emulation

**✦ Émulation** is the default view. It follows the Studio bridge's timing rules for tracks, bursts (`Emit`), continuous emission at `Rate`, and keyframes. Looping clears particles. At the end of an effect, existing particles finish their lifetimes.

Press **Tab** or use **Timeline / Libre** (Free) to switch to the sandbox. In **Libre**, time keeps running, continuous emitters emit at `Rate`, and bursts wait for Emit. The selected ParticleEmitter has a quantity field and an **Emit** button. **Emit sélection** includes descendants, **Emit tout** plays all bursts, and **Vider** clears particles while keeping toggles in place. Changes to Enabled are temporary in **Libre**. In **Timeline**, they are saved to the recipe and disabled bars appear grey. Property edits update the live preview. Reinstall the generated bridge to use this mode in the native preview.

Click **?** for the full shortcut list. **Space / Shift+Space** plays or pauses / stops. **E / Shift+E** emits from the selection / all bursts. **T** toggles Enabled, **Tab** switches modes, and **C** clears. Use the arrow keys and **Home / End** to move the playhead, **[ / ]** to jump between timing starts, **L** for loop, **F / Shift+F** to frame, **G** for ground, **M** for the scale dummy, and **1–5** for backgrounds. Use **↑ / ↓** for the hierarchy and **Alt+↑** for the parent. **Ctrl+C / Ctrl+V** copies JSON with descendants between projects. **Ctrl+E / Ctrl+Shift+E** exports. Keyboard shortcuts are inactive in an input or dialog. Save, history, duplicate, delete, search, and Esc shortcuts remain available. Scrubbing to any time works in the emulator. Restart native playback from zero.

Recipes with `params` show one slider per parameter. For example, `params.radius.default=16` with `scaleWith: {"Size":"radius"}` on a ring lets you resize the ring independently of the other emitters. Sliders only affect the preview.

Emit preserves an explicit pause. After Stop, Emit starts the sandbox again. Switching projects resets particles, the clock, and preview Enabled states. Simple property edits preserve sandbox history. Structural changes and property removal can rebuild the native preview.

- **Lire**, **Pause**, **Arrêter**, and the timeline control emulation. Click the timeline to preview the effect at that instant. The deterministic simulation uses a fixed seed and a 1/60-second time step to replay particle and Trail history up to the selected time.
- **Rejouer les changements** (Replay on change) restarts the effect after each edit.
- Drag the view to orbit. Shift-drag or right-drag to pan, and scroll to zoom. **Caméra du projet** (Project camera) restores the saved camera. **Garder ce cadrage** (Save framing) stores the current camera for renders and Studio.
- **Fond** (Background) uses `environment.background` from the recipe until you choose a preset. Try dark, grey, clear sky, black, or **roblox** (light blue sky and light grey ground), and toggle **Sol** (Ground). PointLights, SpotLights, and SurfaceLights illuminate the ground. Check light backgrounds too, since additive colours can clip to white.
- **Mannequin** (Dummy) adds a five-stud Roblox character for scale. **Cadrer** (Frame) backs the camera away until the whole effect fits from the current angle.
- **Capturer** (Capture) saves the displayed frame and its time as `capture_source: browser-emulator`.

### Emulated features

- Box, Sphere, Cylinder, and Disc emitter shapes with ShapeStyle, ShapeInOut, and ShapePartial.
- EmissionDirection, SpreadAngle, Speed, Lifetime, Acceleration, Drag, Rotation, RotSpeed, TimeScale, and LockedToPart.
- Size, Transparency, Squash, and Color over a particle's lifetime, including envelopes.
- FacingCamera, FacingCameraWorldUp, VelocityParallel, and VelocityPerpendicular.
- Grid2x2 through 8x8 and Custom flipbooks in Loop, OneShot, PingPong, and Random modes with blending.
- LightEmission, LightInfluence, Brightness, and ZOffset.
- Beams with Bézier curves, CurveSize, widths, Segments, FaceCamera, TextureMode, TextureLength, and TextureSpeed.
- Trails with Lifetime, MinLength, MaxLength, WidthScale, FaceCamera, and TextureMode.
- Block, Ball, and Cylinder Parts, Sphere, Cylinder, and Brick SpecialMeshes, Neon material, and lights.

### Emulation limits

- In Play testing with `VelocityParallel` and `Rotation: 0`, negative Squash stretched along the velocity and positive Squash stretched across it. Use `Rotation: 90` with positive Squash for vertical streak textures. FacingCamera remains an unmeasured approximation.
- The plugin connection message appears once in Edit mode and stays out of the client and server Play logs.
- The library uses mostly **420 × 420** Roblox thumbnails. A Roblox ID without a local preview gets a fallback halo and a status message. Original textures under `rbxasset://textures/dataky-local/...` use their PNG files. A missing original is transparent and generates a warning. Other built-in `rbxasset://` textures are approximated with generated shapes.
- Imported OBJ geometry is rendered in 3D. Without local geometry, MeshParts and FileMesh SpecialMeshes appear as wireframe boxes. [Local OBJ format](docs/MESH_PREVIEW.md).
- On Beams and Trails, the emulator maps the **vertical image axis along the ribbon**. This matches most of the 447 textures in the Beams collection.
- Squash, SpreadAngle distribution, lighting, bloom, graphics quality, and particle sorting are approximated from the official documentation. VelocityInheritance has no effect here or in the bridge, where Parts are anchored and moved by property.
- Use **◉ Roblox Studio** to check the result before publishing.

## Verify in Roblox Studio

In **◉ Roblox Studio**, click **Activer l’aperçu intégré** (Enable integrated preview). On first use, the bridge builds the effect and asks for permission to capture the Studio viewport. Accept in Studio. The editor then displays the captured frames. Keep Studio open with the preview document active. Minimising the window or switching to a document that cannot be captured can pause the stream. The bridge retries without asking for permission again.

Restart Studio after updating the capture bridge. Automated checks cover transport, curves, and integration. The first real stream still requires permission in Studio.

The native stream uses `StudioCaptureService` at about **4 frames per second** and up to 1280 × 720, with bandwidth adjusted to the HTTP limits. For smoother playback, use **Utiliser le partage de fenêtre en secours** (Use window sharing as a fallback), then select the Studio window in your browser.

**Rejouer les changements** restarts the composition after edits. Clear it to restart only when you click Play. **Capturer l’aperçu** (Capture preview) saves a local PNG with the actual project and render time for comparison or review by an assistant. Live frames stay in memory. The editor drops old frames when you change the project or stop the preview.

Use the **plan de scène** (Scene plan) for placement and the timeline to edit settings and animations. Scrubbing in the native preview cannot reconstruct arbitrary particle or Trail history. Restart native playback to review an effect. Particles and Beams support pausing. Effects with Trails report that their history cannot be paused faithfully.

Backgrounding Studio can slow particle simulation, as measured in Play mode. The bridge may relay main viewport focus events. The editor warns during playback only when it receives an explicit focus loss. An unknown state produces no warning. Delivery of these events in Edit mode still needs Studio verification. A native Trail continues losing its history during a frozen capture. [Documented viewport focus API](https://create.roblox.com/docs/reference/engine/classes/UserInputService#WindowFocusReleased).

Camera, lighting, graphics settings, randomness, and asset permissions affect appearance. Native playback can vary between runs.

## Save and reuse an effect

**Enregistrer** (Save) writes the project to `editor/projects/`. The browser draft and undo/redo history help while editing. Use Save to keep a project file. **Recette JSON** (JSON recipe) lets you inspect, copy, import, and edit the whole composition.

For Roblox, use **Exporter → Modèle Roblox .rbxmx** (Export → Roblox model), then drag the file into Studio. The model contains editable Parts, Attachments, emitters, Beams, and lights, plus a `DatakyFX` ModuleScript that plays the timeline on those objects.

```lua
local fx = require(workspace.MonEffet.DatakyFX)
fx.play()
-- fx.stop(), fx.pause(), fx.resume(), fx.status()
```

Each object has a `DatakyFXNodeId` attribute so the timeline can find it even after you rename it or change its properties. Move the model with its pivot. Position tracks follow the translation but do not apply pivot rotation. Emitters with timing are disabled in the file and enabled by the player at the right moment. Imported MeshParts retain their MeshId. Check their size in Studio.

**Exporter** also offers the project JSON and a standalone Luau ModuleScript that builds and plays the effect independently of the editor, bridge, and AI.

```lua
local fx = require(game.ReplicatedStorage.MonEffet)
fx.build(workspace, Vector3.new(0, 4, 0))
fx.play()
-- fx.stop(), fx.clear(), fx.pause(), fx.resume(), fx.status()
```

The origin offset applies to Parts. Attachments keep their local positions. For an effect on a moving character, the game code must manage the attachment. Game logic and network replication are handled by your game.

The legacy `.lua` export plays one world-aligned effect at a time. Use a library to play multiple instances.

```powershell
python tool/fx.py export A1_Muzzle.json A2_Impact.json --format library --out exports/MesEffets.lua
```

This produces `MesEffets.lua` with recipes indexed by filename and a separate `DatakyFXKit.lua`. Put them in sibling ModuleScripts.

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MesEffets)
local h = FX.play(Recipes.A1_Muzzle, muzzle.WorldCFrame, {
    follow=muzzle, scale=1, speed=1, hold=false, quality="Auto",
})
-- h:Release(), h:Stop(), h:Move(cframe), h:Part("id")
-- FX.freeze(), FX.unfreeze()
```

The kit respects rotation, follows an Attachment, Bone, or BasePart or a function returning a CFrame, and cleans up each instance independently. `Release` stops continuous emission and lets particles expire. `Stop` destroys everything immediately. Set `params={radius=24}` to override properties marked with `scaleWith`. Property tracks play except preview-only Part position and transparency tracks. `Low` reduces bursts to 60% and `Auto` reads the available quality setting. Call `FX.preload(recipe)` before playing MeshParts. Preloading may yield. `FX.play` never yields. Native Trail history cannot be frozen.

The kit caches validation and decoding per recipe table with weak keys and clones a template. `FX.prepare(recipe)` builds that template in advance without yielding. For MeshParts, call `FX.preload(recipe)` first. Keep recipes immutable after the kit first reads them. Use a deep copy to edit a variant. `table.clone` creates a shallow copy.

`h:Release({hideParts=true})` hides all Parts and MeshParts immediately and lets particles finish. Release stops following for good. `h:SetFollow(fnOrInstance)` changes the target. Pass `nil` to stop following. It has no effect after Release or Stop. The `onFinished=function(h) ... end` callback runs once after cleanup, including for Stop. The kit defers and protects it with `task.defer`, so callback errors or yields do not block `play`.

At startup, `FX.preloadTextures(Recipes)` or `FX.preloadTextures(Recipes.A1_Muzzle)` may wait on `ContentProvider:PreloadAsync`. `FX.listTextures(Recipes)` lists unique URIs without preloading. A newly exported library also supports `Recipes:listTextures()`. Only recipes are enumerated by `pairs`. If a recipe has that name, use `FX.listTextures`. Earlier library modules work with the new kit.

In the connected Edit-mode plugin, **Dataky FX → Exporter les textures utilisées** (Export used textures) scans ParticleEmitter, Beam, and Trail instances in the place as well as literal texture fields in recipe ModuleScripts. It writes `tool/used_textures/<place name>.txt` for use with `--exclude-file`. Modules are read without execution. Inaccessible sources and calculated texture expressions are reported as partial coverage.

## Write, search, and verify from Python

`tool/fx_builder.py` provides `Recipe`, `NS`, `CS`, `NR`, and the part, att, em, trail, light, anim, flip, merge, and save methods. See that module and [the Claude guide](CLAUDE.md) for signatures and examples.

A compose plan can include a rotated and offset recipe with `{"include":"A1_Muzzle.json","at":0.44,"position":[0,1,-4],"orientation":[0,90,0],"scale":1}`. Paths resolve relative to the plan. `positionKeys` adds animated local translation. References, animations, and parameters are remapped. Orientation is exact at the keyframes, with Euler interpolation between composed keys.

- `python tool/fx.py textures --query star --compact --no-sheet --exclude-file used.txt` prints a compact table and skips used textures. `--exclude-ids 123 456` accepts IDs directly.
- `python tool/fx.py sheet 123 456 --exclude-file used.txt --out rendus/choix.png` displays the chosen IDs, flipbook grids, and a USED badge where applicable.
- `python tool/fx.py validate recette.json` shows a summary by code followed by detailed warnings. Estimated-grid information is separate and hidden by default. Show it with `--infos` or `--verbose`. Each texture appears once in the informational results. Warnings do not make a valid recipe invalid or change its exit code.
- `python tool/fx.py grid-confirm 11844402871 4` records a visually confirmed grid in `tool/grid_overrides.json` and clears the corresponding informational entry. The catalogue data stays intact. The file supports square 2, 4, or 8 grids. Search also honours these overrides.
- A final Size near zero or Transparency of at least **0.95** does not trigger `abrupt_transparency`. The warning requires both Transparency below 0.95 and Size above the larger of 0.05 studs or 5% of peak Size.
- `flat_layer_negative_zoffset` warns about flat `VelocityPerpendicular` and `Top` layers with `ZOffset < 0`, which may render below the ground. `dark_ground_contrast` warns about almost-black layers with peak luminance below 0.15 and LightEmission below 0.2 when no bright layer covers their lifetime. Supporting layers need luminance of at least 0.45, LightEmission of at least 0.2, and visible size and opacity. The windows account for timing, Enabled, Count or Rate, Lifetime, and TimeScale. `THRESHOLDS` defines the cutoffs. These heuristics do not simulate positions, textures, engine lighting, or animated properties other than Enabled.
- Visibility diagnostics estimate **equivalent opaque area in studs²** from the lifetime average of `alpha × Size² × (1 - Transparency)`. The threshold is **0.01 stud²**. Fully opaque pixels count at full weight, preserving the small dust and pixel stars observed in Play. `tool/fx_warnings.py::THRESHOLDS` defines the thresholds. Colour, background, envelopes, and combined emitters affect the accuracy of the estimate.
- OneShot flipbooks with nearly empty first frames can disappear with a short Lifetime. This was observed with `70418763522849` at 0.2–0.45 seconds. Alpha information is cached on demand in `tool/texture_frames.json`. Run `python tool/fx_texture_cache.py` to prefill it. The diagnostics use thumbnails and heuristics. Verify in Play.
- `python tool/fx.py render recette.json --fit NODE_ID --times 0.02,0.06` frames live particles at the requested times, including their half-size. An emitter includes its own particles and a Part includes particles from descendant emitters. The 90th percentile of distances from the centroid excludes outliers. Tune it with `--fit-percentile` (greater than 0 and up to 100). With no particles, the renderer reports that it framed the Part and its Attachments. Use `--fit-all` for the legacy framing of the full simulated extent and duration.
- The renderer transforms the visible frame outline by particle size, rotation, and Squash. It keeps 90% of the alpha-squared energy per cell by default, preserving faint textures while excluding isolated halos. `--fit-percentile 100` keeps all alpha and particles. If a thumbnail is unavailable, the full quad counts. The camera uses those points directly without adding artificial billboard depth. Rendering and visibility diagnostics themselves are unaffected.
- `--focus 0,1,-4 --radius 3` frames a sphere of radius 3 at 87.5% of the smaller image dimension and keeps the camera direction.
- `python tool/fx.py render-batch jobs.json` uses one Chromium process to render multiple recipes, times, and cameras. A manifest such as `{"jobs":[{"projects":["recette.json"],"out":"rendus/vue.png","times":[0,0.1],"camera":[10,6,12,0,1,0]}]}` can specify multiple views. Job options use camelCase, including `fitPercentile` and `fitAll`. Recipe paths are relative to the manifest and output paths are relative to the repository. Playwright is required. If the installed Playwright cannot be accessed, the renderer reports that the real captures could not run.

MCP offers the same filters and exclusions, `texture_sheet`, `fit`, `fit_percentile`, `fit_all`, `focus`, `radius`, `render_batch`, validation warnings and summaries through `validate_effect` with optional `include_infos`, `grid_confirm`, and library export.

## Use from an assistant or another tool

Claude or another assistant can inspect texture contact sheets, compose blocks, render and compare versions, validate, save, and export through the same tools.

- For **Claude Desktop**, run **INSTALLER_CLAUDE_DESKTOP.bat**, then restart Claude Desktop. The MCP server `tool/fx_mcp.py` adds Dataky FX tools to the conversation so you can ask for an effect such as an ice explosion. The installer backs up the configuration to a `.bak` file.
- For **Claude Code**, open this folder. [CLAUDE.md](CLAUDE.md) documents the workflow and Roblox details. `.mcp.json` registers the same MCP server with `python`. Change it to `py` if your setup requires that command. The CLI is also available.

```powershell
python tool/fx.py textures --tag Slash --kind flipbook   # Texture sheet with IDs
python tool/fx.py blocks                                 # Available blocks
python tool/fx.py compose plan.json --out recette.json   # Turn the plan into a recipe
python tool/fx.py render recette.json variante.json      # One sheet row per variant
python tool/fx.py export recette.json --format rbxmx     # Import the model into Studio
```

Renders use automatic framing and a scale dummy. Use `--no-auto-camera` and `--no-dummy` to turn them off. Contact sheets go to `rendus/` and exports to `exports/`. An assistant uses these tools to inspect and edit its work. Artistic choices come from the requested direction and VFX guidance.

Node.js and Playwright handle rendering. The lower-level command creates a PNG contact sheet at specific times.

```powershell
node tool/fx_render.cjs editor/projects/dataky-impact.json --out rendu.png --times 0,0.1,0.25,0.5
node tool/fx_render.cjs dataky-impact --frames 8 --size 640x360 --camera 8,4,10,0,1,0
node tool/fx_render.cjs variante-a.json variante-b.json --times 0.1,0.3 --auto-camera --dummy
```

Install Chromium for Playwright with `npm install -g playwright` followed by `npx playwright install chromium`. Rendering needs neither the editor server nor Studio. The same recipe, seed (`--seed`), and time produce the same frame. Change one setting and rerender to compare. `--frames-dir` saves individual frames. `--background`, `--no-ground`, and `--fov` mirror the editor's options. The JSON result lists files, rendered times rounded to a 1/60-second step, and warnings such as missing textures or unsupported meshes.

Single renders, `render-batch`, and MCP share camera precedence. `--camera px,py,pz,tx,ty,tz` sets an exact camera. `--fit` or `--focus` requests framing. Otherwise the renderer keeps the recipe camera. `--auto-camera` or `autoCamera: true` requests global framing while preserving an explicit camera's precedence. The legacy `--no-auto-camera` remains available.

`--background dark` uses a night sky and dark grey ground inspired by `vfx.rbxl`. It approximates that place's lighting. Use `--backgrounds roblox,dark` for one row per recipe and background with identical camera, times, and seed. Python, MCP, and batch jobs accept either `background="dark"` or `backgrounds=["roblox","dark"]`. The latter also accepts a comma-separated string. The choices are mutually exclusive. The JSON report lists the rows and sheet dimensions, and individual frame names distinguish the rows.

Without Node, open **http://127.0.0.1:48754/render.html?project=ID&frames=8** to view a sheet for a saved project. It accepts `times`, `size`, `columns`, `background`, `ground=0`, and `seed`. In the editor, `window.DatakyFX.emulator` exposes `play()`, `stop()`, `seek(t)`, `frame(t)` (a PNG data URL), and `sheet(options)`.

For assistant-driven work, choose textures from their contact sheets, compose or write the recipe, validate it, render it, inspect the result, and iterate. Save and export the final `.rbxmx` model.

### Local API

The API serves the same recipe used by the editor.

| Route | Use |
| --- | --- |
| `GET /api/schema` | List supported classes, properties, types, values, and limits. |
| `GET /api/catalog` | Get assets and tags for all three collections. |
| `GET /api/projects` | List saved projects. |
| `GET /api/project/ID` | Read a recipe. |
| `POST /api/project` | Validate and save a JSON recipe. |
| `POST /api/preview` | Accepts `{ "action": "play", "project": { ... } }` and supports apply, play, stop, clear, pause, and resume. |
| `GET /api/status` | Get Studio connection status, errors, and native results. |
| `GET /api/preview/frame` | Get integrated stream status and metadata for the latest recent frame. |
| `GET /api/preview/frame.png` | Get the latest native frame without caching. Returns an error when no recent frame exists. |
| `POST /api/snapshot` | `{ "native": true }` saves the recent native frame with its real time and project. |
| `GET /api/export/ID.json` | Download a project. |
| `GET /api/export/ID.lua` | Download the standalone ModuleScript. |
| `GET /api/export/ID.rbxmx` | Download the Roblox model with a player for import into Studio. |
| `GET /api/blocks` | Get available blocks and settings. |
| `POST /api/compose` | `{ "project": {…}, "blocks": [{ "block": "flash", "at": 0 }] }` adds blocks and returns the unsaved recipe. |
| `GET /api/snapshots` | List manually saved captures from the Studio view. |

An assistant needs access to the API or to the files and contact sheets. The editor does not grant automatic screen access. Project text is never executed as code. Fix unknown properties, invalid references, and parent cycles before saving or playing the recipe.

## Catalogue and maintenance

The offline library remains available in **catalogue.html**. Run **METTRE_A_JOUR.bat** to rebuild exports and thumbnails from saved captures, or **tool/macro.bat** to recapture the plugin lists. Both work independently of effect creation.

Projects, previews, and scripts stay local. Manual editing and effect playback require no ChatGPT calls.
