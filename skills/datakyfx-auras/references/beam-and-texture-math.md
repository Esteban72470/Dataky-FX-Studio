# Roblox Beam Math, Custom Texture Specs & DatakyFX Aura Templates

Empirical formulas and patterns verified live in Roblox Studio and matched 1:1 in DatakyFX (`tool/fx_builder.py`, `tool/fx_kit.lua`, `editor/emulator.js`).

---

## 1. Exact Roblox `Beam` Math

### Cubic Bézier Control Points (Sign Convention)
For a `Beam` between `Attachment0` (`P0`, `Axis0 = X0`) and `Attachment1` (`P1`, `Axis1 = X1`):
- `C0 = P0 + CurveSize0 * Axis0`
- `C1 = P1 - CurveSize1 * Axis1`  *(the minus sign is built into the Roblox engine!)*

Therefore:
- **Exact 4-Quarter-Arc Circle** (radius `R`, `kappa = 0.55228475`, `<0.027%` radial error):
  - 4 Attachments at `θ = 0, π/2, π, 3π/2`:
    - `pos = (R cos θ, y, R sin θ)`
    - `tangent = (-sin θ, 0, cos θ)` → `Axis` (`X`)
  - On each of the 4 Beams (`A0→A1`, `A1→A2`, `A2→A3`, `A3→A0`):
    - **`CurveSize0 = +kappa * R`**
    - **`CurveSize1 = +kappa * R`** *(POSITIVE!)*
- **General `N`-Segment Circle**:
  - `dθ = 2π / N`, handle length = `+(4/3) * R * tan(dθ / 4)` for BOTH `CurveSize0` and `CurveSize1`.
- **General C1 Parametric Curve / Conical Helix `P(t)`** (`t ∈ [0, 1]`, split into `N` segments of `dt = 1/N`):
  - At knot `t_i`: `Axis_i = P'(t_i).Unit`.
  - For segment `[t_i, t_{i+1}]`:
    - **`CurveSize0 = (|P'(t_i)| * dt) / 3`** *(POSITIVE!)*
    - **`CurveSize1 = (|P'(t_{i+1})| * dt) / 3`** *(POSITIVE!)*

### `FaceCamera = false` Attachment Orientation & UV Mapping
- **`V` (0 → 1, top-to-bottom of PNG)** runs along the curve from `Attachment0` to `Attachment1` and scrolls via `TextureSpeed`.
- **`U` (0 → 1, left-to-right of PNG)** spans across the ribbon's `Width`:
  - **`U = 0` sits at `+SecondaryAxis` (`+Y`)**
  - **`U = 1` sits at `-SecondaryAxis` (`-Y`)**
  - Surface normal is `Z = Axis × SecondaryAxis`.

| Ring Type | `X (Axis)` | `Y (SecondaryAxis)` | `Z (Normal)` | UV Layout (`512×1024` PNG) |
| :--- | :--- | :--- | :--- | :--- |
| **Flat Horizontal Ground Ring** | `tangent` | `+radialOut` | `+up` | `U=0` = crisp outer rim, `U=1` = inner edge |
| **Standing Cylindrical Curtain** | `tangent` | `-up = (0,-1,0)` | `+radialOut` | `U=0` = bright ground line, `U=1` = feathered top in air |

```lua
-- Flat ground ring (yBase = floor + 0.05)
att.CFrame = CFrame.fromMatrix(Vector3.new(px, yBase, pz), tangent, radialOut, Vector3.new(0, 1, 0))

-- Standing vertical curtain (centerY = yBase + curtainHeight * 0.5)
att.CFrame = CFrame.fromMatrix(Vector3.new(px, centerY, pz), tangent, Vector3.new(0, -1, 0), radialOut)
```

---

## 2. DatakyFX `fx_builder.py` Aura Recipe Template

Uses the upgraded native primitives (`circle_beam`, `helix_ribbon`, `local_textures`) so you can author, preview with `--bloom`, recolor for Shiny variants, and export compact Lua cleanly:

```python
import sys
sys.path.insert(0, r"<DatakyFX>\tool")
from fx_builder import Recipe, NS, CS, NR

TEX_CURTAIN = "rbxassetid://127999048780262"
TEX_GROUND  = "rbxassetid://103019753096184"
TEX_RIBBON  = "rbxassetid://83778218037109"
TEX_SPARK   = "rbxassetid://243098098"

fx = Recipe("MyBlessing_Aura", duration=4.0)
fx.part("root")

# Optional: map local PNGs for offline Playwright render before upload
fx.data["local_textures"] = {
    TEX_CURTAIN: r"C:\path\to\npc_ring_curtain.png",
    TEX_GROUND:  r"C:\path\to\npc_ring_ground.png",
    TEX_RIBBON:  r"C:\path\to\wind_stream_beam.png",
}

main_col = CS((0, (1.0, 0.25, 0.35)), (0.5, (1.0, 0.65, 0.55)), (1, (1.0, 0.25, 0.35)))
core_col = CS((0, (1.0, 0.85, 0.75)), (0.5, (1.0, 0.30, 0.35)), (1, (1.0, 0.85, 0.75)))

# Layer 1A — Sleek flat triple-track ground ring (omit if "pas d'aura au sol")
# NOTE: tex_mode="Stretch" + exact integer tex_len=1 guarantees ZERO seam at the 90° joints!
fx.circle_beam(
    "ground_ring", "root",
    radius=4.6, y=0.06, width=1.6,
    color_seq=core_col, trans_seq=NS((0, 0.08), (1, 0.08)),
    tex=TEX_GROUND, segments=4, beam_segments=36,
    tex_mode="Stretch", tex_len=1, tex_speed=-0.16, light_emission=0.9,
    face_camera=False, standing=False, z_offset=0.02,
)

# Layer 1B — Silky standing luminous energy curtain
fx.circle_beam(
    "curtain_ring", "root",
    radius=5.35, y=1.30, width=2.5,
    color_seq=main_col, trans_seq=NS((0, 0.14), (1, 0.14)),
    tex=TEX_CURTAIN, segments=4, beam_segments=36,
    tex_mode="Stretch", tex_len=1, tex_speed=0.28, light_emission=0.92,
    face_camera=False, standing=True, z_offset=0.05,
)

# Layer 2 — Two opposing ascending helix ribbons hugging the character silhouette
# NOTE: slice_sequences=True (default) slices trans_seq continuously across all segments (zero gaps between knots!)
for idx, start_ang in enumerate((0.0, 3.14159)):
    fx.helix_ribbon(
        f"helix_{idx}", "root",
        radius_start=3.6, radius_end=2.4,
        y_start=0.4, y_end=5.4,
        turns=1.25, start_angle=start_ang, steps=12,
        width_min=0.45, width_max=1.05,
        color_seq=main_col,
        trans_seq=NS((0, 1.0), (0.15, 0.28), (0.82, 0.32), (1, 1.0)),
        tex=TEX_RIBBON, tex_mode="Stretch", tex_len=1, tex_speed=0.9,
        light_emission=0.85, face_camera=True,
    )

# Layer 4 — Gentle rising sparkles + subtle accent PointLight
fx.att("motes_att", "root", (0, 0.4, 0))
fx.em(
    "rising_motes", "motes_att", TEX_SPARK,
    mode="continuous", Rate=12,
    Color=core_col,
    Size=NS((0, 0.0), (0.2, 0.24), (0.8, 0.14), (1, 0.0)),
    Transparency=NS((0, 1.0), (0.2, 0.12), (0.8, 0.35), (1, 1.0)),
    Lifetime=NR(1.5, 2.5), Speed=NR(1.2, 2.4),
    SpreadAngle=[20, 20], LightEmission=1.0, LightInfluence=0.0,
)
fx.light("aura_glow", "motes_att", Color=[1.0, 0.35, 0.38], Brightness=1.6, Range=12)

fx.save("MyBlessing_Aura.json")
```

---

## 3. Procedural Texture Upload Pattern (`upload_image` MCP)

1. Generate vertical `512×1024` (Beams) or square `512×512` (Particles/Sigils) RGBA PNGs in Python with pure white RGB (`255, 255, 255`) and smooth feathered alpha.
2. Render a dark preview contact sheet (`RGB (14, 18, 28)`) and visually inspect before uploading.
3. Start a local temporary HTTP server daemon:
   ```powershell
   & "<DatakyFX>\_runtime\python\python.exe" `
       -m http.server 18945 --bind 127.0.0.1 --directory "<texture_dir>"
   ```
4. Call MCP `upload_image` with `["http://127.0.0.1:18945/tex1.png", ...]` and save the returned `rbxassetid://...` IDs.
5. **Kill the HTTP server task immediately** after `upload_image` returns.

---

## 4. Proven Reference Textures Already Uploaded (Reusable!)
- **Silky Vertical Wind / Energy Stream Beam (`512×1024`)**: `rbxassetid://83778218037109`
- **Silky Standing Zone Curtain (`512×1024`, `U=0` ground → `U=1` feathered top)**: `rbxassetid://127999048780262`
- **Triple-Track Sleek Ground Ring (`512×1024`, `U=0` outer rim → `U=1` inner)**: `rbxassetid://103019753096184`
- **Airy Curved Wind-Wisp Particle (`512×512`)**: `rbxassetid://73130927868897`
- **Soft Crisp Glow Spark (`512×512`)**: `rbxassetid://243098098`
