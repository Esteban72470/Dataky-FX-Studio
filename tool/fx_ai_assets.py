"""Compile local-AI layers with assets from a validated live catalogue snapshot.

The model supplies references, never paths, executable source or invented asset
properties. A selected record is resolved back to the trusted snapshot before
its URI or local preview geometry is used. Native mesh assets and local OBJ
preview triangles remain distinct throughout export.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

if __package__:
    from .fx_builder import merge_recipes
    from .fx_modules import BLOCKS, compose
    from .fx_schema import validate_project
else:
    from fx_builder import merge_recipes
    from fx_modules import BLOCKS, compose
    from fx_schema import validate_project


class AssetCompileError(ValueError):
    pass


COMMON_FIELDS = {"block", "at", "color", "position", "scale", "intensity", "name", "asset_query", "asset_key"}
MESH_FIELDS = {"duration", "orientation", "size", "spin", "expand", "end_position", "transparency"}
PRIMARY_SUFFIXES = {"flash": "coeur", "sparks": "etincelles", "shockwave": "anneau", "smoke": "fumee",
                    "slash": "croissant", "fire": "flammes", "charge": "aspiration", "orb": "halo"}


def _catalogue():
    if __package__:
        from . import fx_ai_catalog
    else:
        import fx_ai_catalog
    return fx_ai_catalog


def _number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AssetCompileError(f"{label} : nombre fini requis")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise AssetCompileError(f"{label} : valeur hors limites")
    return float(value)


def _vector(value, label, minimum=-200, maximum=200):
    if not isinstance(value, list) or len(value) != 3:
        raise AssetCompileError(f"{label} : trois nombres requis")
    return [_number(v, label, minimum, maximum) for v in value]


def _text(value, label, maximum=320, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or any(ord(c) < 32 for c in value):
        raise AssetCompileError(f"{label} : texte court requis")
    return value


def _uri(value, *, empty=False):
    if empty and value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise AssetCompileError("URI d'asset Roblox requise")
    match = re.fullmatch(r"(?:rbxassetid://|https?://(?:www\.)?roblox\.com/asset/?\?id=)?([0-9]+)", value)
    if not match or int(match.group(1)) <= 0:
        raise AssetCompileError("URI d'asset Roblox permanente positive requise")
    return "rbxassetid://" + str(int(match.group(1)))


def _validate_layer(item, index):
    label = f"blocks[{index}]"
    if not isinstance(item, dict) or not {"block", "at", "color"} <= item.keys():
        raise AssetCompileError(f"{label} : block, at et color requis")
    block = item["block"]
    if not isinstance(block, str) or block not in {*BLOCKS, "mesh"}:
        raise AssetCompileError(f"{label} : brique inconnue")
    allowed = COMMON_FIELDS | (MESH_FIELDS if block == "mesh" else set(BLOCKS[block]["params"]))
    unknown = item.keys() - allowed
    if unknown:
        raise AssetCompileError(f"{label} : champs inconnus {', '.join(sorted(unknown))}")
    _number(item["at"], label + ".at", 0, 30)
    _vector(item["color"], label + ".color", 0, 1)
    for name in ("position", "start", "end", "end_position"):
        if name in item:
            _vector(item[name], label + "." + name)
    for name in ("orientation", "spin"):
        if name in item:
            _vector(item[name], label + "." + name, -1440, 1440)
    if "size" in item:
        _vector(item["size"], label + ".size", .001, 2048)
    if "color2" in item:
        _vector(item["color2"], label + ".color2", 0, 1)
    for name, lower, upper in (("scale", .05, 5), ("intensity", .05, 3), ("duration", .05, 12),
                               ("expand", .01, 20), ("transparency", 0, 1), ("angle", -1440, 1440), ("bend", -40, 40)):
        if name in item:
            _number(item[name], label + "." + name, lower, upper)
    for name, limit in (("name", 120), ("asset_query", 320), ("asset_key", 160)):
        if name in item:
            _text(item[name], label + "." + name, limit, empty=name == "asset_query")
    if "ground" in item and type(item["ground"]) is not bool:
        raise AssetCompileError(f"{label}.ground : booléen requis")
    if "style" in item and item["style"] not in {"energy", "lightning"}:
        raise AssetCompileError(f"{label}.style : energy ou lightning requis")


def _asset_key(selection):
    if isinstance(selection, str):
        return selection
    if isinstance(selection, dict):
        if isinstance(selection.get("key"), str):
            return selection["key"]
        if isinstance(selection.get("collection"), str) and isinstance(selection.get("id"), str):
            return selection["collection"] + ":" + selection["id"]
    raise AssetCompileError("Sélection : clé d'asset du catalogue requise")


def _resolve(selection, by_key, block):
    if selection is None:
        return None
    key = _asset_key(selection)
    asset = by_key.get(key)
    if asset is None:
        raise AssetCompileError("Asset absent du catalogue utilisé pour cette génération : " + key)
    wanted = "meshes" if block == "mesh" else "beams" if block in {"arc", "swipe"} else "textures"
    if asset.get("collection") != wanted:
        raise AssetCompileError(f"La brique {block} exige un asset de la collection {wanted}")
    return asset


def _texture_layer(piece, block, asset, warnings):
    if asset is None:
        warnings.append(f"{block} : aucun asset sélectionné ; texture de brique historique conservée.")
        return []
    uri = _uri(asset.get("uri"))
    if block in {"arc", "swipe"}:
        targets = [node for node in piece["nodes"] if node["class"] in {"Beam", "Trail"}]
    else:
        suffix = PRIMARY_SUFFIXES.get(block)
        targets = [node for node in piece["nodes"] if node["class"] == "ParticleEmitter" and node["id"].endswith("_" + suffix)]
        if not targets:
            raise AssetCompileError("Émetteur principal absent de la brique " + block)
    for node in targets:
        props = node["properties"]
        props["Texture"] = uri
        if node["class"] == "ParticleEmitter":
            # Replacing an animated flame with a static image must not retain
            # the former atlas settings. Unknown layouts are not guessed.
            flipbook = asset.get("flipbook") or {}
            grid = flipbook.get("grid", 0)
            if type(grid) is int and grid in (2, 4, 8):
                props["FlipbookLayout"] = f"Grid{grid}x{grid}"
                props["FlipbookMode"] = "OneShot"
                props["FlipbookStartRandom"] = False
                props["FlipbookBlendFrames"] = True
                props.pop("FlipbookSizeX", None); props.pop("FlipbookSizeY", None)
                if flipbook.get("estimated"):
                    warnings.append(f"{asset.get('name') or asset.get('id')} : grille flipbook {grid}×{grid} estimée, à vérifier.")
            else:
                props["FlipbookLayout"] = "None"
                for key in ("FlipbookMode", "FlipbookSizeX", "FlipbookSizeY", "FlipbookStartRandom", "FlipbookFramerate", "FlipbookBlendFrames"):
                    props.pop(key, None)
                if asset.get("kind") == "flipbook":
                    warnings.append(f"{asset.get('name') or asset.get('id')} : grille flipbook inconnue ; atlas affiché comme image fixe.")
    return [node["id"] for node in targets]


def _keyframes(points):
    # Gate keys can share t=0. Merge them intentionally before strict schema
    # validation, preserving the final value at each exact timestamp.
    unique = {round(float(t), 6): deepcopy(value) for t, value in points}
    return [{"time": t, "value": unique[t]} for t in sorted(unique)]


def _mesh_layer(item, asset, root, warnings):
    if asset is None:
        raise AssetCompileError("La couche mesh exige un maillage du catalogue")
    at, duration = float(item["at"]), float(item.get("duration", .8))
    end = round(at + duration, 6)
    geometry = _catalogue().load_geometry(asset, root=root)
    uri = _uri(asset.get("mesh_id") or asset.get("uri"), empty=True)
    if not uri and geometry is None:
        raise AssetCompileError("Le maillage n'a ni MeshId Roblox ni géométrie locale disponible")
    if geometry is not None:
        default_size = [max(.001, value) for value in geometry["source"]["dimensions"]]
    else:
        default_size = [4, 4, 4]
        warnings.append(f"{asset.get('name') or asset.get('id')} : MeshId lié, mais géométrie absente en local ; aperçu filaire, rendu final à vérifier dans Studio.")
    scale = float(item.get("scale", 1))
    raw_size = [value * scale for value in item.get("size", default_size)]
    raw_expanded = [value * float(item.get("expand", 1.5)) for value in raw_size]
    if any(value > 2048 for value in raw_size + raw_expanded):
        raise AssetCompileError("MeshPart.Size : l'échelle ou l'expansion dépasse les limites Roblox")
    size = [max(.001, value) for value in raw_size]
    expanded = [max(.001, value) for value in raw_expanded]
    if size != raw_size or expanded != raw_expanded:
        warnings.append(f"{asset.get('name') or asset.get('id')} : les axes très fins conservent la taille Roblox minimale de 0,001 stud.")
    position = deepcopy(item.get("position", [0, 1, 0]))
    orientation = deepcopy(item.get("orientation", [0, 0, 0]))
    spin = item.get("spin", [0, 0, 0])
    transparency = float(item.get("transparency", 0))
    props = {"MeshId": uri, "Size": size, "Position": position, "Orientation": orientation,
             "Color": deepcopy(item["color"]), "Transparency": 1 if at else transparency,
             "Material": "Neon", "Anchored": True, "CanCollide": False, "CanTouch": False,
             "CanQuery": False, "CastShadow": False, "DoubleSided": True}
    texture = asset.get("mesh_texture_id")
    props["TextureID"] = ""
    if texture:
        props["TextureID"] = _uri(texture)
    points = [(0, 1)] if at else []
    if at:
        points += [(max(0, at - .000001), 1)]
    points += [(at, transparency), (at + duration * .65, transparency), (end, 1)]
    animations = [
        {"node": "mesh", "property": "Transparency", "runtime": True, "keyframes": _keyframes(points)},
        {"node": "mesh", "property": "Size", "keyframes": _keyframes([(0, size), (at, size), (end, expanded)])},
        {"node": "mesh", "property": "Orientation", "keyframes": _keyframes([
            (0, orientation), (at, orientation), (end, [orientation[i] + spin[i] * duration for i in range(3)])])},
    ]
    if "end_position" in item:
        animations.append({"node": "mesh", "property": "Position", "runtime": True,
                           "keyframes": _keyframes([(0, position), (at, position), (end, item["end_position"])])})
    piece = {"version": 1, "name": str(item.get("name") or asset.get("name") or "Mesh"),
             "duration": round(end + .1, 6), "nodes": [{"id": "mesh", "class": "MeshPart", "name": str(item.get("name") or asset.get("name") or "Mesh"),
                                                       "parent": None, "properties": props}], "animations": animations}
    if geometry is not None:
        piece["editor"] = {"version": 1, "meshes": {"mesh": deepcopy(geometry)}}
        if not uri:
            warnings.append(f"{asset.get('name') or asset.get('id')} : aperçu OBJ local ; export natif en attente de son MeshId Roblox.")
    return validate_project(piece), ["mesh"]


def compile_plan(plan, selected_assets, *, snapshot=None, root=None):
    """Return a validated project and explicit per-layer asset bindings.

    ``selected_assets`` is a list, one entry per block: catalogue key, a record
    carrying that key, or None. Records are resolved again from the supplied
    immutable generation snapshot, so model-supplied URIs/paths are ignored.
    ``asset_query`` is retrieval intent only and is never an engine property.
    """
    if not isinstance(plan, dict) or set(plan) - {"name", "blocks"} or not {"name", "blocks"} <= plan.keys():
        raise AssetCompileError("Plan : name et blocks requis")
    name = _text(plan["name"], "name", 120)
    layers = plan["blocks"]
    if not isinstance(layers, list) or not 1 <= len(layers) <= 16:
        raise AssetCompileError("Plan : 1 à 16 couches requises")
    if not isinstance(selected_assets, list) or len(selected_assets) != len(layers):
        raise AssetCompileError("Une sélection d'asset par couche est requise")
    if snapshot is None:
        snapshot = _catalogue().snapshot(root=root)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("assets"), list):
        raise AssetCompileError("Snapshot catalogue invalide")
    by_key = {a["key"]: a for a in snapshot["assets"] if isinstance(a, dict) and isinstance(a.get("key"), str)}
    for asset in snapshot["assets"]:
        for alias in asset.get("key_aliases", []):
            by_key.setdefault(alias, asset)
    project = {"version": 1, "name": name, "duration": .1, "loop": False, "nodes": [], "animations": [],
               "camera": {"position": [10, 6, 12], "target": [0, 1.5, 0]}, "environment": {"background": "#191522"}}
    bindings, warnings = [], []
    for index, (item, selected) in enumerate(zip(layers, selected_assets)):
        _validate_layer(item, index)
        block = item["block"]
        if item.get("asset_key"):
            explicit = _resolve(item["asset_key"], by_key, block)
            if selected is None:
                selected = explicit
            elif _resolve(selected, by_key, block)["key"] != explicit["key"]:
                raise AssetCompileError(f"blocks[{index}] : sélection différente de l'asset_key explicite")
        asset = _resolve(selected, by_key, block)
        if block == "mesh":
            piece, node_ids = _mesh_layer(item, asset, root, warnings)
        else:
            params = {key: deepcopy(value) for key, value in item.items() if key not in {"asset_key", "asset_query"}}
            piece = compose({"name": name, "blocks": [params]})
            node_ids = _texture_layer(piece, block, asset, warnings)
            # These are newly generated AI layers, so author-intended support
            # motion must also run in the multi-instance native kit. In
            # particular a swipe's Trail needs its moving Part in Roblox.
            classes = {node["id"]: node["class"] for node in piece["nodes"]}
            for track in piece["animations"]:
                if classes[track["node"]] in {"Part", "MeshPart"} and track["property"] in {"Position", "Transparency"}:
                    track["runtime"] = True
            piece = validate_project(piece)
        prefix = f"ai{index + 1}_"
        project = merge_recipes(project, piece, prefix)
        bindings.append({"block_index": index, "block": block, "asset_key": asset.get("key") if asset else None,
                         "collection": asset.get("collection") if asset else None, "asset_id": asset.get("id") if asset else None,
                         "uri": asset.get("mesh_id") or asset.get("uri") if asset else None,
                         "name": asset.get("name", "") if asset else "", "nodes": [prefix + node for node in node_ids],
                         "preview": "geometry" if block == "mesh" and piece.get("editor", {}).get("meshes") else "placeholder" if block == "mesh" else "texture",
                         "selection": "catalogue" if asset else "legacy_default"})
    return {"project": validate_project(project), "bindings": bindings, "warnings": list(dict.fromkeys(warnings))}
