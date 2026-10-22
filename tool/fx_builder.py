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

