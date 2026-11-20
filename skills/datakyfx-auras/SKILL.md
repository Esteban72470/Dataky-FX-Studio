---
name: datakyfx-auras
description: >-
  Create AAA Roblox character Blessings, Auras, Shiny variants, and sleek circular
  NPC/zone interaction rings using DatakyFX, custom procedural Python textures,
  Blender thematic props, and Roblox Studio MCP. Use whenever the user asks to
  make an aura, blessing, character VFX showcase, Shiny VFX variant, ground sigil,
  or circular Beam interaction ring in Roblox.
---

# DatakyFX Auras & Blessings Production Skill

Proven end-to-end pipeline for creating high-craft, viral-quality Roblox **character Auras / Blessings**, **Shiny variants**, and **circular Beam NPC/zone rings** with **DatakyFX** (`<DatakyFX>`).

> Technical formulas, exact Roblox `Beam` Attachment math, and ready-to-copy recipe templates live in [beam-and-texture-math.md](./references/beam-and-texture-math.md). Reusable procedural texture generator: [gen_aura_textures.py](./scripts/gen_aura_textures.py).

---

## 1. The 4-Layer AAA Aura Architecture

Every standout character Aura / Blessing is composed of **up to 4 distinct, readable layers** (never one noisy blob of stacked particles):

1. **Layer 1 — Ground Anchor / Zone Ring** *(optional — omit completely if the user says "pas d'aura au sol"!)*
   - **Modern RPG / NPC / Zone Ring**: Pair a **flat triple-track circular `Beam`** (`fx.circle_beam(..., standing=False)`) with a **silky standing cylindrical `Beam` curtain** (`fx.circle_beam(..., standing=True)`) fading smoothly upward to zero alpha, plus subtle rising perimeter motes. Zero spiky flat particle stacks!
   - **Fantasy / Blessing Ground Sigil**: One crisp rotating `VelocityPerpendicular` sigil (`Speed = 0.01`, `EmissionDirection = Top`, `ZOffset >= 0.05`) framed by an outer luminous `fx.circle_beam` and a gentle ground glow.
2. **Layer 2 — Silhouette-Hugging Orbiting Energy (`Beam` Helices & Splines)**
   - Wrap **2 to 4 ascending conical or cylindrical `fx.helix_ribbon` spirals** around the character (`R ≈ 2.6–4.2` studs for R15/R6, `y = 0.2 → 5.6`).
   - Always use `FaceCamera = true`, **vertical seamless** beam textures (`W < H`, e.g. `512×1024`), and fade `Transparency` smoothly to `1.0` at both ends so ribbons materialize and dissolve organically.
3. **Layer 3 — Signature Thematic Props & Wearables (Blender + Rigging)**
   - Give each Blessing an unmistakable silhouette prop or accessory (e.g., floating orbiting mushrooms, sheriff bandana/hat/spurs, spinning music-box pedestal + wind-up key, half-moon scholar glasses).
   - **Rigging discipline**:
     - Always inspect character proportions in Studio first — never oversize heads/hats.
     - Keep zero clipping at **waist/belt**, **neck/collar**, and **shoulders**; place sleeve cuffs at the **end of sleeves**, never on the shoulder.
     - Set `CanCollide = false`, `CanQuery = false`, `CanTouch = false`, `CastShadow = false`, and `Massless = true` on all floating VFX/wearable parts.
4. **Layer 4 — Living Micro-Detail (`ParticleEmitter` + `PointLight`)**
   - Keep particle rates light and clean (rising sparkles, petals, spores, steam, embers) with smooth fade-in/fade-out `Transparency` and tapered `Size`.
   - Always start continuous auras with **`FX.play(recipe, cf, { prewarm = true, follow = root })`** so slow emitters (`Rate <= 2.0`) appear immediately on frame 0 with zero dead gap.
   - Add one subtle `PointLight` tinted to the core accent color (avoid harsh white blowout).

---

## 2. Step-by-Step Production Workflow

### Step 1 — Inspect the Target Rig & Lighting in Studio
Before authoring anything, run `execute_luau` on the live Studio place to measure:
- Character/NPC bounding box, `HumanoidRootPart` position, exact **ground Y** (especially on stepped daises or slopes so rings never float or sink!).
- Exact base colors of the character (especially for **Shiny** models — read the real `Color` of its parts instead of guessing!).
- Place `Lighting` & `BloomEffect` (`Intensity`, `Threshold`) so `LightEmission` and `Brightness` match the game's actual exposure.

### Step 2 — Source or Generate Textures
1. **Check the DatakyFX catalog first**:
   ```powershell
   $PY = "<DatakyFX>\_runtime\python\python.exe"
   & $PY <DatakyFX>\tool\fx.py textures --tag Swirl --compact
   ```
2. **Generate custom procedural PNGs in Python when you need bespoke motifs or razor-clean Beams** (e.g., silky aurora curtains, triple-track geometric zone rings, custom wind/energy ribbons, thematic motifs like coffee beans, stars, mushrooms, hearts):
   - Use the bundled Python (`$PY`, includes Pillow) and adapt [gen_aura_textures.py](./scripts/gen_aura_textures.py).
   - **Mandatory Beam texture rule**: Roblox `Beam` textures scroll **vertically (top-to-bottom along V)**; width runs **horizontally (left-to-right along U)**. Always author Beam textures tall (`512×1024`), seamless vertically along `Y`, pure white RGB with sculpted alpha so `Beam.Color` tints cleanly.
   - Render a dark contact-sheet preview and inspect it visually before uploading!
3. **Upload via Roblox Studio MCP (`upload_image`)**:
   - Serve the texture folder briefly via `python -m http.server <port> --bind 127.0.0.1 --directory <dir>` (daemon), call `upload_image` in a single batch to get permanent `rbxassetid://...` IDs, and **immediately kill the temporary HTTP server**.

### Step 3 — Build the DatakyFX Recipe (`tool/fx_builder.py`)
Use DatakyFX's native `Recipe` helpers (`fx.circle_beam`, `fx.helix_ribbon`, `fx.spline_ribbon`, `fx.beam`, `fx.em`, `fx.light`, `NS`, `CS`, `NR`).
- If previewing before upload, map custom textures in `local_textures` (stripped automatically on Roblox export) or pass `--tex-map` at render time.
- Remember: `SpreadAngle` must be a JSON list `[x, y]`, not a tuple.

### Step 4 — Validate & Render Offline Preview (with Bloom!)
Run both validation and dual-background rendering before touching Studio:
```powershell
& $PY <DatakyFX>\tool\fx.py validate MyAura.json
& $PY <DatakyFX>\tool\fx.py render MyAura.json `
    --times 0.2,0.8,1.6 --backgrounds dark,roblox --bloom 0.65 `
    --tex-map "rbxassetid://123=C:/path/to/tex.png"
```
- Confirm **zero** `horizontal_beam_texture`, `abrupt_transparency`, or `flat_layer_negative_zoffset` warnings.
- Open the rendered PNG and verify silhouette readability, scale against the 5-stud mannequin, and Bloom intensity on **both** `dark` and `roblox` backgrounds.

### Step 5 — Shiny & Color Variants (Fast Iteration)
To build a **Shiny** version of an existing Blessing without starting from scratch:
1. Extract the Shiny model's exact palette from Studio.
2. Remap the entire DatakyFX recipe palette in one command:
   ```powershell
   & $PY <DatakyFX>\tool\fx.py recolor BaseAura.json `
       --out ShinyAura.json --map "#ff55aa=#2266ff,#ffd480=#ffe044"
   ```
3. Elevate it beyond a plain recolor: swap **1 signature motif/prop** (e.g., cards → floating mushrooms, desert bandito → gold sheriff stars + spurs, normal dancer → spinning music-box pedestal + 360° pirouette idle) and re-verify in Studio.

### Step 6 — Compact Export & Studio Installation
Export compact Lua library code (`~45%` smaller, zero scientific notation) alongside `DatakyFXKit.lua`:
```powershell
& $PY <DatakyFX>\tool\fx.py export MyAura.json `
    --format library --out <DatakyFX>\exports\MyAuras.lua
```
Play in Roblox with instant warm-up:
```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MyAuras)
FX.preloadTextures(Recipes)
local handle = FX.play(Recipes.MyAura, rootPart.CFrame, {
    follow = rootPart,
    prewarm = true,
})
```
- When upgrading existing Hub/NPC interaction zones (`RerollMutationArea`, `SpinArea`, etc.), **preserve all trigger parts (`default`), `ProximityPrompt`s, `BillboardGui`s, and `AuraScaleController`** (updating the scale controller to scale `Beam` curve sizes, widths, and attachment offsets proportionally).

### Step 7 — Mandatory Visual Verification in Studio
Never declare an aura finished without capturing real Studio screenshots (`screen_capture`):
1. **Front + 3/4 wide view**: check overall silhouette, color harmony, and ground alignment.
2. **Close-ups**: check waist/belt, neck, shoulders, sleeve cuffs, and dais/floor contact for **zero clipping** and **zero overhang**.
3. Fix any clipping, color drift, or bloom blowout immediately and re-capture to confirm.

---

## 3. Critical Pitfalls Checklist
- **Zero Beam seams ("interstices" between Beam segments)**:
  - **NEVER** use `TextureMode = Wrap` with an arbitrary float `TextureLength` on multi-segment circles/splines/helices — UV `V` lands on a fractional value at each Attachment and jumps back to `0` on the next Beam, creating a visible seam/cut dash!
  - **ALWAYS** use **`TextureMode = Stretch`** with an **exact integer `TextureLength`** (`1`, `2`, `3` repeats per segment) so `V` lands on an exact integer at every joint (`circle_beam`, `spline_ribbon`, and `helix_ribbon` now default to `tex_mode="Stretch", tex_len=1`).
  - For open multi-segment ribbons/helices with fade-in/fade-out `Transparency` (`1 → 0.2 → 1`), **slice `Transparency` continuously across the full spline** (`slice_sequences=True`, now default in `spline_ribbon`/`helix_ribbon`) — never repeat `1 → 0.2 → 1` on every segment or you get transparent pinch gaps between every knot!
- **`Beam` `CurveSize1` sign**: Roblox computes `C1 = P1 - CurveSize1 * Axis1` (minus sign built-in!). Always pass **POSITIVE** `CurveSize0` and **POSITIVE** `CurveSize1` — negative `CurveSize1` produces pinched square corners.
- **`Beam` `FaceCamera = false` axis**: `Axis` (`X`) = tangent along curve, **`SecondaryAxis` (`Y`) = ribbon WIDTH** (`U=0` at `+Y`, `U=1` at `-Y`), `Z = X × Y` = face normal.
- **Horizontal Beam texture**: Any `Beam` texture with `width > height * 1.15` will smear/stretch sideways; always author vertical (`512×1024`).
- **Elevated daises / uneven floors**: Never assume `Aura.Position.Y` equals the visible floor surface — measure the exact top `Y` of the dais/sigil mesh and place ground rings `+0.03` to `+0.08` studs flush above it.
- **Luau `string.gsub` trap**: When injecting Lua containing `%` (modulo), avoid raw `string.gsub` replacement strings (which treat `%` as captures); use `string.find` + `string.sub` or escape `%%`.
- **Keep Hub FPS high**: Prefer `Beam` rings/ribbons (near-zero draw cost) + low-rate particles (`Rate = 5–16`) over 55-particles/sec stacked flat emitters.
