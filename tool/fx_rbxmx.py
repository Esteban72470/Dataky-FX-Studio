"""Export a Dataky FX project as a Roblox model file (.rbxmx) to drag into Studio.

The model contains the effect's native objects, visible and editable by hand, and a
ModuleScript « DatakyFX » that plays the timeline on those very objects:

    local fx = require(workspace.MonEffet.DatakyFX)
    fx.play()   -- fx.stop(), fx.pause(), fx.resume(), fx.status()

Each object carries a DatakyFXNodeId attribute so renaming it in Studio keeps the
timeline working. Serialized property names and types follow the rbx-dom reflection
database (e.g. BasePart.Size → "size", Part.Shape → "shape", Color → Color3uint8,
textures → TextureContent). Enum token values come from the Roblox engine API docs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Any
from xml.sax.saxutils import escape

if __package__:
    from .fx_export import RUNTIME_PATH, _lua
    from .fx_schema import CLASSES, validate_project
else:
    from fx_export import RUNTIME_PATH, _lua
    from fx_schema import CLASSES, validate_project

ENUMS = {
    "Material": {"Plastic": 256, "SmoothPlastic": 272, "Neon": 288, "Wood": 512, "WoodPlanks": 528, "Marble": 784, "Basalt": 788, "Slate": 800,
                 "CrackedLava": 804, "Concrete": 816, "Limestone": 820, "Granite": 832, "Pavement": 836, "Brick": 848, "Pebble": 864,
                 "Cobblestone": 880, "Rock": 896, "Sandstone": 912, "CorrodedMetal": 1040, "DiamondPlate": 1056, "Foil": 1072, "Metal": 1088,
                 "Grass": 1280, "LeafyGrass": 1284, "Sand": 1296, "Fabric": 1312, "Snow": 1328, "Mud": 1344, "Ground": 1360, "Asphalt": 1376,
                 "Salt": 1392, "Ice": 1536, "Glacier": 1552, "Glass": 1568, "ForceField": 1584, "Air": 1792, "Water": 2048, "Cardboard": 2304,
                 "Carpet": 2305, "CeramicTiles": 2306, "ClayRoofTiles": 2307, "RoofShingles": 2308, "Leather": 2309, "Plaster": 2310, "Rubber": 2311},
    "MeshType": {"Head": 0, "Torso": 1, "Wedge": 2, "Sphere": 3, "Cylinder": 4, "FileMesh": 5, "Brick": 6, "Prism": 7, "Pyramid": 8,
                 "ParallelRamp": 9, "RightAngleRamp": 10, "CornerWedge": 11},
    "NormalId": {"Right": 0, "Top": 1, "Back": 2, "Left": 3, "Bottom": 4, "Front": 5},
    "PartType": {"Ball": 0, "Block": 1, "Cylinder": 2, "Wedge": 3, "CornerWedge": 4},
    "ParticleEmitterShape": {"Box": 0, "Sphere": 1, "Cylinder": 2, "Disc": 3},
    "ParticleEmitterShapeInOut": {"Outward": 0, "Inward": 1, "InAndOut": 2},
    "ParticleEmitterShapeStyle": {"Volume": 0, "Surface": 1},
    "ParticleFlipbookLayout": {"None": 0, "Grid2x2": 1, "Grid4x4": 2, "Grid8x8": 3, "Custom": 4},
    "ParticleFlipbookMode": {"Loop": 0, "OneShot": 1, "PingPong": 2, "Random": 3},
    "ParticleOrientation": {"FacingCamera": 0, "FacingCameraWorldUp": 1, "VelocityParallel": 2, "VelocityPerpendicular": 3},
    "RenderFidelity": {"Automatic": 0, "Precise": 1, "Performance": 2},
    "SurfaceType": {"Smooth": 0, "Glue": 1, "Weld": 2, "Studs": 3, "Inlet": 4, "Universal": 5, "Hinge": 6, "Motor": 7, "SteppingMotor": 8,
                    "SmoothNoOutlines": 10},
    "TextureMode": {"Stretch": 0, "Wrap": 1, "Static": 2},
}
BASE_PARTS = {"Part", "MeshPart"}
SWITCHES = {"ParticleEmitter", "Beam", "Trail", "PointLight", "SpotLight", "SurfaceLight"}
# Properties whose serialized name differs (rbx-dom: SerializesAs or Migrate to a Content property).
RENAMED = {"Size": "size", "Shape": "shape", "MaterialVariant": "MaterialVariantSerialized"}
CONTENT = {("ParticleEmitter", "Texture"): "TextureContent", ("Beam", "Texture"): "TextureContent", ("Trail", "Texture"): "TextureContent",
           ("MeshPart", "MeshId"): "MeshContent", ("MeshPart", "TextureID"): "TextureContent",
           ("SpecialMesh", "MeshId"): "MeshContent", ("SpecialMesh", "TextureId"): "TextureContent"}
FRAME_PROPERTIES = {"Position", "Orientation", "Axis", "SecondaryAxis"}


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("nombre non fini")
    text = f"{value:.7g}"
    return "0" if text == "-0" else text


def _matrix(orientation: list[float]) -> list[float]:
    """CFrame.fromOrientation(rx, ry, rz) = Ry · Rx · Rz, rows R00..R22."""
    rx, ry, rz = (math.radians(v) for v in orientation)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    x = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    y = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    mul = lambda a, b: [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
    m = mul(y, mul(x, z))
    return [m[r][c] for r in range(3) for c in range(3)]


def _axes(axis: list[float], secondary: list[float]) -> list[float]:
    norm = lambda v: [c / (math.sqrt(sum(x * x for x in v)) or 1) for c in v]
    cross = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    x = norm(axis)
    z = cross(x, secondary)
    if math.sqrt(sum(v * v for v in z)) < 1e-6:
        z = cross(x, [0, 1, 0] if abs(x[1]) < 0.9 else [0, 0, 1])
    z = norm(z)
    y = cross(z, x)
    return [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]]


def _content(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"(?:rbxassetid://)?(\d+)", text) or re.search(r"[?&]id=(\d+)$", text)
    return f"rbxassetid://{match.group(1)}" if match else text


def _attributes(values: dict[str, str]) -> str:
    """Roblox attribute blob: u32 count, then (string name, u8 type 0x02, string value)."""
    data = struct.pack("<I", len(values))
    for key, value in values.items():
        for text, prefix in ((key, b""), (value, b"\x02")):
            raw = text.encode("utf-8")
            data += prefix + struct.pack("<I", len(raw)) + raw
    return base64.b64encode(data).decode("ascii")


def _referent(ident: str) -> str:
    return "RBX" + hashlib.md5(ident.encode("utf-8")).hexdigest().upper()


class Writer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> None:
        self.lines.append(text)

    def prop(self, kind: str, name: str, inner: str) -> None:
        self.add(f'<{kind} name="{escape(name)}">{inner}</{kind}>')

    def vector(self, kind: str, name: str, values: list[float]) -> None:
        self.prop(kind, name, "".join(f"<{axis}>{_number(v)}</{axis}>" for axis, v in zip("XYZ", values)))

    def cframe(self, name: str, position: list[float], rotation: list[float]) -> None:
        keys = ["X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"]
        self.prop("CoordinateFrame", name, "".join(f"<{k}>{_number(v)}</{k}>" for k, v in zip(keys, [*position, *rotation])))


def _write_property(w: Writer, node: dict[str, Any], key: str, value: Any, referents: dict[str, str]) -> None:
    cls = node["class"]
    spec = CLASSES[cls]["properties"][key]
    kind = spec["type"]
    name = RENAMED.get(key, key) if cls in BASE_PARTS or key == "MaterialVariant" else key
    if (cls, key) in CONTENT:
        uri = _content(value)
        w.prop("Content", CONTENT[(cls, key)], f"<uri>{escape(uri)}</uri>" if uri else "<null></null>")
    elif kind == "content":
        uri = _content(value)
        w.prop("ContentId", key, f"<url>{escape(uri)}</url>" if uri else "<null></null>")
    elif kind == "boolean":
        w.prop("bool", name, "true" if value else "false")
    elif kind == "number":
        w.prop("float", name, _number(value))
    elif kind == "integer":
        w.prop("int", name, str(int(value)))
    elif kind == "string":
        if key == "MaterialVariant" and not value:
            return
        w.prop("string", name, escape(value))
    elif kind == "enum":
        w.prop("token", name, str(ENUMS[spec["enumType"]][value]))
    elif kind == "Vector2":
        w.prop("Vector2", name, f"<X>{_number(value[0])}</X><Y>{_number(value[1])}</Y>")
    elif kind == "Vector3":
        w.vector("Vector3", name, value)
    elif kind == "Color3":
        if cls in BASE_PARTS:
            r, g, b = (max(0, min(255, round(c * 255))) for c in value)
            w.prop("Color3uint8", "Color3uint8", str(0xFF000000 | r << 16 | g << 8 | b))
        else:
            w.prop("Color3", name, "".join(f"<{c}>{_number(v)}</{c}>" for c, v in zip("RGB", value)))
    elif kind == "NumberRange":
        w.prop("NumberRange", name, f"{_number(value[0])} {_number(value[1])} ")
    elif kind == "NumberSequence":
        w.prop("NumberSequence", name, "".join(f"{_number(p['time'])} {_number(p['value'])} {_number(p['envelope'])} " for p in value))
    elif kind == "ColorSequence":
        w.prop("ColorSequence", name, "".join(f"{_number(p['time'])} {' '.join(_number(c) for c in p['value'])} 0 " for p in value))
    elif kind == "reference":
        w.prop("Ref", name, referents[value] if value else "null")
    else:
        raise ValueError(f"type non exportable : {kind}")


def _write_node(w: Writer, node: dict[str, Any], children: dict[str | None, list[dict[str, Any]]], referents: dict[str, str]) -> None:
    cls, props = node["class"], node["properties"]
    w.add(f'<Item class="{cls}" referent="{referents[node["id"]]}"><Properties>')
    w.prop("string", "Name", escape(node["name"]))
    w.prop("BinaryString", "AttributesSerialize", _attributes({"DatakyFXNodeId": node["id"]}))
    if cls in BASE_PARTS or cls == "Attachment":
        position = props.get("Position", [0, 0, 0])
        if cls == "Attachment" and ("Axis" in props or "SecondaryAxis" in props):
            rotation = _axes(props.get("Axis", [1, 0, 0]), props.get("SecondaryAxis", [0, 1, 0]))
        else:
            rotation = _matrix(props.get("Orientation", [0, 0, 0]))
        w.cframe("CFrame", position, rotation)
    for key, value in props.items():
        if key in FRAME_PROPERTIES and (cls in BASE_PARTS or cls == "Attachment"):
            continue
        if key == "Enabled" and node.get("timing"):
            continue
        _write_property(w, node, key, value, referents)
    if cls in SWITCHES and node.get("timing"):
        # Le lecteur allume ces objets au bon instant ; ils restent éteints dans le fichier.
        w.prop("bool", "Enabled", "false")
    w.add("</Properties>")
    for child in children.get(node["id"], []):
        _write_node(w, child, children, referents)
    w.add("</Item>")


def player_source(project: dict[str, Any]) -> str:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8-sig")
    return (
        f"-- Dataky FX Studio — lecteur de l’effet {project['name'].replace(chr(10), ' ')}\n"
        "-- Ce module joue la timeline sur les objets de son modèle parent (attribut DatakyFXNodeId).\n"
        "-- local fx = require(chemin.Vers.LeModele.DatakyFX)\n"
        "-- fx.play()  -- fx.stop(), fx.pause(), fx.resume(), fx.status()\n"
        "-- Déplacez le modèle par son pivot : les animations de position suivent (sans rotation).\n"
        "local Runtime = (function()\n" + runtime + "\nend)()\n"
        "local Project = " + _lua(project) + "\n"
        "local Effect = {}\n"
        "local function origin()\n"
        "    local model = script.Parent\n"
        "    local pivot = model:IsA(\"PVInstance\") and model:GetPivot() or CFrame.new()\n"
        "    return {pivot.X, pivot.Y, pivot.Z}\n"
        "end\n"
        "function Effect.play()\n"
        "    Runtime.adopt(Project, script.Parent, {preview=false, camera=false, origin=origin()})\n"
        "    return Runtime.play()\n"
        "end\n"
        "Effect.stop = Runtime.stop\n"
        "Effect.pause = Runtime.pause\n"
        "Effect.resume = Runtime.resume\n"
        "Effect.status = Runtime.status\n"
        "return Effect\n"
    )


def export_rbxmx(project: dict[str, Any]) -> str:
    project = validate_project(project)
    referents = {node["id"]: _referent(node["id"]) for node in project["nodes"]}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for node in project["nodes"]:
        children.setdefault(node["parent"], []).append(node)
    w = Writer()
    w.add('<?xml version="1.0" encoding="utf-8"?>')
    w.add('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
          'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">')
    w.add('<Meta name="ExplicitAutoJoints">true</Meta>')
    w.add('<External>null</External><External>nil</External>')
    w.add(f'<Item class="Model" referent="{_referent("model:" + project["name"])}"><Properties>')
    w.prop("string", "Name", escape(project["name"]))
    # Pivot fixé à l’origine : le lecteur en déduit le déplacement du modèle.
    w.add('<OptionalCoordinateFrame name="WorldPivotData"><CFrame>' + "".join(
        f"<{k}>{v}</{k}>" for k, v in zip(["X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"],
                                         [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1])) + "</CFrame></OptionalCoordinateFrame>")
    w.add("</Properties>")
    for node in children.get(None, []):
        _write_node(w, node, children, referents)
    w.add(f'<Item class="ModuleScript" referent="{_referent("module:" + project["name"])}"><Properties>')
    w.prop("string", "Name", "DatakyFX")
    w.add('<ProtectedString name="Source"><![CDATA[' + player_source(project).replace("]]>", "]]]]><![CDATA[>") + "]]></ProtectedString>")
    w.add("</Properties></Item>")
    w.add("</Item></roblox>")
    return "\n".join(w.lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(export_rbxmx(json.loads(args.project.read_text(encoding="utf-8-sig"))), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
