"""
Generate reusable, pure-white alpha-sculpted vertical Roblox Beam textures
and airy particle wisps for DatakyFX Auras / Blessings / NPC interaction rings,
plus a dark contact-sheet preview (_preview_sheet.png).

Usage:
    python gen_aura_textures.py --out ./my_textures
"""
import argparse
import math
import os
from PIL import Image, ImageDraw, ImageFilter


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def make_energy_ribbon_beam(out_dir):
    """512x1024 RGBA vertical seamless silky energy/wind ribbon for Roblox Beam."""
    W, H = 512, 1024
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    px = img.load()
    two_pi = 2.0 * math.pi

    for y in range(H):
        v = y / H
        c1 = 0.50 + 0.085 * math.sin(two_pi * (v * 1.0 + 0.10)) + 0.03 * math.sin(two_pi * (v * 2.0 + 0.35))
        c2 = 0.30 + 0.065 * math.sin(two_pi * (v * 2.0 + 0.55)) - 0.025 * math.cos(two_pi * (v * 1.0))
        c3 = 0.72 + 0.060 * math.sin(two_pi * (v * 2.0 + 0.15)) + 0.03 * math.sin(two_pi * (v * 3.0 + 0.40))
        c4 = 0.43 + 0.110 * math.cos(two_pi * (v * 1.0 + 0.70))

        p1 = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(two_pi * v))
        p2 = (0.5 + 0.5 * math.sin(two_pi * (v * 2.0 + 0.32))) ** 1.4
        p3 = (0.5 + 0.5 * math.sin(two_pi * (v * 2.0 + 0.78))) ** 1.5
        p4 = (0.5 + 0.5 * math.sin(two_pi * (v * 3.0 + 0.12))) ** 1.8

        w1 = 0.055 + 0.022 * math.sin(two_pi * (v * 2.0 + 0.2))
        w2 = 0.038 + 0.015 * math.cos(two_pi * (v * 1.0 + 0.6))
        w3 = 0.035 + 0.014 * math.sin(two_pi * (v * 3.0 + 0.1))
        w4 = 0.022

        for x in range(W):
            u = x / (W - 1)
            env_u = smoothstep(0.02, 0.18, u) * smoothstep(0.98, 0.82, u)
            if env_u <= 0.001:
                continue
            veil = math.exp(-((u - 0.50) / 0.28) ** 2) * (0.14 + 0.06 * math.sin(two_pi * v))
            s1 = math.exp(-((u - c1) / w1) ** 2) * (0.85 * p1)
            s2 = math.exp(-((u - c2) / w2) ** 2) * (0.68 * p2)
            s3 = math.exp(-((u - c3) / w3) ** 2) * (0.65 * p3)
            s4 = math.exp(-((u - c4) / w4) ** 2) * (0.55 * p4)
            core1 = math.exp(-((u - c1) / (w1 * 0.35)) ** 2) * (0.45 * p1)
            a = clamp((veil + s1 + s2 + s3 + s4 + core1) * env_u)
            if a > 0.002:
                px[x, y] = (255, 255, 255, int(a * 255))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    path = os.path.join(out_dir, "energy_ribbon_beam.png")
    img.save(path)
    return path


def make_standing_curtain_beam(out_dir):
    """512x1024 RGBA vertical seamless silky aurora curtain (U=0 ground, U=1 feathered top)."""
    W, H = 512, 1024
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    px = img.load()
    two_pi = 2.0 * math.pi

    for y in range(H):
        v = y / H
        wave_h1 = 0.72 + 0.14 * math.sin(two_pi * (v * 1.0 + 0.15)) + 0.06 * math.sin(two_pi * (v * 2.0 + 0.4))
        wave_h2 = 0.54 + 0.12 * math.sin(two_pi * (v * 2.0 + 0.65))

        for x in range(W):
            u = x / (W - 1)
            bot_fade = smoothstep(0.0, 0.03, u)
            top_fade = smoothstep(0.96, 0.48, u)

            base_line = math.exp(-((u - 0.055) / 0.018) ** 2) * 1.00
            base_halo = math.exp(-((u - 0.075) / 0.075) ** 2) * 0.52

            rib1_u = 0.22 + 0.055 * math.sin(two_pi * (v * 1.0 + 0.10))
            rib1 = math.exp(-((u - rib1_u) / 0.040) ** 2) * (0.28 + 0.16 * math.sin(two_pi * (v * 2.0 + 0.2)))

            rib2_u = 0.36 + 0.070 * math.sin(two_pi * (v * 2.0 + 0.55))
            rib2 = math.exp(-((u - rib2_u) / 0.055) ** 2) * (0.18 + 0.10 * math.cos(two_pi * (v * 1.0 + 0.8)))

            veil1 = (clamp(1.0 - u / max(wave_h1, 0.1)) ** 2.1) * 0.44
            veil2 = (clamp(1.0 - u / max(wave_h2, 0.1)) ** 1.7) * 0.22 * (0.65 + 0.35 * math.sin(two_pi * (v * 2.0 - u * 0.5)))

            a = clamp((base_line + base_halo + rib1 + rib2 + veil1 + veil2) * bot_fade * top_fade)
            if a > 0.002:
                px[x, y] = (255, 255, 255, int(a * 255))

    img = img.filter(ImageFilter.GaussianBlur(radius=1.0))
    path = os.path.join(out_dir, "standing_curtain_beam.png")
    img.save(path)
    return path


def make_ground_ring_beam(out_dir):
    """512x1024 RGBA vertical seamless triple-track flat ground ring (U=0 outer rim, U=1 inner)."""
    W, H = 512, 1024
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    px = img.load()
    two_pi = 2.0 * math.pi

    for y in range(H):
        v = y / H
        dash_mask = smoothstep(-0.15, 0.25, math.sin(two_pi * (v * 12.0)))
        tick_mask = smoothstep(0.45, 0.78, math.sin(two_pi * (v * 36.0)))
        flow = 0.78 + 0.22 * math.sin(two_pi * (v * 2.0))

        for x in range(W):
            u = x / (W - 1)
            env_u = smoothstep(0.02, 0.09, u) * smoothstep(0.98, 0.90, u)
            if env_u <= 0.001:
                continue
            outer_core = math.exp(-((u - 0.18) / 0.032) ** 2) * 1.00 * flow
            outer_glow = math.exp(-((u - 0.18) / 0.110) ** 2) * 0.45
            mid_dash = math.exp(-((u - 0.48) / 0.042) ** 2) * 0.72 * dash_mask
            inner_line = math.exp(-((u - 0.74) / 0.020) ** 2) * (0.35 + 0.35 * tick_mask)
            wash = math.exp(-((u - 0.45) / 0.30) ** 2) * 0.14
            a = clamp((outer_core + outer_glow + mid_dash + inner_line + wash) * env_u)
            if a > 0.002:
                px[x, y] = (255, 255, 255, int(a * 255))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    path = os.path.join(out_dir, "ground_ring_beam.png")
    img.save(path)
    return path


def make_wisp_particle(out_dir):
    """512x512 RGBA soft curved wind/energy wisp for rising ambient particles."""
    S = 512
    img = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    px = img.load()

    for y in range(S):
        ny = (y / (S - 1)) * 2.0 - 1.0
        for x in range(S):
            nx = (x / (S - 1)) * 2.0 - 1.0
            r = math.hypot(nx, ny)
            if r > 0.96:
                continue
            ang = math.atan2(ny, nx)
            arc_r = 0.58 + 0.06 * math.sin(ang * 2.0)
            radial = math.exp(-((r - arc_r) / 0.12) ** 2)
            ang_mask = smoothstep(2.2, 0.4, abs(ang))

            radial2 = math.exp(-((r - 0.36) / 0.07) ** 2)
            ang2 = abs(((ang - 0.55 + math.pi) % (2.0 * math.pi)) - math.pi)
            ang_mask2 = smoothstep(1.6, 0.3, ang2) * 0.65

            edge = smoothstep(0.96, 0.80, r)
            a = clamp((radial * ang_mask + radial2 * ang_mask2) * edge)
            if a > 0.002:
                px[x, y] = (255, 255, 255, int(a * 255))

    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    path = os.path.join(out_dir, "wisp_particle.png")
    img.save(path)
    return path


def build_preview_sheet(out_dir, paths):
    sheet = Image.new("RGB", (1200, 620), (14, 18, 28))
    dr = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA")
        im.thumbnail((270, 540))
        x = 20 + i * 295
        y = 50 + (540 - im.height) // 2
        bg = Image.new("RGBA", im.size, (18, 24, 38, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (x, y))
        dr.text((x, 16), os.path.basename(p), fill=(220, 235, 255))
    out_path = os.path.join(out_dir, "_preview_sheet.png")
    sheet.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="./aura_textures", help="Output directory")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    paths = [
        make_energy_ribbon_beam(args.out),
        make_standing_curtain_beam(args.out),
        make_ground_ring_beam(args.out),
        make_wisp_particle(args.out),
    ]
    sheet = build_preview_sheet(args.out, paths)
    for p in paths + [sheet]:
        print("Saved:", p)


if __name__ == "__main__":
    main()
