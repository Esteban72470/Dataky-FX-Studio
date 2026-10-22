"""Derived alpha statistics for local PNG thumbnails; never edits the catalogue.

python tool/fx_texture_cache.py [asset IDs...] --out tool/texture_frames.json
The standard-library PNG reader supports non-interlaced grayscale/RGB/palette
images (1/2/4/8/16-bit samples). Unsupported thumbnails are reported, not guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).with_name("texture_frames.json")


def png_pixels(data: bytes):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("image PNG requise")
    pos, compressed, palette, transparent = 8, bytearray(), None, b""
    header = None
    while pos + 12 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        payload = data[pos + 8:pos + 8 + length]
        if len(payload) != length:
            raise ValueError("PNG tronqué")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"PLTE":
            palette = [tuple(payload[i:i + 3]) for i in range(0, len(payload), 3)]
        elif kind == b"tRNS":
            transparent = payload
        pos += length + 12
        if kind == b"IEND":
            break
    if header is None:
        raise ValueError("IHDR absent")
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if not channels or compression or filtering or interlace or depth not in (1, 2, 4, 8, 16):
        raise ValueError("format PNG non pris en charge (entrelacement ou profondeur)")
    if depth < 8 and color not in (0, 3) or color == 3 and depth == 16:
        raise ValueError("profondeur PNG incompatible")
    if not width or not height or width * height > 16_000_000:
        raise ValueError("dimensions PNG invalides")
    stride, bpp = (width * channels * depth + 7) // 8, max(1, (channels * depth + 7) // 8)
    raw = zlib.decompress(compressed)
    if len(raw) != (stride + 1) * height:
        raise ValueError("taille des lignes PNG invalide")
    pixels, previous = [], bytearray(stride)
    maximum = (1 << depth) - 1
    for y in range(height):
        start = y * (stride + 1)
        filter_type, row = raw[start], bytearray(raw[start + 1:start + stride + 1])
        for i in range(stride):
            left = row[i - bpp] if i >= bpp else 0
            up, corner = previous[i], previous[i - bpp] if i >= bpp else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                p = left + up - corner
                a, b, c = abs(p - left), abs(p - up), abs(p - corner)
                predictor = left if a <= b and a <= c else up if b <= c else corner
            elif filter_type == 0:
                predictor = 0
            else:
                raise ValueError("filtre PNG inconnu")
            row[i] = (row[i] + predictor) & 255
        if depth == 8:
            samples = list(row)
        elif depth == 16:
            samples = list(struct.unpack(">" + "H" * (len(row) // 2), row))
        else:
            samples = [(row[(i * depth) // 8] >> (8 - depth - (i * depth) % 8)) & maximum for i in range(width)]
        for x in range(width):
            values = samples[x * channels:(x + 1) * channels]
            convert = lambda v: v * 255 // maximum
            if color == 3:
                index = values[0]
                if palette is None or index >= len(palette):
                    raise ValueError("palette PNG invalide")
                r, g, b = palette[index]
                a = transparent[index] if index < len(transparent) else 255
            elif color in (0, 4):
                r = g = b = convert(values[0])
                a = convert(values[1]) if color == 4 else (0 if len(transparent) == 2 and values[0] == struct.unpack(">H", transparent)[0] else 255)
            else:
                r, g, b = map(convert, values[:3])
                a = convert(values[3]) if color == 6 else (0 if len(transparent) == 6 and tuple(values) == struct.unpack(">HHH", transparent) else 255)
            pixels.append((r, g, b, a))
        previous = row
    return width, height, pixels


def frame_statistics(data: bytes, columns: int = 1, rows: int | None = None):
    rows = columns if rows is None else rows
    if not isinstance(columns, int) or not isinstance(rows, int) or not 1 <= columns <= 32 or not 1 <= rows <= 32:
        raise ValueError("grille de 1 à 32 cases par axe requise")
    width, height, pixels = png_pixels(data)
    if columns > width or rows > height:
        raise ValueError("grille plus grande que l’image")
    frames = []
    for row in range(rows):
        for col in range(columns):
            samples = [pixels[y * width + x] for y in range(row * height // rows, (row + 1) * height // rows)
                       for x in range(col * width // columns, (col + 1) * width // columns)]
            count = len(samples)
            frames.append({"alpha_mean": sum(p[3] for p in samples) / (255 * count),
                           "coverage": sum(p[3] >= 16 for p in samples) / count,
                           "luma_alpha_mean": sum((.2126 * p[0] + .7152 * p[1] + .0722 * p[2]) * p[3] for p in samples) / (255 * 255 * count)})
    return {"width": width, "height": height, "columns": columns, "rows": rows, "frames": frames}


def _valid_cached_entry(entry, digest, columns, rows):
    """A corrupted derived cache is a miss, never authoritative image data."""
    if not isinstance(entry, dict) or entry.get("sha256") != digest:
        return False
    if entry.get("columns") != columns or entry.get("rows") != rows:
        return False
    for name, minimum in (("width", columns), ("height", rows)):
        dimension = entry.get(name)
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < minimum:
            return False
    frames = entry.get("frames")
    if not isinstance(frames, list) or len(frames) != columns * rows:
        return False
    for frame in frames:
        if not isinstance(frame, dict):
            return False
        for name in ("alpha_mean", "coverage", "luma_alpha_mean"):
            value = frame.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                return False
    return True


def texture_stats(asset_id: str, columns=1, rows=None, *, root=ROOT, cache_path=CACHE):
    if not str(asset_id).isdigit():
        return None
    path = Path(root) / "images" / (str(asset_id) + ".png")
    if not path.is_file():
        return None
    rows = columns if rows is None else rows
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    cache_path = Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict) or cache.get("version") != 1 or not isinstance(cache.get("items"), dict):
            cache = {"version": 1, "items": {}}
    except (OSError, ValueError):
        cache = {"version": 1, "items": {}}
    key = f"{asset_id}:{columns}x{rows}"
    entry = cache["items"].get(key)
    if _valid_cached_entry(entry, digest, columns, rows):
        return entry
    entry = {**frame_statistics(data, columns, rows), "sha256": digest}
    cache["items"][key] = entry
    # Cache write failures must never make an otherwise valid recipe invalid.
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--out", type=Path, default=CACHE)
    args = parser.parse_args()
    catalog = json.loads((ROOT / "textures.json").read_text(encoding="utf-8"))
    wanted = set(args.ids)
    count, errors = 0, []
    for item in catalog:
        asset_id = str(item.get("asset_id"))
        if wanted and asset_id not in wanted:
            continue
        grid = int(item.get("grid") or 1) if item.get("kind") == "flipbook" else 1
        try:
            count += texture_stats(asset_id, grid, root=ROOT, cache_path=args.out) is not None
        except (OSError, ValueError, zlib.error, struct.error) as error:
            errors.append({"id": asset_id, "error": str(error)})
    print(json.dumps({"cache": str(args.out), "analyzed": count, "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
