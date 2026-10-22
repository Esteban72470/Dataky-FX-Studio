"""Dataky FX Studio · briques d’effets réutilisables.

Chaque brique produit des objets Roblox natifs (Parts, Attachments, ParticleEmitter,
Beam, Trail, lumières) à partir de quelques réglages : instant, position, échelle,
couleurs, intensité. Un plan assemble plusieurs briques en une recette validée :

    {"name": "Explosion de glace", "blocks": [
        {"block": "flash", "at": 0, "color": [0.6, 0.9, 1]},
        {"block": "sparks", "at": 0, "color": [0.7, 0.95, 1], "intensity": 1.5},
        {"block": "shockwave", "at": 0.05, "scale": 1.5}]}

Les textures viennent de la bibliothèque locale ; elles ont été choisies sur les
planches de tool/fx.py textures. Le résultat reste une recette ordinaire, modifiable
dans l’atelier.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable

if __package__:
    from .fx_schema import ValidationError, validate_project
else:
    from fx_schema import ValidationError, validate_project

# Textures de la bibliothèque (IDs vérifiés sur les planches de textures).
GLOW = "rbxassetid://107251295851688"      # Basic Glowing Spec : disque blanc doux
GLARE = "rbxassetid://87561602489912"      # Bright Glare 1 : étoile de lumière
RING = "rbxassetid://15268066299"          # 2 layers thick ring : anneau lumineux
SMOKE = "rbxassetid://8779210242"          # blurry smoke : bouffée douce
CRESCENT = "rbxassetid://14242056438"      # Basic : croissant épais
CRESCENT_SOFT = "rbxassetid://15728405620" # Blur 2 : croissant flou
FLAME = "rbxassetid://92411870095278"      # Candle Flame : flipbook 4×4 blanc
ENERGY_BEAM = "rbxassetid://16892366666"   # Beam1 : faisceau d’énergie étoilé
LIGHTNING_BEAM = "rbxassetid://118741503383946"  # Beam115 : éclair en zigzag

DEFAULTS = {"at": 0.0, "position": [0, 1, 0], "scale": 1.0, "intensity": 1.0}


def seq(*points: tuple) -> list[dict[str, float]]:
    return [{"time": p[0], "value": p[1], "envelope": p[2] if len(p) > 2 else 0} for p in points]


def colors(first: list[float], last: list[float] | None = None) -> list[dict[str, Any]]:
    return [{"time": 0, "value": first}, {"time": 1, "value": last or first}]


def _color(value: Any, fallback: list[float]) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        return fallback
    return [min(1.0, max(0.0, float(v))) for v in value]


def _vec(value: Any, fallback: list[float]) -> list[float]:
    return [float(v) for v in value] if isinstance(value, list) and len(value) == 3 else list(fallback)


def _r(value: float) -> float:
    return round(value, 4)


class Block:
    """Collecte les objets d’une brique avec des identifiants préfixés uniques."""

    def __init__(self, prefix: str, title: str, params: dict[str, Any]):
        self.prefix, self.title, self.params = prefix, title, params
        self.nodes: list[dict[str, Any]] = []
        self.animations: list[dict[str, Any]] = []
        self.end = params["at"]

    def node(self, suffix: str, cls: str, name: str, parent: str | None, properties: dict[str, Any], timing: dict | None = None) -> str:
        ident = self.prefix + suffix
        node = {"id": ident, "class": cls, "name": name, "parent": parent, "properties": properties}
        if timing:
            node["timing"] = timing
            self.end = max(self.end, timing["start"] + timing["duration"])
        self.nodes.append(node)
        return ident

    def anchor(self, size: list[float] | None = None, position: list[float] | None = None, suffix: str = "ancre", name: str | None = None) -> str:
        return self.node(suffix, "Part", name or self.title, None, {
            "Position": [_r(v) for v in (position or self.params["position"])], "Size": [_r(max(0.05, v)) for v in (size or [1, 1, 1])],
            "Transparency": 1, "Anchored": True, "CanCollide": False, "CanTouch": False, "CanQuery": False, "CastShadow": False})

    def point(self, parent: str, suffix: str = "point", position: list[float] | None = None, **properties: Any) -> str:
        return self.node(suffix, "Attachment", "Point", parent, {"Position": [_r(v) for v in (position or [0, 0, 0])], **properties})

    def burst(self, at: float, count: int) -> dict[str, Any]:
        return {"start": _r(at), "duration": 0.05, "mode": "burst", "count": max(1, min(10000, int(round(count))))}

    def window(self, at: float, duration: float) -> dict[str, Any]:
        return {"start": _r(at), "duration": _r(max(0.01, duration)), "mode": "continuous"}

    def emitter(self, suffix: str, name: str, parent: str, timing: dict[str, Any], lifetime: list[float], **properties: Any) -> str:
        self.end = max(self.end, timing["start"] + timing["duration"] + lifetime[1])
        base = {"Rate": 0, "Lifetime": [_r(lifetime[0]), _r(lifetime[1])], "LightInfluence": 0, "Speed": [0, 0], "SpreadAngle": [0, 0]}
        return self.node(suffix, "ParticleEmitter", name, parent, {**base, **properties}, timing)


def flash(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [1, 0.85, 0.6])
    root = b.anchor()
    at = b.point(root)
    b.emitter("coeur", "Flash · cœur", at, b.burst(p["at"], 1), [0.22, 0.22], Texture=GLOW, LightEmission=1,
              Brightness=_r(2 * p["intensity"]), Color=colors(color), ZOffset=1,
              Size=seq((0, 1.5 * s), (0.35, 6 * s), (1, 7 * s)), Transparency=seq((0, 0), (0.45, 0.35), (1, 1)))
    b.emitter("etoile", "Flash · étoile", at, b.burst(p["at"], 2), [0.18, 0.24], Texture=GLARE, LightEmission=1,
              Brightness=_r(2 * p["intensity"]), Color=colors([1, 1, 1], color), ZOffset=1.5, Rotation=[0, 360],
              Size=seq((0, 4 * s), (0.3, 10 * s), (1, 12 * s)), Transparency=seq((0, 0), (0.5, 0.4), (1, 1)))
    light = b.node("lumiere", "PointLight", "Flash · lumière", at, {"Brightness": _r(8 * p["intensity"]), "Range": _r(min(60, 14 * s)), "Color": color},
                   b.window(p["at"], 0.15))
    b.animations.append({"node": light, "property": "Brightness", "keyframes": [{"time": _r(p["at"]), "value": _r(8 * p["intensity"])}, {"time": _r(p["at"] + 0.15), "value": 0}]})


def sparks(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [1, 0.8, 0.45])
    root = b.anchor()
    at = b.point(root)
    b.emitter("etincelles", "Étincelles", at, b.burst(p["at"], 28 * p["intensity"]), [0.25, 0.55], Texture=GLOW, LightEmission=1,
              Brightness=_r(3 * p["intensity"]), Color=colors([1, 1, 1], _color(p.get("color2"), color)), Orientation="VelocityParallel",
              Speed=[_r(18 * s), _r(34 * s)], SpreadAngle=[180, 180], Drag=5, Acceleration=[0, _r(-25 * s), 0],
              Size=seq((0, 0.6 * s), (1, 0)), Squash=seq((0, -2.6), (1, -1.2)), Transparency=seq((0, 0), (0.7, 0.1), (1, 1)))


def shockwave(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [1, 0.9, 0.7])
    position = list(p["position"])
    if p.get("ground", True):
        position[1] = 0.15
    root = b.anchor(position=position)
    at = b.point(root)
    # VelocityPerpendicular avec une vitesse infime vers le haut : la particule reste à plat sur le sol.
    b.emitter("anneau", "Onde de choc", at, b.burst(p["at"], 1), [0.5, 0.5], Texture=RING, LightEmission=1, Brightness=_r(2 * p["intensity"]),
              Color=colors(color, _color(p.get("color2"), color)), Orientation="VelocityPerpendicular", Speed=[0.01, 0.01],
              Size=seq((0, 0.5 * s), (0.3, 9 * s), (1, 13 * s)), Transparency=seq((0, 0), (0.5, 0.25), (1, 1)))


def smoke(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.7, 0.7, 0.75])
    root = b.anchor(size=[2 * s, 1 * s, 2 * s])
    b.emitter("fumee", "Fumée", root, b.burst(p["at"], 10 * p["intensity"]), [1.2, 2], Texture=SMOKE, LightEmission=0,
              Color=colors(color, _color(p.get("color2"), [c * 0.6 for c in color])), Shape="Sphere", ShapeStyle="Surface",
              Speed=[_r(3 * s), _r(6 * s)], Drag=2.5, Acceleration=[0, _r(1.5 * s), 0], Rotation=[0, 360], RotSpeed=[-40, 40],
              Size=seq((0, 2 * s, 0.4 * s), (1, 5 * s, 0.8 * s)), Transparency=seq((0, 0.55), (0.15, 0.35), (1, 1)))


def slash(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.75, 0.9, 1])
    root = b.anchor()
    at = b.point(root)
    angle = float(p.get("angle", -20))
    common = dict(LightEmission=1, Rotation=[_r(angle), _r(angle)], RotSpeed=[-90, -90])
    b.emitter("croissant", "Slash", at, b.burst(p["at"], 1), [0.32, 0.32], Texture=CRESCENT, Brightness=_r(2 * p["intensity"]), Color=colors([1, 1, 1], color),
              Size=seq((0, 4 * s), (0.2, 9 * s), (1, 10.5 * s)), Transparency=seq((0, 0), (0.55, 0.1), (1, 1)), ZOffset=0.5, **common)
    b.emitter("halo", "Slash · halo", at, b.burst(p["at"] + 0.02, 1), [0.3, 0.3], Texture=CRESCENT_SOFT, Brightness=_r(1.5 * p["intensity"]), Color=colors(color),
              Size=seq((0, 5 * s), (0.25, 10 * s), (1, 12 * s)), Transparency=seq((0, 0.2), (0.5, 0.4), (1, 1)), **common)


def arc(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.55, 0.85, 1])
    start, end = _vec(p.get("start"), [-3 * s, 0, 0]), _vec(p.get("end"), [3 * s, 0, 0])
    d = [e - a for a, e in zip(start, end)]
    length = math.sqrt(sum(v * v for v in d)) or 1.0
    d = [v / length for v in d]
    up = [0.0, 1.0, 0.0] if abs(d[1]) < 0.95 else [1.0, 0.0, 0.0]
    bend = max(0.0, float(p.get("bend", 0.5)))
    theta = math.radians(60)
    # Les points de contrôle suivent +X d’Attachment0 et -X d’Attachment1 : on incline ces axes vers le haut.
    axis0 = [math.cos(theta) * dv + math.sin(theta) * uv for dv, uv in zip(d, up)]
    axis1 = [math.cos(theta) * dv - math.sin(theta) * uv for dv, uv in zip(d, up)]

    def secondary(axis: list[float]) -> list[float]:
        k = sum(a * u for a, u in zip(axis, up))
        v = [u - a * k for a, u in zip(axis, up)]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [_r(x / n) for x in v]

    root = b.anchor()
    a0 = b.point(root, "depart", start, Axis=[_r(v) for v in axis0], SecondaryAxis=secondary(axis0))
    a1 = b.point(root, "arrivee", end, Axis=[_r(v) for v in axis1], SecondaryAxis=secondary(axis1))
    lightning = p.get("style") == "lightning"
    duration = float(p.get("duration", 0.6))
    width = (1.2 if lightning else 1.8) * s
    b.node("faisceau", "Beam", "Éclair" if lightning else "Arc d’énergie", root, {
        "Attachment0": a0, "Attachment1": a1, "Texture": LIGHTNING_BEAM if lightning else ENERGY_BEAM, "LightEmission": 1,
        "Brightness": _r(2 * p["intensity"]), "Color": colors(color, _color(p.get("color2"), color)), "FaceCamera": True,
        "Segments": 30, "Width0": _r(width), "Width1": _r(width), "CurveSize0": _r(length * 0.5 * bend * 2), "CurveSize1": _r(length * 0.5 * bend * 2),
        "TextureSpeed": 3 if lightning else 1.5, "TextureLength": 1, "TextureMode": "Stretch",
        "Transparency": seq((0, 1), (0.12, 0), (0.88, 0), (1, 1))}, b.window(p["at"], duration))


def swipe(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.8, 0.9, 1])
    duration = float(p.get("duration", 0.3))
    radius = 3.5 * s
    center = _vec(p["position"], [0, 1, 0])
    root = b.anchor(size=[0.2, 0.2, 0.2], position=[center[0] - radius, center[1], center[2]])
    top = b.point(root, "haut", [0, 0.6 * s, 0])
    bottom = b.point(root, "bas", [0, -0.6 * s, 0])
    lifetime = 0.3
    b.node("trainee", "Trail", "Traînée", root, {
        "Attachment0": top, "Attachment1": bottom, "LightEmission": 1, "Brightness": _r(2 * p["intensity"]),
        "Color": colors([1, 1, 1], _color(p.get("color2"), color)), "Lifetime": lifetime, "MinLength": 0.05, "FaceCamera": False,
        "Transparency": seq((0, 0), (1, 1)), "WidthScale": seq((0, 1), (1, 0.25))}, b.window(p["at"], duration))
    frames = []
    for i in range(9):
        a = math.pi * i / 8
        t = p["at"] + duration * i / 8
        frames.append({"time": _r(t), "value": [_r(center[0] - radius * math.cos(a)), _r(center[1]), _r(center[2] - radius * math.sin(a))]})
    b.animations.append({"node": root, "property": "Position", "keyframes": frames})
    b.end = max(b.end, p["at"] + duration + lifetime)


def fire(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [1, 0.55, 0.15])
    root = b.anchor(size=[1.6 * s, 0.2, 1.6 * s])
    b.emitter("flammes", "Flammes", root, b.window(p["at"], float(p.get("duration", 2))), [0.6, 0.9], Texture=FLAME, LightEmission=1,
              Brightness=_r(1.5 * p["intensity"]), Rate=_r(14 * p["intensity"]), Shape="Disc", EmissionDirection="Top",
              Color=colors([1, 0.9, 0.55], _color(p.get("color2"), color)), Speed=[_r(2 * s), _r(4 * s)], SpreadAngle=[8, 8],
              FlipbookLayout="Grid4x4", FlipbookMode="OneShot", Rotation=[-10, 10],
              Size=seq((0, 1.6 * s), (0.6, 1.9 * s), (1, 0.8 * s)), Transparency=seq((0, 0.3), (0.2, 0.05), (0.75, 0.3), (1, 1)))


def charge(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.6, 0.8, 1])
    duration = float(p.get("duration", 0.8))
    root = b.anchor(size=[6 * s, 6 * s, 6 * s])
    b.emitter("aspiration", "Concentration", root, b.window(p["at"], duration), [0.42, 0.42], Texture=GLOW, LightEmission=1,
              Brightness=_r(2.5 * p["intensity"]), Rate=_r(70 * p["intensity"]), Shape="Sphere", ShapeStyle="Surface", ShapeInOut="Inward",
              Speed=[_r(7 * s), _r(7 * s)], Orientation="VelocityParallel", Color=colors(color, [1, 1, 1]),
              Size=seq((0, 0.15 * s), (0.5, 0.35 * s), (1, 0.2 * s)), Squash=seq((0, -2), (1, -2)), Transparency=seq((0, 1), (0.2, 0), (1, 0.2)))
    at = b.point(root)
    b.emitter("coeur", "Concentration · cœur", at, b.burst(p["at"], 1), [duration, duration], Texture=GLOW, LightEmission=1,
              Brightness=_r(2 * p["intensity"]), Color=colors(color, [1, 1, 1]),
              Size=seq((0, 0), (1, 2.6 * s)), Transparency=seq((0, 0.6), (1, 0)))


def orb(b: Block) -> None:
    p, s = b.params, b.params["scale"]
    color = _color(p.get("color"), [0.55, 0.8, 1])
    duration = float(p.get("duration", 1.5))
    root = b.anchor()
    at = b.point(root)
    window = b.window(p["at"], duration)
    b.emitter("halo", "Orbe · halo", at, window, [0.25, 0.35], Texture=GLOW, LightEmission=1, Brightness=_r(2 * p["intensity"]),
              Rate=_r(30 * p["intensity"]), LockedToPart=True, Color=colors(color),
              Size=seq((0, 2.6 * s, 0.3 * s), (1, 3.2 * s, 0.3 * s)), Transparency=seq((0, 0.55), (1, 1)))
    b.emitter("noyau", "Orbe · noyau", at, window, [0.15, 0.2], Texture=GLOW, LightEmission=1, Brightness=_r(3 * p["intensity"]),
              Rate=_r(30 * p["intensity"]), LockedToPart=True, Color=colors([1, 1, 1]), ZOffset=0.5,
              Size=seq((0, 1.1 * s), (1, 1.3 * s)), Transparency=seq((0, 0.1), (1, 1)))
    b.node("lumiere", "PointLight", "Orbe · lumière", at, {"Brightness": _r(3 * p["intensity"]), "Range": _r(min(60, 10 * s)), "Color": color}, window)


BLOCKS: dict[str, dict[str, Any]] = {
    "flash": {"title": "Flash", "build": flash, "description": "Éclair lumineux bref : halo, étoile de lumière et PointLight qui s’éteint en 0,15 s.",
              "params": {"color": "couleur [r,g,b]", "intensity": "luminosité"}},
    "sparks": {"title": "Étincelles", "build": sparks, "description": "Gerbe d’étincelles étirées dans leur direction, freinées et retombantes.",
               "params": {"color": "couleur finale", "color2": "couleur de fin", "intensity": "nombre d’étincelles (×28)"}},
    "shockwave": {"title": "Onde de choc", "build": shockwave, "description": "Anneau à plat qui s’élargit (13 studs × scale) et s’efface en 0,5 s.",
                  "params": {"color": "couleur", "color2": "couleur de fin", "ground": "true : posé au sol (y = 0,15)"}},
    "smoke": {"title": "Fumée", "build": smoke, "description": "Bouffées de fumée qui s’écartent, montent et se dissipent en 1,2 à 2 s (mélange normal).",
              "params": {"color": "couleur", "color2": "couleur de fin", "intensity": "nombre de bouffées (×10)"}},
    "slash": {"title": "Slash", "build": slash, "description": "Croissant tranchant qui s’ouvre et tourne, avec un halo coloré.",
              "params": {"color": "couleur", "angle": "rotation de départ en degrés"}},
    "arc": {"title": "Arc", "build": arc, "description": "Beam courbé entre deux points : énergie (style energy) ou éclair (style lightning).",
            "params": {"start": "départ relatif [x,y,z]", "end": "arrivée relative [x,y,z]", "bend": "courbure (0 = droit)",
                       "style": "energy ou lightning", "duration": "durée en s", "color": "couleur", "color2": "couleur à l’arrivée"}},
    "swipe": {"title": "Traînée", "build": swipe, "description": "Trail porté par un support qui décrit un demi-cercle (coup d’épée, balayage).",
              "params": {"duration": "durée du geste en s", "color": "couleur", "color2": "couleur de fin"}},
    "fire": {"title": "Feu", "build": fire, "description": "Flammes continues animées (flipbook 4×4) qui montent d’un disque.",
             "params": {"duration": "durée en s", "color": "couleur des pointes", "color2": "couleur de fin", "intensity": "débit"}},
    "charge": {"title": "Concentration", "build": charge, "description": "Particules aspirées vers le centre et cœur lumineux qui grandit (chargement d’attaque).",
               "params": {"duration": "durée en s", "color": "couleur", "intensity": "débit"}},
    "orb": {"title": "Orbe", "build": orb, "description": "Boule d’énergie continue avec halo pulsé et lumière ; suit son support (projectile, aura).",
            "params": {"duration": "durée en s", "color": "couleur", "intensity": "luminosité et débit"}},
}
COMMON = {"block": "nom de la brique", "at": "instant de départ en s (défaut 0)", "position": "position [x,y,z] (défaut [0,1,0])",
          "scale": "échelle de la brique (défaut 1)", "intensity": "intensité (défaut 1)", "name": "nom affiché (facultatif)"}


def list_blocks() -> list[dict[str, Any]]:
    return [{"block": name, "title": spec["title"], "description": spec["description"], "params": {**COMMON, **spec["params"]}}
            for name, spec in BLOCKS.items()]


def _prefix(name: str, taken: set[str]) -> str:
    index = 1
    while any(ident.startswith(f"{name}{index}_") for ident in taken):
        index += 1
    return f"{name}{index}_"


def compose(plan: dict[str, Any], base: dict[str, Any] | None = None, *, include_loader=None) -> dict[str, Any]:
    """Assemble briques et inclusions en recette ; include_loader(name) est injectable.

    Une inclusion accepte include, at, position, orientation (YXZ), scale,
    prefix et positionKeys (translation animée relative, temps locaux à la pièce).
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("blocks"), list) or not plan["blocks"]:
        raise ValidationError("plan : liste blocks requise, par exemple [{\"block\": \"flash\"}]")
    if len(plan["blocks"]) > 40:
        raise ValidationError("plan : 40 briques maximum")
    if base is not None and not isinstance(base, dict):
        raise ValidationError("project : recette (objet JSON) requise")
    project = validate_project(base) if base else {"version": 1, "name": plan.get("name", "Effet composé"), "duration": 0.5, "loop": False,
                                           "nodes": [], "animations": [], "camera": {"position": [10, 6, 12], "target": [0, 1.5, 0]},
                                           "environment": {"background": "#191522"}}
    project.setdefault("nodes", []); project.setdefault("animations", [])
    taken = {node["id"] for node in project["nodes"]}
    end = 0.0
    for index, item in enumerate(plan["blocks"]):
        if isinstance(item, dict) and "include" in item:
            if "block" in item:
                raise ValidationError(f"blocks[{index}] : choisir block ou include")
            if __package__:
                from .fx_builder import load_recipe, merge_recipes
            else:
                from fx_builder import load_recipe, merge_recipes
            try:
                piece = (include_loader or load_recipe)(item["include"])
                project = merge_recipes(project, piece, item.get("prefix", _prefix("include", taken)),
                    at=item.get("at", 0), position=item.get("position", [0, 0, 0]),
                    orientation=item.get("orientation", [0, 0, 0]), scale=item.get("scale", 1),
                    position_keys=item.get("positionKeys"))
            except (TypeError, ValueError, OSError) as exc:
                raise ValidationError(f"blocks[{index}] (include) : {exc}") from exc
            taken.update(node["id"] for node in project["nodes"])
            end = max(end, project["duration"])
            continue
        if not isinstance(item, dict) or item.get("block") not in BLOCKS:
            raise ValidationError(f"blocks[{index}] : brique inconnue ; disponibles : {', '.join(BLOCKS)}")
        spec = BLOCKS[item["block"]]
        try:
            params = {**DEFAULTS, **item}
            params["at"] = max(0.0, float(params["at"]))
            params["scale"] = min(20.0, max(0.05, float(params["scale"])))
            params["intensity"] = min(10.0, max(0.05, float(params["intensity"])))
            params["position"] = _vec(params["position"], DEFAULTS["position"])
            block = Block(_prefix(item["block"], taken), str(item.get("name") or spec["title"]), params)
            spec["build"](block)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"blocks[{index}] ({item['block']}) : réglage invalide — {exc}") from exc
        taken.update(node["id"] for node in block.nodes)
        project["nodes"].extend(block.nodes)
        project["animations"].extend(block.animations)
        end = max(end, block.end)
    needed = math.ceil((end + 0.1) * 10) / 10
    project["duration"] = max(float(plan.get("duration") or 0), float(project.get("duration", 0.5)), needed)
    if "loop" in plan:
        project["loop"] = bool(plan["loop"])
    if plan.get("camera"):
        project["camera"] = plan["camera"]
    return validate_project(project)


Builder = Callable[[Block], None]
__all__ = ["BLOCKS", "compose", "list_blocks"]
