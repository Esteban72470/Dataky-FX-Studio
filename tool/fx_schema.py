"""Versioned, explicit Roblox VFX recipe schema. No code is accepted in projects.

Only public, editable properties represented by the JSON codecs are exposed.
Native-only Content objects, hidden properties, and read-only diagnostics are
deliberately absent: unknown properties raise errors rather than disappear.
Official references: https://create.roblox.com/docs/reference/engine/classes/
ParticleEmitter, Beam, Trail (consulted 2026-10-21).
"""
from copy import deepcopy
import json
import math
import re


class ValidationError(ValueError):
    pass


def p(kind, default, **kwargs):
    return {"type": kind, "default": default, **kwargs}


def enum(default, values, enum_type):
    return p("enum", default, enum=values.split(), enumType=enum_type)


def sequence(value, **kwargs):
    return p("NumberSequence", [{"time": 0, "value": value, "envelope": 0}, {"time": 1, "value": value, "envelope": 0}], **kwargs)


COLOR = p("ColorSequence", [{"time": 0, "value": [1, 1, 1]}, {"time": 1, "value": [1, 1, 1]}])
NORMAL = "Right Top Back Left Bottom Front"
MATERIALS = ("Plastic SmoothPlastic Neon Wood WoodPlanks Marble Slate Concrete Granite Brick Pebble "
             "Cobblestone Rock Sandstone Basalt CrackedLava Limestone Pavement CorrodedMetal DiamondPlate "
             "Foil Metal Grass LeafyGrass Sand Fabric Snow Mud Ground Asphalt Salt Ice Glacier Glass "
             "ForceField Air Water Cardboard Carpet CeramicTiles ClayRoofTiles RoofShingles Leather Plaster Rubber")
BASE_PART = {
    "Position": p("Vector3", [0, 0, 0]), "Orientation": p("Vector3", [0, 0, 0]),
    "Size": p("Vector3", [4, 1, 2], min=0.001, max=2048),
    "Anchored": p("boolean", True), "CanCollide": p("boolean", False),
    "CanTouch": p("boolean", False), "CanQuery": p("boolean", False),
    "CastShadow": p("boolean", False), "Massless": p("boolean", True),
    "Color": p("Color3", [1, 1, 1]), "Transparency": p("number", 1, min=0, max=1),
    "Reflectance": p("number", 0, min=0, max=1),
    "Material": enum("SmoothPlastic", MATERIALS, "Material"),
    "MaterialVariant": p("string", ""),
}
LIGHT = {
    "Brightness": p("number", 1, min=0), "Color": p("Color3", [1, 1, 1]),
    "Enabled": p("boolean", True), "Shadows": p("boolean", False),
    "Range": p("number", 8, min=0, max=60),
}

CLASSES = {
    "Folder": {"properties": {}},
    "Model": {"properties": {}},
    "Part": {"properties": {
        **deepcopy(BASE_PART), "Shape": enum("Block", "Ball Block Cylinder", "PartType"),
        "TopSurface": enum("Smooth", "Smooth Glue Weld Studs Inlet Universal Hinge Motor SteppingMotor SmoothNoOutlines", "SurfaceType"),
        "BottomSurface": enum("Smooth", "Smooth Glue Weld Studs Inlet Universal Hinge Motor SteppingMotor SmoothNoOutlines", "SurfaceType"),
    }},
    "MeshPart": {"properties": {
        **deepcopy(BASE_PART), "MeshId": p("content", ""), "TextureID": p("content", ""),
        "DoubleSided": p("boolean", False),
        "RenderFidelity": enum("Automatic", "Automatic Precise Performance", "RenderFidelity"),
    }},
    "Attachment": {"properties": {
        "Position": p("Vector3", [0, 0, 0]), "Orientation": p("Vector3", [0, 0, 0]),
        "Axis": p("Vector3", [1, 0, 0], advanced=True, omitOnCreate=True),
        "SecondaryAxis": p("Vector3", [0, 1, 0], advanced=True, omitOnCreate=True),
        "Visible": p("boolean", False),
    }},
    "ParticleEmitter": {"properties": {
        "Acceleration": p("Vector3", [0, 0, 0]), "Brightness": p("number", 1, min=0),
        "Color": deepcopy(COLOR), "Drag": p("number", 0, min=0),
        "EmissionDirection": enum("Top", NORMAL, "NormalId"), "Enabled": p("boolean", True),
        "FlipbookBlendFrames": p("boolean", True),
        "FlipbookFramerate": p("NumberRange", [1, 1], min=0),
        "FlipbookLayout": enum("None", "None Grid2x2 Grid4x4 Grid8x8 Custom", "ParticleFlipbookLayout"),
        "FlipbookMode": enum("Loop", "Loop OneShot PingPong Random", "ParticleFlipbookMode"),
        "FlipbookSizeX": p("integer", 1, min=1, max=64),
        "FlipbookSizeY": p("integer", 1, min=1, max=64),
        "FlipbookStartRandom": p("boolean", False),
        "Lifetime": p("NumberRange", [5, 10], min=0, max=1000),
        "LightEmission": p("number", 0, min=0, max=1),
        "LightInfluence": p("number", 0, min=0, max=1), "LockedToPart": p("boolean", False),
        "Orientation": enum("FacingCamera", "FacingCamera FacingCameraWorldUp VelocityParallel VelocityPerpendicular", "ParticleOrientation"),
        "Rate": p("number", 20, min=0, max=10000),
        "Rotation": p("NumberRange", [0, 0]), "RotSpeed": p("NumberRange", [0, 0]),
        "Shape": enum("Box", "Box Sphere Cylinder Disc", "ParticleEmitterShape"),
        "ShapeInOut": enum("Outward", "Outward Inward InAndOut", "ParticleEmitterShapeInOut"),
        "ShapePartial": p("number", 1, min=0, max=1),
        "ShapeStyle": enum("Volume", "Volume Surface", "ParticleEmitterShapeStyle"),
        "Size": sequence(1, min=0), "Speed": p("NumberRange", [5, 5], min=0),
        "SpreadAngle": p("Vector2", [0, 0], min=-360, max=360),
        "Squash": sequence(0), "Texture": p("content", "rbxasset://textures/particles/sparkles_main.dds"),
        "TimeScale": p("number", 1, min=0, max=1),
        "Transparency": sequence(0, min=0, max=1),
        "VelocityInheritance": p("number", 0), "WindAffectsDrag": p("boolean", False),
        "ZOffset": p("number", 0),
    }},
    "Beam": {"properties": {
        "Attachment0": p("reference", None, className="Attachment"),
        "Attachment1": p("reference", None, className="Attachment"),
        "Brightness": p("number", 1, min=0), "Color": deepcopy(COLOR),
        "CurveSize0": p("number", 0), "CurveSize1": p("number", 0),
        "Enabled": p("boolean", True), "FaceCamera": p("boolean", False),
        "LightEmission": p("number", 0, min=0, max=1),
        "LightInfluence": p("number", 0, min=0, max=1),
        "Segments": p("integer", 10, min=1, max=100), "Texture": p("content", ""),
        "TextureLength": p("number", 1, min=0.001),
        "TextureMode": enum("Stretch", "Stretch Wrap Static", "TextureMode"),
        "TextureSpeed": p("number", 1), "Transparency": sequence(0.5, min=0, max=1),
        "Width0": p("number", 1, min=0), "Width1": p("number", 1, min=0),
        "ZOffset": p("number", 0),
    }},
    "Trail": {"properties": {
        "Attachment0": p("reference", None, className="Attachment"),
        "Attachment1": p("reference", None, className="Attachment"),
        "Brightness": p("number", 1, min=0), "Color": deepcopy(COLOR),
        "Enabled": p("boolean", True), "FaceCamera": p("boolean", False),
        "Lifetime": p("number", 2, min=0.001, max=20),
        "LightEmission": p("number", 0, min=0, max=1),
        "LightInfluence": p("number", 0, min=0, max=1),
        "MaxLength": p("number", 0, min=0), "MinLength": p("number", 0.1, min=0),
        "Texture": p("content", ""), "TextureLength": p("number", 1, min=0.001),
        "TextureMode": enum("Stretch", "Stretch Wrap Static", "TextureMode"),
        "Transparency": sequence(0.5, min=0, max=1), "WidthScale": sequence(1, min=0),
    }},
    "SpecialMesh": {"properties": {
        "MeshId": p("content", ""), "TextureId": p("content", ""),
        "MeshType": enum("Head", "Head Torso Wedge Sphere Cylinder FileMesh Brick Prism Pyramid ParallelRamp RightAngleRamp CornerWedge", "MeshType"),
        "Scale": p("Vector3", [1, 1, 1]), "Offset": p("Vector3", [0, 0, 0]),
        "VertexColor": p("Vector3", [1, 1, 1]),
    }},
    "PointLight": {"properties": deepcopy(LIGHT)},
    "SpotLight": {"properties": {
        **deepcopy(LIGHT), "Angle": p("number", 90, min=0, max=180),
        "Face": enum("Front", NORMAL, "NormalId"),
    }},
    "SurfaceLight": {"properties": {
        **deepcopy(LIGHT), "Angle": p("number", 90, min=0, max=180),
        "Face": enum("Front", NORMAL, "NormalId"),
    }},
}

ANIMATABLE = {"number", "integer", "Vector2", "Vector3", "Color3", "NumberRange", "boolean", "enum"}
for _class in CLASSES.values():
    for _prop in _class["properties"].values():
        _prop["animatable"] = _prop["type"] in ANIMATABLE

SCHEMA = {
    "version": 1, "classes": CLASSES,
    "types": ["boolean", "number", "integer", "string", "content", "enum", "Vector2", "Vector3", "Color3", "NumberRange", "NumberSequence", "ColorSequence", "reference"],
    "limits": {"nodes": 400, "animations": 2000, "duration": 600, "keyframes": 1000},
    "sequenceFormat": {"NumberSequence": "[{time,value,envelope},...] (also accepts [time,value,envelope])", "ColorSequence": "[{time,value:[r,g,b]},...] (also accepts [time,[r,g,b]])"},
    "defaultsPolicy": "Property defaults are editor presets; omitted properties keep Roblox native defaults. Explicit values are never silently dropped.",
    "editorPolicy": "Optional editor.version=1 and editor.curves preserve authoring handles only. Roblox uses the baked properties/keyframes; metadata is never executed. Max depth 8, 20 KB per curve, 50 KB total.",
}

ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def fail(path, message):
    raise ValidationError(f"{path}: {message}")


def identifier(value, path):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        fail(path, "identifiant invalide (lettres, chiffres, _, -, . ; 80 caractères max)")
    return value


def number(value, path, minimum=None, maximum=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(path, "nombre fini requis")
    if integer and int(value) != value:
        fail(path, "entier requis")
    if minimum is not None and value < minimum:
        fail(path, f"minimum {minimum}")
    if maximum is not None and value > maximum:
        fail(path, f"maximum {maximum}")
    return int(value) if integer else value


def text(value, path, maximum=256, allow_empty=True):
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        fail(path, f"texte {'non vide ' if not allow_empty else ''}de {maximum} caractères max requis")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        fail(path, "caractère de contrôle interdit")
    return value


def keys(value, allowed, path):
    if not isinstance(value, dict):
        fail(path, "objet requis")
    unknown = set(value) - set(allowed)
    if unknown:
        fail(path, "champ inconnu : " + ", ".join(sorted(unknown)))


def validate_value(value, spec, path):
    kind = spec["type"]
    if kind == "boolean":
        if not isinstance(value, bool):
            fail(path, "booléen requis")
    elif kind in {"number", "integer"}:
        number(value, path, spec.get("min"), spec.get("max"), kind == "integer")
    elif kind in {"Vector2", "Vector3", "Color3", "NumberRange"}:
        length = 2 if kind in {"Vector2", "NumberRange"} else 3
        if not isinstance(value, list) or len(value) != length:
            fail(path, f"tableau de {length} nombres requis")
        for i, component in enumerate(value):
            number(component, f"{path}[{i}]", 0 if kind == "Color3" else spec.get("min"), 1 if kind == "Color3" else spec.get("max"))
        if kind == "NumberRange" and value[0] > value[1]:
            fail(path, "minimum supérieur au maximum")
    elif kind == "enum":
        if value not in spec["enum"]:
            fail(path, "valeur requise : " + " / ".join(spec["enum"]))
    elif kind in {"string", "content"}:
        text(value, path, 2048 if kind == "content" else 256)
        if kind == "content" and value and not re.fullmatch(r"(?:rbxassetid://[0-9]+|rbxasset://[^\s]+|https?://(?:www\.)?roblox\.com/asset/?\?id=[0-9]+|[0-9]+)", value):
            fail(path, "ID Roblox ou URI de contenu valide requis")
    elif kind == "reference":
        if value is not None:
            identifier(value, path)
    elif kind in {"NumberSequence", "ColorSequence"}:
        if not isinstance(value, list) or not 2 <= len(value) <= 20:
            fail(path, "séquence de 2 à 20 points requise")
        previous = -1
        canonical = []
        for i, point in enumerate(value):
            required = (2, 3) if kind == "NumberSequence" else (2,)
            if isinstance(point, dict):
                keys(point, {"time", "value", "envelope"} if kind == "NumberSequence" else {"time", "value"}, f"{path}[{i}]")
                point = [point.get("time"), point.get("value"), point.get("envelope", 0)] if kind == "NumberSequence" else [point.get("time"), point.get("value")]
            if not isinstance(point, list) or len(point) not in required:
                fail(f"{path}[{i}]", "point invalide")
            time = number(point[0], f"{path}[{i}].time", 0, 1)
            if time <= previous:
                fail(path, "temps des points strictement croissants requis")
            previous = time
            if kind == "ColorSequence":
                validate_value(point[1], {"type": "Color3"}, f"{path}[{i}].color")
                canonical.append({"time": time, "value": point[1]})
            else:
                val = number(point[1], f"{path}[{i}].value", spec.get("min"), spec.get("max"))
                envelope = number(point[2] if len(point) > 2 else 0, f"{path}[{i}].envelope", 0)
                # Native envelopes may extend beyond nominal property limits;
                # the renderer handles/clamps the sampled values.
                canonical.append({"time": time, "value": val, "envelope": envelope})
        if canonical[0]["time"] != 0 or canonical[-1]["time"] != 1:
            fail(path, "la séquence doit commencer à 0 et finir à 1")
        return deepcopy(canonical)
    else:
        fail(path, "type non pris en charge")
    return deepcopy(value)


def validate_project(project):
    """Validate and copy a complete project; never mutate the caller's object."""
    keys(project, {"version", "id", "name", "duration", "loop", "nodes", "animations", "camera", "environment", "editor"}, "project")
    if project.get("version", 1) != 1 or isinstance(project.get("version"), bool):
        fail("version", "seule la version 1 est prise en charge")
    out = {"version": 1, "name": text(project.get("name", "Effet sans titre"), "name", 160, False)}
    if "id" in project:
        out["id"] = identifier(project["id"], "id")
    out["duration"] = number(project.get("duration", 3), "duration", 0.01, 600)
    out["loop"] = validate_value(project.get("loop", False), {"type": "boolean"}, "loop")
    nodes = project.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) > 400:
        fail("nodes", "tableau de 400 objets maximum requis")
    by_id = {}
    out["nodes"] = []
    for i, node in enumerate(nodes):
        path = f"nodes[{i}]"
        keys(node, {"id", "class", "name", "parent", "properties", "timing"}, path)
        ident = identifier(node.get("id"), path + ".id")
        if ident in by_id:
            fail(path, "identifiant déjà utilisé")
        cls = node.get("class")
        if cls not in CLASSES:
            fail(path + ".class", "classe non prise en charge")
        props = node.get("properties", {})
        specs = CLASSES[cls]["properties"]
        keys(props, specs, path + ".properties")
        if cls == "Attachment" and "Orientation" in props and ({"Axis", "SecondaryAxis"} & props.keys()):
            fail(path + ".properties", "Orientation et Axis/SecondaryAxis sont liés : choisir une seule représentation")
        if cls == "Attachment":
            for axis in ("Axis", "SecondaryAxis"):
                if axis in props and props[axis] == [0, 0, 0]:
                    fail(path + "." + axis, "axe non nul requis")
        parent = node.get("parent")
        if parent is not None:
            identifier(parent, path + ".parent")
        cleaned = {"id": ident, "class": cls, "name": text(node.get("name", cls), path + ".name", 160, False), "parent": parent,
                   "properties": {key: validate_value(value, specs[key], path + "." + key) for key, value in props.items()}}
        if "timing" in node:
            if cls not in {"ParticleEmitter", "Beam", "Trail", "PointLight", "SpotLight", "SurfaceLight"}:
                fail(path + ".timing", "timing réservé aux émetteurs, beams, trails et lumières")
            timing = node["timing"]
            keys(timing, {"start", "duration", "mode", "count"}, path + ".timing")
            start = number(timing.get("start", 0), path + ".timing.start", 0, out["duration"])
            duration = number(timing.get("duration", out["duration"] - start), path + ".timing.duration", 0, out["duration"])
            if start + duration > out["duration"] + 1e-9:
                fail(path + ".timing", "la fin dépasse la durée du projet")
            mode = timing.get("mode", "continuous")
            if mode not in {"burst", "continuous"}:
                fail(path + ".timing.mode", "burst ou continuous requis")
            if mode == "burst" and cls != "ParticleEmitter":
                fail(path + ".timing.mode", "burst réservé aux ParticleEmitter")
            cleaned["timing"] = {"start": start, "duration": duration, "mode": mode,
                                 "count": number(timing.get("count", 20), path + ".timing.count", 0, 10000, True)}
        by_id[ident] = cleaned
        out["nodes"].append(cleaned)
    physical = {"Part", "MeshPart"}
    containers = {"Folder", "Model"} | physical
    for node in out["nodes"]:
        path = "node " + node["id"]
        parent = by_id.get(node["parent"])
        if node["parent"] is not None and parent is None:
            fail(path + ".parent", "parent introuvable")
        cls = node["class"]
        allowed = (physical | {"Attachment"}) if cls in {"Attachment", "ParticleEmitter", "PointLight", "SpotLight", "SurfaceLight"} else {"Part"} if cls == "SpecialMesh" else containers | ({"Attachment"} if cls in {"Beam", "Trail"} else set())
        if parent is None and cls not in containers:
            fail(path + ".parent", "cette classe exige un parent compatible")
        if parent and parent["class"] not in allowed:
            fail(path + ".parent", "parent incompatible avec " + cls)
        seen = {node["id"]}
        ancestor = parent
        while ancestor:
            if ancestor["id"] in seen:
                fail(path + ".parent", "cycle dans la hiérarchie")
            seen.add(ancestor["id"])
            ancestor = by_id.get(ancestor["parent"])
        for prop, value in node["properties"].items():
            spec = CLASSES[cls]["properties"][prop]
            if spec["type"] == "reference" and value is not None:
                if value not in by_id or by_id[value]["class"] != spec["className"]:
                    fail(path + "." + prop, "référence vers un Attachment du projet requise")
    animations = project.get("animations", [])
    if not isinstance(animations, list) or len(animations) > 2000:
        fail("animations", "tableau de 2000 animations maximum requis")
    out["animations"] = []
    tracks = set()
    for i, animation in enumerate(animations):
        path = f"animations[{i}]"
        keys(animation, {"node", "property", "keyframes"}, path)
        node_id, prop = animation.get("node"), animation.get("property")
        if node_id not in by_id:
            fail(path + ".node", "objet introuvable")
        spec = CLASSES[by_id[node_id]["class"]]["properties"].get(prop)
        if not spec or not spec["animatable"]:
            fail(path + ".property", "propriété non animable ou inconnue")
        if (node_id, prop) in tracks:
            fail(path, "une seule piste par objet/propriété")
        tracks.add((node_id, prop))
        frames = animation.get("keyframes")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 1000:
            fail(path + ".keyframes", "1 à 1000 images clés requises")
        cleaned_frames, previous = [], -1
        for j, frame in enumerate(frames):
            keys(frame, {"time", "value"}, f"{path}.keyframes[{j}]")
            time = number(frame.get("time"), path + ".time", 0, out["duration"])
            if time <= previous:
                fail(path, "temps des images clés strictement croissants requis")
            previous = time
            cleaned_frames.append({"time": time, "value": validate_value(frame.get("value"), spec, path + ".value")})
        out["animations"].append({"node": node_id, "property": prop, "keyframes": cleaned_frames})
    camera = project.get("camera", {"position": [10, 6, 12], "target": [0, 1, 0]})
    keys(camera, {"position", "target", "fov"}, "camera")
    out["camera"] = {key: validate_value(camera.get(key, default), {"type": "Vector3"}, "camera." + key)
                     for key, default in (("position", [10, 6, 12]), ("target", [0, 1, 0]))}
    if out["camera"]["position"] == out["camera"]["target"]:
        fail("camera", "position et cible doivent être différentes")
    if "fov" in camera:
        out["camera"]["fov"] = number(camera["fov"], "camera.fov", 1, 120)
    if "environment" in project:
        environment = project["environment"]
        keys(environment, {"background"}, "environment")
        background = environment.get("background", "#191522")
        if not isinstance(background, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", background):
            fail("environment.background", "couleur hexadécimale #RRGGBB requise")
        # This is the author's 2D plan backdrop, not a native Lighting mutation.
        out["environment"] = {"background": background}
    if "editor" in project:
        editor = project["editor"]
        keys(editor, {"version", "curves"}, "editor")
        if editor.get("version") != 1 or isinstance(editor.get("version"), bool):
            fail("editor.version", "version 1 requise")
        curves = editor.get("curves", {})
        if not isinstance(curves, dict) or len(curves) > 2000:
            fail("editor.curves", "objet de 2000 courbes maximum requis")

        def metadata(value, path, depth=0):
            if depth > 8:
                fail(path, "métadonnée trop imbriquée (8 niveaux max)")
            if value is None or isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                number(value, path)
            elif isinstance(value, str):
                text(value, path, 20000)
            elif isinstance(value, list):
                if len(value) > 2000:
                    fail(path, "2000 éléments maximum")
                for i, child in enumerate(value):
                    metadata(child, f"{path}[{i}]", depth + 1)
            elif isinstance(value, dict):
                if len(value) > 2000:
                    fail(path, "2000 champs maximum")
                for key, child in value.items():
                    text(key, path + ".key", 160, False)
                    if key in {"__proto__", "constructor", "prototype"}:
                        fail(path, "clé de prototype interdite")
                    metadata(child, path + "." + key, depth + 1)
            else:
                fail(path, "métadonnée JSON uniquement")

        for key, curve in curves.items():
            text(key, "editor.curves.key", 180, False)
            node_id, separator, prop = key.partition("::")
            if not separator or not prop or "::" in prop:
                fail("editor.curves." + key, "clé attendue : node.id::property")
            identifier(node_id, "editor.curves.node")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", prop):
                fail("editor.curves.property", "nom de propriété invalide")
            if not isinstance(curve, dict):
                fail("editor.curves." + key, "objet JSON requis")
            metadata(curve, "editor.curves." + key)
            if len(json.dumps(curve, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 20000:
                fail("editor.curves." + key, "courbe limitée à 20 Ko")
        cleaned_editor = {"version": 1, "curves": deepcopy(curves)}
        if len(json.dumps(cleaned_editor, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 50000:
            fail("editor", "métadonnées limitées à 50 Ko")
        out["editor"] = cleaned_editor
    return out
