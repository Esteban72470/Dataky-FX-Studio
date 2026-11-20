"""Export a Dataky FX project as standalone, offline Roblox Luau source.

The generated ModuleScript exposes build(parent, origin), play(), stop(), clear(),
pause(), resume(), status(). It never calls an HTTP endpoint or uses loadstring.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
from typing import Any

RUNTIME_PATH = Path(__file__).with_name("fx_runtime.lua")
KIT_PATH = Path(__file__).with_name("fx_kit.lua")


class MeshExportError(ValueError):
    """An editable local mesh still needs an authorized Roblox asset mapping."""

    def __init__(self, manifest: dict[str, Any]):
        self.manifest = manifest
        missing = ", ".join(item["node"] for item in manifest["missing_assets"])
        super().__init__(
            "Export Roblox bloqué : maillage local sans MeshId Roblox pour " + missing
            + ". Importez le fichier OBJ dans Roblox Studio, vérifiez ses dimensions et ses UV, "
            "puis renseignez le MeshId obtenu. Le JSON et le manifeste restent exportables."
        )


def _roblox_mesh_uri(value: Any) -> str | None:
    """A local preview requires a persistent positive Roblox mesh asset ID.

    This checks an explicit mapping, never claims ownership or visual equality.
    Session content handles and local rbxasset:// paths are not published assets.
    """
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"(?:rbxassetid://|https?://(?:www\.)?roblox\.com/asset/?\?id=)?([0-9]+)", value
    )
    if not match or int(match.group(1)) <= 0:
        return None
    return "rbxassetid://" + str(int(match.group(1)))


def mesh_export_manifest(project: dict[str, Any]) -> dict[str, Any]:
    """Describe local geometry mappings without embedding or uploading meshes.

    The schema validates the original editable project. Local OBJ geometry is
    preview metadata, not a Roblox mesh asset. Mapping an ID is an explicit
    authoring step; authorization and matching geometry still require Studio.
    """
    if __package__:
        from .fx_schema import validate_project
    else:
        from fx_schema import validate_project
    return _validated_mesh_export_manifest(validate_project(project))


def _validated_mesh_export_manifest(project: dict[str, Any]) -> dict[str, Any]:
    by_id = {node["id"]: node for node in project["nodes"]}
    missing, mapped = [], []
    for node_id, geometry in (project.get("editor", {}).get("meshes") or {}).items():
        node = by_id[node_id]
        source = geometry.get("source") or {}
        item = {
            "node": node_id,
            "class": node["class"],
            "source": {key: source[key] for key in ("name", "format", "sha256", "dimensions") if key in source},
            "mesh_id": _roblox_mesh_uri(node.get("properties", {}).get("MeshId")),
            "verification": "Roblox permissions, geometry, dimensions and UVs must be checked in Studio",
        }
        (mapped if item["mesh_id"] else missing).append(item)
    return {
        "version": 1,
        "project": project.get("id") or project["name"],
        "exportable": not missing,
        "missing_assets": missing,
        "mapped_assets": mapped,
        "manual_steps": [
            "Keep the original OBJ file; JSON contains preview triangles, not an uploaded Roblox asset.",
            "Import each original OBJ through Roblox Studio's 3D importer using your own authorized account.",
            "Check axis orientation, world scale, pivot, normals, UVs and texture permissions against the local preview.",
            "Copy the resulting persistent MeshId into the corresponding MeshPart properties and export again.",
            "Verify the exported effect inside the target Roblox experience before integration.",
        ] if missing or mapped else [],
        "warnings": [
            "An explicit MeshId is not proof of asset access or equivalent geometry; this export never uploads assets.",
            "Preview mesh metadata is omitted from native exports; preserve JSON to continue editing it locally.",
        ] if missing or mapped else [],
    }


def prepare_native_project(project: dict[str, Any]) -> dict[str, Any]:
    """Validate mappings and remove renderer-only mesh buffers and local texture paths from native data."""
    if __package__:
        from .fx_schema import validate_project
    else:
        from fx_schema import validate_project
    project = validate_project(project)
    manifest = _validated_mesh_export_manifest(project)
    if not manifest["exportable"]:
        raise MeshExportError(manifest)
    if "editor" in project:
        project["editor"].pop("meshes", None)
    project.pop("local_textures", None)
    return project


_LUA_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LUA_KEYWORDS = frozenset({
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "if", "in", "local", "nil", "not", "or", "repeat",
    "return", "then", "true", "until", "while",
})

# Property defaults guaranteed identical between fx_kit.lua and Roblox Instance.new.
# ParticleEmitter.LightInfluence is intentionally NOT omitted (Roblox native default is 1).
_BASE_PART_DEFAULTS = {
    "Anchored": True, "CanCollide": False, "CanTouch": False, "CanQuery": False,
    "Transparency": 1, "CastShadow": False, "Massless": True,
    "Position": [0, 0, 0], "Orientation": [0, 0, 0],
}
_LIGHT_DEFAULTS = {"Enabled": True, "Shadows": False, "Brightness": 1, "Range": 8, "Color": [1, 1, 1]}
_KIT_DEFAULTS: dict[str, dict[str, Any]] = {
    "Part": _BASE_PART_DEFAULTS,
    "MeshPart": _BASE_PART_DEFAULTS,
    "Attachment": {"Position": [0, 0, 0], "Visible": False},
    "ParticleEmitter": {
        "Enabled": True, "SpreadAngle": [0, 0], "Acceleration": [0, 0, 0], "Drag": 0,
        "Rotation": [0, 0], "RotSpeed": [0, 0], "ZOffset": 0, "VelocityInheritance": 0,
        "LockedToPart": False, "TimeScale": 1, "WindAffectsDrag": False,
        "LightEmission": 0, "Brightness": 1, "EmissionDirection": "Top",
        "Orientation": "FacingCamera", "FlipbookLayout": "None",
        "Shape": "Box", "ShapeStyle": "Volume", "ShapeInOut": "Outward", "ShapePartial": 1,
    },
    "Beam": {
        "Enabled": True, "CurveSize0": 0, "CurveSize1": 0, "FaceCamera": False,
        "LightEmission": 0, "LightInfluence": 0, "Brightness": 1, "Segments": 10,
        "TextureMode": "Stretch", "TextureLength": 1, "TextureSpeed": 1,
        "Width0": 1, "Width1": 1, "ZOffset": 0,
    },
    "Trail": {
        "Enabled": True, "FaceCamera": False, "LightEmission": 0, "LightInfluence": 0,
        "Brightness": 1, "MaxLength": 0, "MinLength": 0.1, "TextureLength": 1,
        "TextureMode": "Stretch", "Lifetime": 2,
    },
    "PointLight": _LIGHT_DEFAULTS,
    "SpotLight": _LIGHT_DEFAULTS,
    "SurfaceLight": _LIGHT_DEFAULTS,
}


def _same_default(value: Any, default: Any) -> bool:
    if isinstance(value, bool) or isinstance(default, bool):
        return type(value) is type(default) and value == default
    if isinstance(value, (int, float)) and isinstance(default, (int, float)):
        return abs(float(value) - float(default)) < 1e-6
    if isinstance(value, list) and isinstance(default, list) and len(value) == len(default):
        return all(_same_default(a, b) for a, b in zip(value, default))
    return value == default


def _compact_for_kit(project: dict[str, Any]) -> dict[str, Any]:
    """Prune redundant defaults and editor-only fields for DatakyFXKit library output."""
    if __package__:
        from .fx_schema import CLASSES
    else:
        from fx_schema import CLASSES
    duration = float(project.get("duration", 3))
    animated_props = {(t["node"], t["property"]) for t in project.get("animations", [])}
    out: dict[str, Any] = {
        "version": project["version"],
        "name": project["name"],
        "duration": project["duration"],
    }
    if project.get("loop"):
        out["loop"] = True
    if project.get("params"):
        out["params"] = project["params"]
    compact_nodes = []
    for node in project.get("nodes", []):
        cls = node["class"]
        scale_with = node.get("scaleWith") or {}
        defaults = _KIT_DEFAULTS.get(cls, {})
        specs = CLASSES[cls]["properties"]
        raw_props = node.get("properties") or {}
        props: dict[str, Any] = {}
        for key, value in raw_props.items():
            if key not in scale_with and (node["id"], key) not in animated_props:
                if key in defaults and _same_default(value, defaults[key]):
                    continue
                if cls == "Attachment" and key == "Orientation" and "Axis" not in raw_props and "SecondaryAxis" not in raw_props and _same_default(value, [0, 0, 0]):
                    continue
            prop_type = specs[key]["type"]
            if prop_type == "NumberSequence" and isinstance(value, list):
                seq = []
                for pt in value:
                    t = pt["time"] if isinstance(pt, dict) else pt[0]
                    v = pt["value"] if isinstance(pt, dict) else pt[1]
                    env = (pt.get("envelope", 0) if isinstance(pt, dict) else (pt[2] if len(pt) > 2 else 0)) or 0
                    seq.append([t, v] if abs(float(env)) < 1e-6 else [t, v, env])
                props[key] = seq
            elif prop_type == "ColorSequence" and isinstance(value, list):
                props[key] = [
                    [pt["time"] if isinstance(pt, dict) else pt[0], pt["value"] if isinstance(pt, dict) else pt[1]]
                    for pt in value
                ]
            else:
                props[key] = value
        compact_node: dict[str, Any] = {"id": node["id"], "class": cls}
        if node.get("name") and node["name"] != cls:
            compact_node["name"] = node["name"]
        if node.get("parent") is not None:
            compact_node["parent"] = node["parent"]
        if props:
            compact_node["properties"] = props
        if scale_with:
            compact_node["scaleWith"] = scale_with
        timing = node.get("timing")
        if timing is not None:
            mode = timing.get("mode", "continuous")
            start = float(timing.get("start", 0))
            span = float(timing.get("duration", duration))
            # A full-duration continuous timing starting at 0 is fx_kit.lua's default when timing is omitted.
            if not (mode == "continuous" and abs(start) < 1e-6 and abs(span - duration) < 1e-6):
                t_out: dict[str, Any] = {"mode": mode}
                if abs(start) >= 1e-6:
                    t_out["start"] = timing["start"]
                if abs(span - duration) >= 1e-6:
                    t_out["duration"] = timing["duration"]
                if mode == "burst" and timing.get("count", 30) != 30:
                    t_out["count"] = timing["count"]
                compact_node["timing"] = t_out
        compact_nodes.append(compact_node)
    out["nodes"] = compact_nodes
    if project.get("animations"):
        out["animations"] = project["animations"]
    return out


def _lua_num(value: int | float) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers cannot be exported")
        if abs(value) < 1e-6:
            return "0"
        rounded = round(value, 4)
        if rounded == int(rounded):
            return str(int(rounded))
        return f"{rounded:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _lua(value: Any) -> str:
    """Serialize JSON values as Luau literals without executable interpolation."""
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _lua_num(value)
    if isinstance(value, str):
        # JSON's \uXXXX is not Lua syntax; utf-8 text is valid in quoted Luau.
        # Escape controls with unambiguous three-digit decimal escapes.
        result = []
        for char in value:
            code = ord(char)
            if char == "\\":
                result.append("\\\\")
            elif char == '"':
                result.append('\\"')
            elif code < 32 or code == 127:
                result.append(f"\\{code:03d}")
            else:
                result.append(char)
        return '"' + "".join(result) + '"'
    if isinstance(value, list):
        return "{" + ",".join(_lua(item) for item in value) + "}"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Project dictionary keys must be strings")
        pairs = []
        for key, item in value.items():
            if item is None:
                continue
            k = key if (_LUA_IDENT.match(key) and key not in _LUA_KEYWORDS) else "[" + _lua(key) + "]"
            pairs.append(k + "=" + _lua(item))
        return "{" + ",".join(pairs) + "}"
    raise ValueError(f"Unsupported project value: {type(value).__name__}")


def export_project(project: dict[str, Any]) -> str:
    project = prepare_native_project(project)
    if not isinstance(project, dict) or project.get("version") != 1 or not isinstance(project.get("nodes"), list):
        raise ValueError("Dataky FX project version 1 with nodes is required")
    if len(project["nodes"]) > 400:
        raise ValueError("A project can contain at most 400 nodes")
    source = RUNTIME_PATH.read_text(encoding="utf-8-sig")
    literal = _lua(project)
    return (
        "-- Dataky FX Studio — standalone native Roblox effect\n"
        "-- Put this source in a ModuleScript; no local server or AI is required.\n"
        "-- local fx = require(path.To.ThisModule)\n"
        "-- fx.build(workspace, Vector3.new(0, 4, 0)); fx.play()\n"
        "-- Coordinates of BaseParts are relative to the supplied origin.\n"
        "local Runtime = (function()\n" + source + "\nend)()\n"
        "local Project = " + literal + "\n"
        "local Effect = {}\n"
        "function Effect.build(parent, origin)\n"
        "    origin = origin or Vector3.zero\n"
        "    return Runtime.apply(Project, {preview=false, camera=false, parent=parent or workspace, "
        "rootName=Project.name or 'DatakyFX', origin={origin.X,origin.Y,origin.Z}})\n"
        "end\n"
        "function Effect.play()\n"
        "    if not Runtime.status().ready then Effect.build() end\n"
        "    return Runtime.play()\n"
        "end\n"
        "Effect.stop = Runtime.stop\n"
        "Effect.clear = Runtime.clear\n"
        "Effect.pause = Runtime.pause\n"
        "Effect.resume = Runtime.resume\n"
        "Effect.status = Runtime.status\n"
        "return Effect\n"
    )


def export_library(recipes: dict[str, dict[str, Any]]) -> str:
    """Serialize several validated version-1 recipes as one data ModuleScript.

    Keys are supplied by the caller (normally the input filename stem). Data
    keeps the ordinary recipe format, including params, scaleWith and tracks;
    DatakyFXKit ignores carrier Part Position/Transparency preview tracks unless
    the track explicitly opts into runtime playback with runtime=true.
    listTextures() lives on the metatable so pairs() still yields only recipes.
    """
    if not isinstance(recipes, dict) or not recipes:
        raise ValueError("Une bibliothèque doit contenir au moins une recette")
    validated = {}
    compacted = {}
    for name, recipe in recipes.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Chaque recette doit avoir un nom court non vide")
        native = prepare_native_project(recipe)
        validated[name] = native
        compacted[name] = _compact_for_kit(native)
    return (
        "-- Dataky FX Studio — recipe library (data only)\n"
        "-- Install DatakyFXKit.lua as a sibling ModuleScript.\n"
        "-- local FX = require(script.Parent.DatakyFXKit)\n"
        "-- local Recipes = require(script.Parent.MesEffets)\n"
        "-- local h = FX.play(Recipes[\"NomCourt\"], CFrame.new(), {scale=1})\n"
        "-- Recipes:listTextures() returns sorted, unique texture content URIs.\n"
        "local Recipes = " + _lua(compacted) + "\n"
        "local Textures = " + _lua(library_textures(validated)) + "\n"
        "local function listTextures()\n"
        "    return table.clone(Textures)\n"
        "end\n"
        "-- Metatable access also works if a recipe is named listTextures.\n"
        "return setmetatable(Recipes, {__index={listTextures=listTextures}, listTextures=listTextures})\n"
    )


def library_textures(recipes: dict[str, dict[str, Any]]) -> list[str]:
    """List explicit texture content URIs, including surface textures, not meshes.

    The caller supplies validated recipes. Aliases are normalized before
    deduplication so an asset used by several particle/ribbon layers is loaded
    once. Built-in rbxasset:// content retains its original URI.
    """
    properties = {"ParticleEmitter": "Texture", "Beam": "Texture", "Trail": "Texture",
                  "MeshPart": "TextureID", "SpecialMesh": "TextureId"}
    textures: set[str] = set()
    for recipe in recipes.values():
        for node in recipe.get("nodes", []):
            key = properties.get(node.get("class"))
            value = node.get("properties", {}).get(key, "") if key else ""
            if not value:
                continue
            match = re.fullmatch(r"(?:rbxassetid://|https?://(?:www\.)?roblox\.com/asset/?\?id=)?([0-9]+)", value)
            textures.add("rbxassetid://" + match.group(1) if match else value)
    return sorted(textures)


def write_library(recipes: dict[str, dict[str, Any]], out: str | Path) -> tuple[Path, Path]:
    """Write the data module and its independent gameplay kit beside it."""
    path = Path(out)
    kit = path.with_name("DatakyFXKit.lua")
    if path.resolve() == kit.resolve():
        raise ValueError("Le module de données ne doit pas s'appeler DatakyFXKit.lua")
    source = export_library(recipes)
    kit_source = KIT_PATH.read_text(encoding="utf-8-sig")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    kit.write_text(kit_source, encoding="utf-8")
    return path, kit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.project.read_text(encoding="utf-8-sig"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(export_project(data), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
