"""Compile reusable procedural motions into ordinary Dataky version-1 tracks.

No procedural code runs in Roblox. Parts use world coordinates; Attachments use
their parent's local coordinates. Times are seconds, angles are degrees, and
Orientation contains unwrapped X/Y/Z Euler angles in Roblox YXZ order.
"""
from __future__ import annotations

from copy import deepcopy
import math

if __package__:
    from .fx_schema import CLASSES, ValidationError, validate_project, validate_value
else:
    from fx_schema import CLASSES, ValidationError, validate_project, validate_value


_COMMON = {"node", "type", "property", "start", "duration", "samples", "easing", "replace"}
_FIELDS = {
    "bezier": {"points"}, "arc": {"from", "to", "height", "axis"},
    "helix": {"center", "radius", "end_radius", "turns", "start_angle", "height", "axis"},
    "orbit": {"center", "radius", "end_radius", "turns", "start_angle", "axis"},
    "oscillation": {"amplitude", "cycles", "phase", "offset", "decay"},
    "spin": {"from", "to", "degrees", "axis"},
    "squash": {"from", "amount", "axis"}, "tween": {"from", "to"},
}
_EASINGS = ("linear", "in", "out", "inOut", "backOut")
_NUMERIC = {"number", "integer", "Vector2", "Vector3", "Color3", "NumberRange"}
_LIMIT = 1_000_000


def _fail(path, message):
    raise ValidationError(path + ": " + message)


def _number(value, path, low=-_LIMIT, high=_LIMIT):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(path, "nombre fini requis")
    if not low <= value <= high:
        _fail(path, f"valeur comprise entre {low} et {high} requise")
    return float(value)


def _vector(value, path, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        _fail(path, f"vecteur de {length} nombres requis")
    return [_number(component, f"{path}[{i}]") for i, component in enumerate(value)]


def _axis(spec, path, default="y"):
    value = spec.get("axis", default)
    if not isinstance(value, str) or value not in ("x", "y", "z"):
        _fail(path + ".axis", "axe x, y ou z requis")
    return "xyz".index(value)


def _ease(name, t):
    if t == 0 or t == 1:
        return t
    if name == "in":
        return t * t * t
    if name == "out":
        return 1 - (1 - t) ** 3
    if name == "inOut":
        return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2
    if name == "backOut":
        return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2
    return t


def _mix(a, b, t):
    if isinstance(a, list):
        return [x + (y - x) * t for x, y in zip(a, b)]
    return a + (b - a) * t


def _checked(value, definition, path):
    """Normalize authoring tuples and enforce native property endpoint bounds."""
    if isinstance(value, (list, tuple)):
        value = _vector(value, path, 2 if definition["type"] in {"Vector2", "NumberRange"} else 3)
    else:
        value = _number(value, path)
    return validate_value(value, definition, path)


def _bounded(value, definition, path):
    """Easing may overshoot; bounded native properties saturate at their bounds."""
    kind = definition["type"]
    low = 0 if kind == "Color3" else definition.get("min", -_LIMIT)
    high = 1 if kind == "Color3" else definition.get("max", _LIMIT)
    def component(v):
        v = min(high, max(low, _number(v, path)))
        return int(round(v)) if kind == "integer" else v
    result = [component(v) for v in value] if isinstance(value, list) else component(value)
    return validate_value(result, definition, path)


def _sampler(kind, spec, base, path):
    if kind == "bezier":
        points = spec.get("points")
        if not isinstance(points, (list, tuple)) or len(points) != 4:
            _fail(path + ".points", "quatre points de contrôle [x,y,z] requis")
        points = [_vector(point, f"{path}.points[{i}]") for i, point in enumerate(points)]
        return lambda t: [sum(weight * point[axis] for weight, point in zip(
            ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3), points)) for axis in range(3)]
    if kind == "arc":
        first = _vector(spec.get("from", base), path + ".from")
        last = _vector(spec.get("to"), path + ".to")
        height = _number(spec.get("height", 2), path + ".height")
        axis = _axis(spec, path)
        return lambda t: [value + (4 * height * t * (1-t) if i == axis else 0)
                          for i, value in enumerate(_mix(first, last, t))]
    if kind in {"helix", "orbit"}:
        center = _vector(spec.get("center", base), path + ".center")
        radius = _number(spec.get("radius", 1), path + ".radius", 0)
        end_radius = _number(spec.get("end_radius", radius), path + ".end_radius", 0)
        turns = _number(spec.get("turns", 1), path + ".turns", -32, 32)
        angle = math.radians(_number(spec.get("start_angle", 0), path + ".start_angle"))
        height = _number(spec.get("height", 3), path + ".height") if kind == "helix" else 0
        axis = _axis(spec, path)
        # Right-handed planes: YZ around X, X(-Z) around Y, XY around Z.
        plane = ((1, 2, 1), (0, 2, -1), (0, 1, 1))[axis]
        def orbit(t):
            theta = angle + math.tau * turns * t
            r = radius + (end_radius - radius) * t
            point = center.copy()
            point[plane[0]] += r * math.cos(theta)
            point[plane[1]] += plane[2] * r * math.sin(theta)
            point[axis] += height * t
            return point
        return orbit
    if kind == "oscillation":
        vector = isinstance(base, list)
        amplitude = (_vector(spec.get("amplitude"), path + ".amplitude", len(base)) if vector
                     else _number(spec.get("amplitude"), path + ".amplitude"))
        offset = (_vector(spec.get("offset", base), path + ".offset", len(base)) if vector
                  else _number(spec.get("offset", base), path + ".offset"))
        cycles = _number(spec.get("cycles", 1), path + ".cycles", 0, 32)
        phase = math.radians(_number(spec.get("phase", 0), path + ".phase"))
        decay = _number(spec.get("decay", 0), path + ".decay", 0, 100)
        def oscillate(t):
            factor = math.sin(math.tau * cycles * t + phase) * math.exp(-decay * max(0, t))
            return [v + a * factor for v, a in zip(offset, amplitude)] if vector else offset + amplitude * factor
        return oscillate
    if kind in {"spin", "tween"}:
        first = spec.get("from", base)
        if kind == "spin":
            first = _vector(first, path + ".from")
            if "to" in spec and ("degrees" in spec or "axis" in spec):
                _fail(path, "spin : utiliser to ou degrees/axis, sans les combiner")
            last = _vector(spec["to"], path + ".to") if "to" in spec else first.copy()
            if "to" not in spec:
                last[_axis(spec, path)] += _number(spec.get("degrees", 360), path + ".degrees")
        else:
            last = spec.get("to")
        return first, last
    # Squash/stretch preserves the product of the three dimensions.
    first = _vector(spec.get("from", base), path + ".from")
    if any(v <= 0 for v in first):
        _fail(path + ".from", "dimensions strictement positives requises")
    amount = _number(spec.get("amount", 1.5), path + ".amount", .05, 20)
    axis = _axis(spec, path)
    def squash(t):
        factor = 1 + (amount - 1) * math.sin(math.pi * min(1, max(0, t)))
        return [v * (factor if i == axis else 1 / math.sqrt(factor)) for i, v in enumerate(first)]
    return squash


def bake_motion(project, specs):
    """Return a validated copy with one motion or an atomic list of 1..128 motions.

    Existing tracks are replaced only with replace=True. A replacement covers the
    entire track, including keys outside this motion's interval. Part/MeshPart
    Position and Transparency tracks opt into the exported gameplay runtime.
    """
    result = validate_project(project)
    specs = [specs] if isinstance(specs, dict) else specs
    if not isinstance(specs, list) or not 1 <= len(specs) <= 128:
        _fail("motions", "un objet ou une liste de 1 à 128 mouvements requis")
    by_id = {node["id"]: node for node in result["nodes"]}
    for index, spec in enumerate(specs):
        path = f"motions[{index}]"
        if not isinstance(spec, dict):
            _fail(path, "objet mouvement requis")
        kind = spec.get("type")
        kind = "helix" if kind == "spiral" else kind
        if not isinstance(kind, str) or kind not in _FIELDS:
            _fail(path + ".type", "type attendu : " + ", ".join((*_FIELDS, "spiral")))
        unknown = set(spec) - (_COMMON | _FIELDS[kind])
        if unknown:
            _fail(path, "champ inconnu : " + ", ".join(sorted(map(str, unknown))))
        node_id = spec.get("node")
        if not isinstance(node_id, str) or node_id not in by_id:
            _fail(path + ".node", "objet introuvable ; fournir un identifiant de node existant")
        node = by_id[node_id]
        default = "Orientation" if kind == "spin" else ("Scale" if node["class"] == "SpecialMesh" else "Size") if kind == "squash" else "Position"
        prop = spec.get("property", default)
        definition = CLASSES[node["class"]]["properties"].get(prop) if isinstance(prop, str) else None
        if not definition or not definition.get("animatable") or definition["type"] not in _NUMERIC:
            _fail(path + ".property", "propriété numérique animable requise sur " + node["class"])
        if kind in {"bezier", "arc", "helix", "orbit"} and prop != "Position":
            _fail(path + ".property", "cette trajectoire anime Position ; utiliser Attachment.Position pour un espace local")
        if kind == "spin" and prop != "Orientation":
            _fail(path + ".property", "spin anime Orientation en degrés X/Y/Z")
        if kind == "squash" and (prop not in {"Size", "Scale"} or definition["type"] != "Vector3"):
            _fail(path + ".property", "squash anime Size ou Scale (Vector3)")
        replace = spec.get("replace", False)
        if not isinstance(replace, bool):
            _fail(path + ".replace", "booléen requis")
        existing = any(t["node"] == node_id and t["property"] == prop for t in result["animations"])
        if existing and not replace:
            _fail(path, f"piste {node_id}.{prop} déjà présente ; replace:true remplace explicitement toute la piste")
        start = _number(spec.get("start", 0), path + ".start", 0, result["duration"])
        duration = _number(spec.get("duration", result["duration"] - start), path + ".duration", 0, result["duration"])
        if duration <= 0 or start + duration > result["duration"] + 1e-9:
            _fail(path + ".duration", "durée > 0 et start + duration <= durée du projet requis")
        end = min(result["duration"], start + duration)
        samples = spec.get("samples", 61)
        if isinstance(samples, bool) or not isinstance(samples, int) or not 2 <= samples <= 241:
            _fail(path + ".samples", "entier entre 2 et 241 requis")
        easing = spec.get("easing", "linear")
        if not isinstance(easing, str) or easing not in _EASINGS:
            _fail(path + ".easing", "courbe attendue : " + ", ".join(_EASINGS))
        base = deepcopy(node["properties"].get(prop, [1, 1, 1] if node["class"] == "MeshPart" and prop == "Size" else definition["default"]))
        if kind == "squash" and "from" in spec:
            _checked(spec["from"], definition, path + ".from")
        if kind == "oscillation" and "offset" in spec:
            _checked(spec["offset"], definition, path + ".offset")
        sampler = _sampler(kind, spec, base, path)
        if kind in {"tween", "spin"}:
            first, last = (_checked(value, definition, path + "." + field) for value, field in zip(sampler, ("from", "to")))
            sampler = lambda t, a=first, b=last: _mix(a, b, t)
        frames = []
        for i in range(samples):
            time = end if i == samples - 1 else start + duration * i / (samples - 1)
            if frames and time <= frames[-1]["time"]:
                _fail(path + ".duration", "intervalle trop court pour produire des instants distincts")
            value = _bounded(sampler(_ease(easing, i / (samples - 1))), definition, f"{path}.keyframes[{i}].value")
            frames.append({"time": time, "value": value})
        track = {"node": node_id, "property": prop, "keyframes": frames}
        if node["class"] in {"Part", "MeshPart"} and prop in {"Position", "Transparency"}:
            track["runtime"] = True
        result["animations"] = [t for t in result["animations"] if not (t["node"] == node_id and t["property"] == prop)]
        result["animations"].append(track)
        # A replaced track must not reopen stale Bezier handles in the editor.
        result.get("editor", {}).get("curves", {}).pop(node_id + "::" + prop, None)
    return validate_project(result)


def motion_schema():
    """Describe the JSON authoring contract; no executable expressions accepted."""
    return {
        "version": 1, "operation": "bake_motion(project, spec_or_list) -> validated recipe copy",
        "common": {
            "node": "Required existing node ID.", "type": "Required type from types below.",
            "property": "Default Position; spin: Orientation; squash: Size or SpecialMesh.Scale. tween requires an explicit useful numeric property.",
            "start": "Seconds >=0, default 0.", "duration": "Seconds >0; default project.duration-start. Must fit within project duration.",
            "samples": "Integer 2..241, default 61. Increase for fast turns; sample count includes both endpoints.",
            "easing": "linear | in | out | inOut | backOut; cubic timing, backOut overshoots.",
            "replace": "Boolean default false. True replaces the complete existing node/property track.",
        },
        "types": {
            "bezier": {"points": "Required four 3D cubic Bezier control points; first/last are endpoints."},
            "arc": {"from": "3D start, default node Position.", "to": "Required 3D end.", "height": "Signed peak displacement on axis at progress .5, default 2.", "axis": "x | y | z; default y."},
            "helix": {"center": "3D axis origin, default node Position.", "radius": "Initial radius >=0, default 1.", "end_radius": "Final radius >=0, default radius.", "turns": "Signed revolutions -32..32, default 1.", "start_angle": "Degrees, default 0.", "height": "Signed axial travel, default 3.", "axis": "x | y | z; default y."},
            "spiral": {"alias": "helix; change end_radius for radial growth/shrinkage."},
            "orbit": {"like": "helix with height=0; height is not an accepted field."},
            "oscillation": {"amplitude": "Required number or vector matching property dimension.", "offset": "Baseline, default node property.", "cycles": "0..32 cycles across duration, default 1.", "phase": "Degrees, default 0.", "decay": "Exponential damping >=0..100, default 0."},
            "spin": {"from": "3D Euler degrees, default Orientation.", "to": "Optional absolute Euler end; excludes axis/degrees.", "degrees": "Signed delta on axis, default 360; angles stay unwrapped.", "axis": "x | y | z; default y."},
            "squash": {"from": "Positive 3D dimensions, default node Size/Scale.", "amount": "Peak factor .05..20, default 1.5; below 1 squashes chosen axis, above 1 stretches it. Transverse dimensions preserve volume.", "axis": "x | y | z; default y."},
            "tween": {"from": "Default current numeric property.", "to": "Required numeric or vector end matching property."},
        },
        "conventions": [
            "Parts/MeshParts use world positions; Attachments use parent-local positions. Folder/Model do not transform descendants.",
            "Angles are degrees. Axis planes are right-handed YZ/X(-Z)/XY for X/Y/Z. At angle zero a Y orbit begins on +X.",
            "All numeric inputs must be finite and within +/-1000000; native property bounds also apply. Generated overshoot saturates at native bounds.",
            "Motion compiles to ordinary keyframes. Parts/MeshParts Position and Transparency receive runtime:true for gameplay export.",
            "Tracks hold first/last values outside their interval. Use separate visibility/timing tracks to stage phases. No automatic visual evaluation is claimed.",
        ],
    }


__all__ = ["bake_motion", "motion_schema"]
