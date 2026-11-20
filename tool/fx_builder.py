"""Public helpers for authoring Dataky FX version 1 recipes.

Example::

    from fx_builder import Recipe, NS, CS, NR
    fx = Recipe("Muzzle", 1)
    fx.part("root")
    fx.att("tip", "root", (0, 0, -1))
    fx.em("sparks", "tip", "rbxassetid://123", count=12,
          Lifetime=NR(.2, .4), Size=NS((0, .3), (1, 0)),
          Transparency=NS((0, 0), (1, 1)))
    fx.save("Muzzle.json")

Parts use world positions even when parented to a Model or Folder. Attachments
use local positions. merge() composes YXZ rotations, scales dimensional values,
remaps IDs, attachment references and tracks, and never changes the input recipe.
Included parameters receive the same prefix as nodes to avoid accidental sharing.
Orientation tracks preserve rotations at their keys; Euler interpolation between
composed keys can differ. Use intermediate keys for deliberate full revolutions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
import unicodedata

if __package__:
    from .fx_schema import CLASSES, ValidationError, validate_project
else:
    from fx_schema import CLASSES, ValidationError, validate_project


def NS(*points):
    """Build NumberSequence points (time, value[, envelope])."""
    return [{"time": p[0], "value": p[1], "envelope": p[2] if len(p) > 2 else 0} for p in points]


def CS(*points):
    """Build ColorSequence points (time, normalized RGB)."""
    return [{"time": p[0], "value": list(p[1])} for p in points]


def NR(first, last=None):
    """Build a NumberRange, constant when last is omitted."""
    return [first, first if last is None else last]


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(name + " : nombre fini requis")
    return float(value)


def _vec(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValidationError(name + " : vecteur [x,y,z] requis")
    return [_finite(x, name) for x in value]


def _clean_float(value: float) -> float:
    return 0.0 if abs(value) < 1e-12 else float(value)


def _clean_vec(vec):
    return [_clean_float(v) for v in vec]


def _normalize(vec, fallback=(1.0, 0.0, 0.0)):
    length = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2])
    if length < 1e-9:
        return list(fallback)
    return [_clean_float(v / length) for v in vec]


def _matmul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def _rotate(matrix, value):
    return [sum(matrix[r][c] * value[c] for c in range(3)) for r in range(3)]


def _rotation(orientation):
    x, y, z = map(math.radians, orientation)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    # CFrame.fromOrientation: Ry * Rx * Rz, matching editor/emulator.js.
    return [[cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx],
            [cx * sz, cx * cz, -sx],
            [-sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx]]


def _orientation(matrix):
    x = math.asin(max(-1, min(1, -matrix[1][2])))
    if abs(math.cos(x)) > 1e-8:
        y, z = math.atan2(matrix[0][2], matrix[2][2]), math.atan2(matrix[1][0], matrix[1][1])
    else:
        y, z = math.atan2(-matrix[2][0], matrix[0][0]), 0
    return [math.degrees(v) for v in (x, y, z)]


def _renamed(prefix, name):
    candidate = prefix + name
    if len(candidate) > 80:
        candidate = candidate[:68] + "-" + hashlib.sha256(candidate.encode()).hexdigest()[:10]
    return candidate


def _scaled(value, factor):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value * factor
    if isinstance(value, (tuple, list)):
        return [_scaled(v, factor) for v in value]
    if isinstance(value, dict) and "time" in value and "value" in value:
        result = deepcopy(value)
        result["value"] = _scaled(result["value"], factor)
        if "envelope" in result:
            result["envelope"] *= factor
        return result
    return deepcopy(value)


def _sample(keys, time):
    if time <= keys[0]["time"]:
        return keys[0]["value"]
    for a, b in zip(keys, keys[1:]):
        if time <= b["time"]:
            alpha = (time - a["time"]) / (b["time"] - a["time"])
            return [x + (y - x) * alpha for x, y in zip(a["value"], b["value"])]
    return keys[-1]["value"]


def _position_keys(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not value:
        raise ValidationError("position_keys : liste non vide requise")
    keys = []
    previous = -1.0
    for item in value:
        time, position = (item.get("time"), item.get("value")) if isinstance(item, dict) else item
        time = _finite(time, "position_keys.time")
        if time < 0 or time <= previous:
            raise ValidationError("position_keys : temps positifs croissants requis")
        keys.append({"time": time, "value": _vec(position, "position_keys.value")})
        previous = time
    return keys


DIMENSIONS = {
    "Part": {"Size"}, "MeshPart": {"Size"},
    "Attachment": {"Position"}, "SpecialMesh": {"Offset"},
    "ParticleEmitter": {"Size", "Speed", "ZOffset"},
    "Beam": {"Width0", "Width1", "CurveSize0", "CurveSize1", "TextureLength", "ZOffset"},
    "Trail": {"MinLength", "MaxLength", "TextureLength"},
    "PointLight": {"Range"}, "SpotLight": {"Range"}, "SurfaceLight": {"Range"},
}


def merge_recipes(base, other, prefix, *, position=(0, 0, 0), at=0, orientation=(0, 0, 0),
                  scale=1, position_keys=None):
    """Copy a piece into base, composing space and time without mutating either.

    position_keys is an optional translation path relative to position, expressed
    in piece-local seconds as [{time, value:[x,y,z]}] or (time, vector) pairs.
    It combines with existing Part Position tracks. Attachment motion stays local.
    Dimensional properties scale; colors, lifetimes, counts, Rate and Squash do not.
    SpecialMesh.Scale and Trail.WidthScale remain relative to their scaled parent.
    """
    result = validate_project(base.d if isinstance(base, Recipe) else base)
    source = validate_project(other.d if isinstance(other, Recipe) else other)
    if not isinstance(prefix, str):
        raise ValidationError("prefix : texte requis")
    position, orientation = _vec(position, "position"), _vec(orientation, "orientation")
    at, factor = _finite(at, "at"), _finite(scale, "scale")
    if at < 0 or factor <= 0:
        raise ValidationError("at >= 0 et scale > 0 requis")
    motion = _position_keys(position_keys)
    rotation = _rotation(orientation)
    node_ids = {node["id"]: _renamed(prefix, node["id"]) for node in source["nodes"]}
    if len(set(node_ids.values())) != len(node_ids) or set(node_ids.values()) & {n["id"] for n in result["nodes"]}:
        raise ValidationError("prefix : collision d'identifiants")
    param_ids = {name: _renamed(prefix, name) for name in source.get("params", {})}
    if set(param_ids.values()) & set(result.get("params", {})):
        raise ValidationError("prefix : collision de paramètres")
    if param_ids:
        result.setdefault("params", {}).update({param_ids[k]: deepcopy(v) for k, v in source["params"].items()})

    def transform(cls, prop, value, time=0):
        if cls in {"Part", "MeshPart"} and prop == "Position":
            offset = _sample(motion, time) if motion else [0, 0, 0]
            rotated = _rotate(rotation, _scaled(value, factor))
            return [position[i] + offset[i] + rotated[i] for i in range(3)]
        if cls in {"Part", "MeshPart"} and prop == "Orientation":
            if not any(orientation):
                return deepcopy(value)
            return _orientation(_matmul(rotation, _rotation(value)))
        if cls == "ParticleEmitter" and prop == "Acceleration":
            return _rotate(rotation, _scaled(value, factor))
        return _scaled(value, factor) if prop in DIMENSIONS.get(cls, set()) else deepcopy(value)

    source_by_id = {node["id"]: node for node in source["nodes"]}
    for node in source["nodes"]:
        clone = deepcopy(node)
        cls, props = clone["class"], clone["properties"]
        clone["id"] = node_ids[node["id"]]
        clone["parent"] = node_ids.get(node.get("parent"))
        for key, value in list(props.items()):
            if cls == "Beam" and key == "TextureLength" and props.get("TextureMode") == "Stretch":
                props[key] = deepcopy(value)
            else:
                props[key] = node_ids.get(value, value) if CLASSES[cls]["properties"][key]["type"] == "reference" else transform(cls, key, value)
        # Explicitly materialize transformed native defaults when the scale changes.
        if factor != 1:
            for key in DIMENSIONS.get(cls, set()) - props.keys():
                default = CLASSES[cls]["properties"][key]["default"]
                if cls == "MeshPart" and key == "Size":
                    default = [1, 1, 1]
                props[key] = transform(cls, key, default)
        if cls in {"Part", "MeshPart"}:
            for key in ("Position", "Orientation"):
                if key not in props:
                    props[key] = transform(cls, key, [0, 0, 0])
        if cls == "ParticleEmitter" and "Acceleration" not in props and (factor != 1 or any(orientation)):
            props["Acceleration"] = [0, 0, 0]
        if "scaleWith" in clone:
            clone["scaleWith"] = {key: param_ids[value] for key, value in clone["scaleWith"].items()}
        if "timing" in clone:
            clone["timing"]["start"] += at
        result["nodes"].append(clone)

    position_tracks = set()
    for track in source["animations"]:
        cls = source_by_id[track["node"]]["class"]
        clone = {"node": node_ids[track["node"]], "property": track["property"], "keyframes": []}
        if "runtime" in track:
            clone["runtime"] = track["runtime"]
        if cls in {"Part", "MeshPart"} and track["property"] == "Position" and motion:
            position_tracks.add(track["node"])
            times = sorted({k["time"] for k in track["keyframes"]} | {k["time"] for k in motion})
            clone["keyframes"] = [{"time": t + at, "value": transform(cls, "Position", _sample(track["keyframes"], t), t)} for t in times]
        else:
            clone["keyframes"] = [{"time": key["time"] + at,
                                   "value": transform(cls, track["property"], key["value"], key["time"])}
                                  for key in track["keyframes"]]
        if cls in {"Part", "MeshPart"} and track["property"] == "Orientation" and any(orientation):
            for previous, current in zip(clone["keyframes"], clone["keyframes"][1:]):
                current["value"] = [angle + 360 * round((prior - angle) / 360)
                                    for angle, prior in zip(current["value"], previous["value"])]
        result["animations"].append(clone)
    if motion:
        for node in source["nodes"]:
            if node["class"] in {"Part", "MeshPart"} and node["id"] not in position_tracks:
                position_value = node["properties"].get("Position", [0, 0, 0])
                result["animations"].append({"node": node_ids[node["id"]], "property": "Position",
                    "keyframes": [{"time": k["time"] + at, "value": transform(node["class"], "Position", position_value, k["time"])} for k in motion]})
    source_end = max(source["duration"], motion[-1]["time"] if motion else 0)
    result["duration"] = max(result["duration"], at + source_end)
    # Local geometry follows the copied node IDs. Keeping this authoring data
    # also preserves the native-export requirement for an explicit MeshId.
    # Vertices are normalized; the native Size tracks above carry scene scale.
    if source.get("editor", {}).get("meshes"):
        meshes = result.setdefault("editor", {"version": 1, "curves": {}}).setdefault("meshes", {})
        for source_id, geometry in source["editor"]["meshes"].items():
            meshes[node_ids[source_id]] = deepcopy(geometry)
    if source.get("local_textures"):
        result.setdefault("local_textures", {}).update(deepcopy(source["local_textures"]))
    return validate_project(result)


def load_recipe(source):
    """Resolve a JSON path, project ID, file stem or unique short recipe name."""
    if isinstance(source, (Recipe, dict)):
        return validate_project(source.d if isinstance(source, Recipe) else source)
    if not isinstance(source, (str, Path)):
        raise ValidationError("include : chemin ou nom de recette requis")
    path = Path(source)
    if path.is_file():
        return validate_project(json.loads(path.read_text(encoding="utf-8-sig")))
    if __package__:
        from . import fx_tools
    else:
        import fx_tools
    candidates = []
    needle = str(source).casefold()
    for path in fx_tools.PROJECTS.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            names = {path.stem, path.name, data.get("id", ""), data.get("name", "")}
            names.add(data.get("name", "").split("·")[-1].strip())
            if needle in {str(name).casefold() for name in names}:
                candidates.append(data)
        except (OSError, ValueError):
            continue
    if len(candidates) == 1:
        return validate_project(candidates[0])
    raise ValidationError("include : recette " + str(source) + (" ambiguë" if candidates else " introuvable"))


class Recipe:
    """Mutable authoring helper; .d is an ordinary portable version 1 recipe."""
    def __init__(self, name, duration=3, camera=None, *, ident=None, background="#191522", loop=False):
        slug = re.sub(r"[^a-z0-9_.-]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-") or "effect"
        self.short = name
        self.d = {"version": 1, "name": name, "id": ident or slug[:80], "duration": duration, "loop": loop,
                  "nodes": [], "animations": [], "camera": deepcopy(camera or {"position": [16, 9, 18], "target": [0, 3, 0]}),
                  "environment": {"background": background}}

    def _add(self, node):
        if any(n["id"] == node["id"] for n in self.d["nodes"]):
            raise ValidationError("identifiant déjà utilisé : " + node["id"])
        self.d["nodes"].append(deepcopy(node))
        return node["id"]

    def part(self, id, pos=(0, 0, 0), size=(1, 1, 1), name=None, parent=None, **props):
        properties = {"Position": list(pos), "Size": list(size), "Transparency": 1, "Anchored": True,
                      "CanCollide": False, "CanTouch": False, "CanQuery": False, "CastShadow": False}
        properties.update(props)
        return self._add({"id": id, "class": "Part", "name": name or id, "parent": parent, "properties": properties})

    def att(self, id, parent, pos=(0, 0, 0), ori=None, name=None, **props):
        properties = {"Position": list(pos), **props}
        if ori is not None:
            properties["Orientation"] = list(ori)
        return self._add({"id": id, "class": "Attachment", "name": name or id, "parent": parent, "properties": properties})

    def em(self, id, parent, tex, start=0.0, mode="burst", count=1, dur=0.05, name=None, scaleWith=None, **props):
        properties = {"Texture": tex, "Rate": 30 if mode == "continuous" else 0, "LightInfluence": 0,
                      "LightEmission": 0, "Brightness": 1, "Speed": NR(0), "SpreadAngle": [0, 0], "Lifetime": NR(.5), **props}
        node = {"id": id, "class": "ParticleEmitter", "name": name or id, "parent": parent, "properties": properties,
                "timing": {"start": start, "duration": dur, "mode": mode, "count": count}}
        if scaleWith is not None:
            node["scaleWith"] = deepcopy(scaleWith)
        return self._add(node)

    def flip(self, grid=4, mode="OneShot"):
        if grid in (2, 4, 8):
            return {"FlipbookLayout": "Grid%dx%d" % (grid, grid), "FlipbookMode": mode}
        if isinstance(grid, (tuple, list)) and len(grid) == 2:
            return {"FlipbookLayout": "Custom", "FlipbookSizeX": grid[0], "FlipbookSizeY": grid[1], "FlipbookMode": mode}
        raise ValidationError("flip : grille 2, 4, 8 ou (colonnes, lignes) requise")

    def trail(self, id, parent, a0, a1, tex="", **props):
        properties = {"Attachment0": a0, "Attachment1": a1, "Texture": tex, "LightInfluence": 0, "LightEmission": 0, "FaceCamera": True, **props}
        timing = properties.pop("_timing", None)
        node = {"id": id, "class": "Trail", "name": id, "parent": parent, "properties": properties}
        if timing is not None:
            node["timing"] = timing
        return self._add(node)

    def beam(self, bid, parent, a0, a1, **props):
        """Add a Beam node linking attachments a0 and a1."""
        name = props.pop("name", None)
        timing = props.pop("_timing", None)
        if "timing" in props:
            timing = props.pop("timing")
        properties = {"Attachment0": a0, "Attachment1": a1, "LightInfluence": 0, "Enabled": True, **props}
        node = {"id": bid, "class": "Beam", "name": name or bid, "parent": parent, "properties": properties}
        if timing is not None:
            node["timing"] = deepcopy(timing)
        return self._add(node)

    def circle_beam(self, prefix, parent, radius, y, width, color_seq, trans_seq, tex, *,
                    segments=4, beam_segments=28, light_emission=0.85, brightness=2.2,
                    tex_len=1, tex_speed=0.5, z_offset=0.05, face_camera=False,
                    standing=False, tex_mode="Stretch", start=0.0, dur=None, **extra):
        """Create a closed, seamless circular Beam ring using exact cubic Bezier handles.

        Defaults to TextureMode='Stretch' with integer TextureLength=1 per arc so UV V
        lands on an exact integer at every attachment joint (zero visible seam).
        When face_camera=False:
          - standing=False (default): flat horizontal ring (SecondaryAxis=radialOut, Z=+up).
          - standing=True: standing vertical curtain (SecondaryAxis=-up, Z=radialOut; U=0 bottom, U=1 top).
        """
        radius = _finite(radius, "radius")
        y = _finite(y, "y")
        width = _finite(width, "width")
        if radius <= 0:
            raise ValidationError("circle_beam : radius > 0 requis")
        if not isinstance(segments, int) or segments < 3:
            raise ValidationError("circle_beam : segments >= 3 requis")
        dtheta = 2.0 * math.pi / segments
        handle = (4.0 / 3.0) * radius * math.tan(dtheta / 4.0)
        timing = extra.pop("timing", None)
        if timing is None:
            span = self.d["duration"] - start if dur is None else dur
            timing = {"start": start, "duration": span, "mode": "continuous", "count": 1}
        att_ids = []
        for i in range(segments):
            theta = i * dtheta
            c, s = math.cos(theta), math.sin(theta)
            pos = _clean_vec((radius * c, y, radius * s))
            axis = _clean_vec((-s, 0.0, c))
            sec = [0.0, -1.0, 0.0] if standing else _clean_vec((c, 0.0, s))
            att_ids.append(self.att(f"{prefix}_p{i}", parent, pos, Axis=axis, SecondaryAxis=sec))
        beam_ids = []
        for i in range(segments):
            a0, a1 = att_ids[i], att_ids[(i + 1) % segments]
            beam_ids.append(self.beam(
                f"{prefix}_b{i}", parent, a0, a1,
                Texture=tex, TextureMode=tex_mode, TextureLength=tex_len, TextureSpeed=tex_speed,
                Width0=width, Width1=width, CurveSize0=handle, CurveSize1=handle,
                Segments=beam_segments, FaceCamera=face_camera,
                Color=deepcopy(color_seq), Transparency=deepcopy(trans_seq),
                LightEmission=light_emission, Brightness=brightness, ZOffset=z_offset,
                timing=timing, **extra,
            ))
        return beam_ids

    def spline_ribbon(self, prefix, parent, points, widths, color_seq, trans_seq, tex, *,
                      closed=False, tension=0.34, beam_segments=16, light_emission=0.72,
                      brightness=2.0, tex_len=1, tex_speed=0.85, face_camera=True,
                      z_offset=0.0, tilt_vec=(0, 1, 0), tex_mode="Stretch",
                      slice_sequences=True, start=0.0, dur=None, **extra):
        """Build a smooth, seamless multi-segment Beam ribbon along 3D spline control points.

        Defaults to TextureMode='Stretch' with integer TextureLength=1 per segment (zero UV seam)
        and slices trans_seq/color_seq continuously across the full ribbon length (slice_sequences=True)
        so fade-in/fade-out endpoints never create transparent gaps between interior segments.
        """
        def _eval_num_seq(seq, t):
            if not isinstance(seq, list) or not seq:
                return 0.0
            if t <= seq[0]["time"]:
                return float(seq[0]["value"])
            if t >= seq[-1]["time"]:
                return float(seq[-1]["value"])
            for a, b in zip(seq, seq[1:]):
                if t <= b["time"]:
                    span = max(b["time"] - a["time"], 1e-9)
                    f = (t - a["time"]) / span
                    return float(a["value"]) + (float(b["value"]) - float(a["value"])) * f
            return float(seq[-1]["value"])

        def _slice_num_seq(seq, u0, u1):
            if not slice_sequences or not isinstance(seq, list) or len(seq) < 2:
                return deepcopy(seq)
            span = max(u1 - u0, 1e-9)
            pts_t = [u0] + [k["time"] for k in seq if u0 < k["time"] < u1] + [u1]
            out = []
            for gt in pts_t:
                lt = round(max(0.0, min(1.0, (gt - u0) / span)), 4)
                val = round(_eval_num_seq(seq, gt), 4)
                if not out or abs(out[-1]["time"] - lt) > 1e-5:
                    out.append({"time": lt, "value": val, "envelope": 0})
            if len(out) == 1:
                out.append({"time": 1.0, "value": out[0]["value"], "envelope": 0})
            out[0]["time"] = 0.0
            out[-1]["time"] = 1.0
            return out

        def _eval_col_seq(seq, t):
            if not isinstance(seq, list) or not seq:
                return [1.0, 1.0, 1.0]
            if t <= seq[0]["time"]:
                return list(seq[0]["value"])
            if t >= seq[-1]["time"]:
                return list(seq[-1]["value"])
            for a, b in zip(seq, seq[1:]):
                if t <= b["time"]:
                    span = max(b["time"] - a["time"], 1e-9)
                    f = (t - a["time"]) / span
                    return [a["value"][c] + (b["value"][c] - a["value"][c]) * f for c in range(3)]
            return list(seq[-1]["value"])

        def _slice_col_seq(seq, u0, u1):
            if not slice_sequences or not isinstance(seq, list) or len(seq) < 2:
                return deepcopy(seq)
            span = max(u1 - u0, 1e-9)
            pts_t = [u0] + [k["time"] for k in seq if u0 < k["time"] < u1] + [u1]
            out = []
            for gt in pts_t:
                lt = round(max(0.0, min(1.0, (gt - u0) / span)), 4)
                val = [round(c, 4) for c in _eval_col_seq(seq, gt)]
                if not out or abs(out[-1]["time"] - lt) > 1e-5:
                    out.append({"time": lt, "value": val})
            if len(out) == 1:
                out.append({"time": 1.0, "value": list(out[0]["value"])})
            out[0]["time"] = 0.0
            out[-1]["time"] = 1.0
            return out

        pts = [_vec(pt, "points") for pt in points]
        n = len(pts)
        if n < (3 if closed else 2):
            raise ValidationError("spline_ribbon : au moins " + ("3" if closed else "2") + " points requis")
        if isinstance(widths, (int, float)) and not isinstance(widths, bool):
            w_list = [_finite(widths, "widths")] * n
        else:
            w_list = [_finite(w, "widths") for w in widths]
            if len(w_list) != n:
                raise ValidationError("spline_ribbon : widths doit avoir la même longueur que points")
        tilt = _vec(tilt_vec, "tilt_vec")
        tension = _finite(tension, "tension")
        timing = extra.pop("timing", None)
        if timing is None:
            span = self.d["duration"] - start if dur is None else dur
            timing = {"start": start, "duration": span, "mode": "continuous", "count": 1}
        att_ids = []
        for i in range(n):
            if closed:
                prev_p, next_p = pts[(i - 1) % n], pts[(i + 1) % n]
            elif i == 0:
                prev_p, next_p = pts[0], pts[1]
            elif i == n - 1:
                prev_p, next_p = pts[n - 2], pts[n - 1]
            else:
                prev_p, next_p = pts[i - 1], pts[i + 1]
            tan = _normalize([next_p[k] - prev_p[k] for k in range(3)], (1.0, 0.0, 0.0))
            proj = tan[0] * tilt[0] + tan[1] * tilt[1] + tan[2] * tilt[2]
            sec_raw = [tilt[k] - proj * tan[k] for k in range(3)]
            if math.sqrt(sum(v * v for v in sec_raw)) < 1e-6:
                alt = (1.0, 0.0, 0.0) if abs(tan[0]) < 0.9 else (0.0, 0.0, 1.0)
                proj = tan[0] * alt[0] + tan[1] * alt[1] + tan[2] * alt[2]
                sec_raw = [alt[k] - proj * tan[k] for k in range(3)]
            sec = _normalize(sec_raw, (0.0, 1.0, 0.0))
            att_ids.append(self.att(f"{prefix}_p{i}", parent, _clean_vec(pts[i]), Axis=tan, SecondaryAxis=sec))
        seg_count = n if closed else n - 1
        beam_ids = []
        for i in range(seg_count):
            j = (i + 1) % n
            dist = math.sqrt(sum((pts[j][k] - pts[i][k]) ** 2 for k in range(3)))
            curve = dist * tension
            u0, u1 = i / seg_count, (i + 1) / seg_count
            beam_ids.append(self.beam(
                f"{prefix}_b{i}", parent, att_ids[i], att_ids[j],
                Texture=tex, TextureMode=tex_mode, TextureLength=tex_len, TextureSpeed=tex_speed,
                Width0=w_list[i], Width1=w_list[j], CurveSize0=curve, CurveSize1=curve,
                Segments=beam_segments, FaceCamera=face_camera,
                Color=_slice_col_seq(color_seq, u0, u1),
                Transparency=_slice_num_seq(trans_seq, u0, u1),
                LightEmission=light_emission, Brightness=brightness, ZOffset=z_offset,
                timing=timing, **extra,
            ))
        return beam_ids

    def helix_ribbon(self, prefix, parent, *, radius_start, radius_end, y_start, y_end,
                     turns=1.5, start_angle=0.0, steps=14, width_min=0.2, width_max=1.0,
                     color_seq, trans_seq, tex, tension=0.34, beam_segments=14,
                     light_emission=0.72, brightness=2.0, tex_len=1, tex_speed=0.85,
                     face_camera=True, z_offset=0.0, tilt_vec=(0, 1, 0),
                     tex_mode="Stretch", slice_sequences=True, start=0.0, dur=None, **extra):
        """Build a rising/tapering helical Beam ribbon (wind updrafts, auras, spirals)."""
        radius_start = _finite(radius_start, "radius_start")
        radius_end = _finite(radius_end, "radius_end")
        y_start = _finite(y_start, "y_start")
        y_end = _finite(y_end, "y_end")
        turns = _finite(turns, "turns")
        start_angle = _finite(start_angle, "start_angle")
        width_min = _finite(width_min, "width_min")
        width_max = _finite(width_max, "width_max")
        if not isinstance(steps, int) or steps < 2:
            raise ValidationError("helix_ribbon : steps >= 2 requis")
        pts, widths = [], []
        for i in range(steps + 1):
            u = i / steps
            angle = start_angle + turns * 2.0 * math.pi * u
            r = radius_start + (radius_end - radius_start) * u
            y = y_start + (y_end - y_start) * u
            pts.append((r * math.cos(angle), y, r * math.sin(angle)))
            widths.append(width_min + (width_max - width_min) * math.sin(math.pi * u))
        return self.spline_ribbon(
            prefix, parent, pts, widths, color_seq, trans_seq, tex,
            closed=False, tension=tension, beam_segments=beam_segments,
            light_emission=light_emission, brightness=brightness,
            tex_len=tex_len, tex_speed=tex_speed, face_camera=face_camera,
            z_offset=z_offset, tilt_vec=tilt_vec, tex_mode=tex_mode,
            slice_sequences=slice_sequences, start=start, dur=dur, **extra,
        )

    def light(self, id, parent, start, dur, color, rng, peak, name=None, fall=None):
        ident = self._add({"id": id, "class": "PointLight", "name": name or id, "parent": parent,
                          "properties": {"Brightness": peak, "Range": rng, "Color": list(color)},
                          "timing": {"start": start, "duration": dur, "mode": "continuous", "count": 1}})
        self.anim(id, "Brightness", [(start, peak), (start + (dur if fall is None else fall), 0)])
        return ident

    def anim(self, node, prop, keys):
        self.d["animations"].append({"node": node, "property": prop, "keyframes":
            [{"time": t, "value": deepcopy(list(value) if isinstance(value, tuple) else value)} for t, value in keys]})
        return self

    def merge(self, other, prefix, offset=(0, 0, 0), dt=0.0, *, orientation=(0, 0, 0), scale=1, position_keys=None):
        self.d = merge_recipes(self.d, other, prefix, position=offset, at=dt, orientation=orientation, scale=scale, position_keys=position_keys)
        return self

    def to_dict(self):
        return validate_project(self.d)

    def save(self, path=None):
        """Validate and write a JSON file, creating its parent directory."""
        target = Path(path) if path is not None else Path(self.d["id"] + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target


__all__ = ["Recipe", "NS", "CS", "NR", "merge_recipes", "load_recipe"]

