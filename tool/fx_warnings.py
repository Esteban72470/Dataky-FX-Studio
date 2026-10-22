"""Advisory Roblox authoring traps, separate from recipe validity.

Visibility is an equivalent opaque area in studs², averaged over normalized
particle life: integral(alpha * Size² * (1 - Transparency), life=0..1).
Thumbnail alpha is already linear coverage: a hard opaque pixel contributes 1,
an empty pixel 0, and a soft edge its alpha, without a second coverage penalty.
OneShot alpha follows the thumbnail's evenly spaced cells; other modes use the
mean cell alpha, since their playback phase is not known. Simpson integration
is exact for the cubic Size² * opacity on each linear-sequence/cell interval.
Envelopes, colour, backgrounds and native OneShot scheduling are not measured.
These estimates describe one particle, not aggregate emitter brightness.
"""
from __future__ import annotations

import re
import struct
import zlib

if __package__:
    from .fx_grid_overrides import read_grid_overrides
    from .fx_schema import CLASSES
    from .fx_texture_cache import texture_stats
else:
    from fx_grid_overrides import read_grid_overrides
    from fx_schema import CLASSES
    from fx_texture_cache import texture_stats


# All advisory thresholds live here. They are heuristic units, not guarantees
# about native rendering. In particular the empty-prefix rule is a separate
# short-OneShot timing risk, so even a large particle can trigger it.
THRESHOLDS = {
    "end_transparency": .95,         # below this, disappearance is still visible
    "end_size_studs": .05,          # minimum significant remaining size
    "end_size_peak_fraction": .05,  # or 5% of the maximum authored size
    "parallel_squash": .01,
    "additive_light_emission": .6,
    "additive_color_channel": .5,
    "additive_saturation": .5,
    "visible_area_studs2": .01,     # opaque equivalent of a 0.1 x 0.1 stud quad
    "empty_start_lifetime_seconds": .5,
    "empty_start_life_fraction": .25,
    "empty_start_alpha": .08,
    "dark_light_emission": .2,
    "dark_max_luminance": .15,
    "contrast_light_min_luminance": .45,
    "contrast_light_min_emission": .2,
    "contrast_min_opacity": .05,
    "contrast_min_size_studs": .05,
    "timing_epsilon_seconds": 1e-6,
}


def points(value):
    return [(p.get("time"), p.get("value")) if isinstance(p, dict) else (p[0], p[1]) for p in value]


def sample(value, time):
    keys = points(value)
    if time <= keys[0][0]:
        return keys[0][1]
    for (ta, a), (tb, b) in zip(keys, keys[1:]):
        if time < tb:
            return a + (b - a) * (time - ta) / (tb - ta)
    return keys[-1][1]


def visible_area(frames, size, transparency, *, one_shot=False):
    """Integrate equivalent opaque particle area, in studs², over life 0..1."""
    count = len(frames)
    breaks = {0., 1., *(t for t, _ in points(size)), *(t for t, _ in points(transparency))}
    if one_shot:
        breaks.update(i / count for i in range(1, count))
    breaks = sorted(breaks)
    mean_alpha = sum(frame["alpha_mean"] for frame in frames) / count

    def area(t):
        return sample(size, t) ** 2 * (1 - sample(transparency, t))

    result = 0.
    for a, b in zip(breaks, breaks[1:]):
        midpoint = (a + b) / 2
        alpha = frames[min(count - 1, int(midpoint * count))]["alpha_mean"] if one_shot else mean_alpha
        result += alpha * (b - a) * (area(a) + 4 * area(midpoint) + area(b)) / 6
    return result


def luminance(rgb):
    """Authored RGB luminance estimate, not a native lighting measurement."""
    return sum(a * b for a, b in zip(rgb, (.2126, .7152, .0722)))


def active_intervals(project, node):
    """Potential particle presence, including drain and authored Enabled tracks.

    Bursts emit once; continuous windows are split when Enabled changes. The
    longest Lifetime/TimeScale bounds presence. This is an advisory envelope,
    not a simulation of native alpha, spatial coverage, or randomized particles.
    """
    defaults = CLASSES["ParticleEmitter"]["properties"]
    get = lambda key: node["properties"].get(key, defaults[key]["default"])
    if not get("Enabled") or max(v for _, v in points(get("Size"))) <= THRESHOLDS["contrast_min_size_studs"]:
        return []
    if 1 - min(v for _, v in points(get("Transparency"))) < THRESHOLDS["contrast_min_opacity"]:
        return []
    timing = node.get("timing")
    start = timing["start"] if timing else 0
    end = start + timing["duration"] if timing else project["duration"]
    tracks = [track for track in project.get("animations", []) if track["node"] == node["id"] and track["property"] == "Enabled"]
    def enabled(t):
        for track in tracks:
            keys = track["keyframes"]
            value = keys[0]["value"]
            for key in keys:
                if key["time"] > t:
                    break
                value = key["value"]
            if not value:
                return False
        return True
    timescale = get("TimeScale")
    life = max(get("Lifetime")) / timescale if timescale > 0 else project["duration"] + max(get("Lifetime"))
    if timing and timing["mode"] == "burst":
        return [(start, start + life)] if timing["count"] > 0 and enabled(start) and life > 0 else []
    if get("Rate") <= 0 or end <= start:
        return []
    breaks = sorted({start, end, *(key["time"] for track in tracks for key in track["keyframes"] if start < key["time"] < end)})
    return [(a, b + life) for a, b in zip(breaks, breaks[1:]) if enabled(a)]


def covered_intervals(target, covering):
    """Require coverage of the whole potential presence, not a one-frame overlap."""
    epsilon = THRESHOLDS["timing_epsilon_seconds"]
    covering = sorted(covering)
    for start, end in target:
        cursor = start
        for a, b in covering:
            if a > cursor + epsilon:
                break
            if b > cursor:
                cursor = b
            if cursor >= end - epsilon:
                break
        if cursor < end - epsilon:
            return False
    return True


def validation_warnings(project, *, assets=None, stats_loader=texture_stats, include_infos=False, grid_overrides=None):
    if assets is None:
        if __package__:
            from .fx_tools import catalog
        else:
            from fx_tools import catalog
        assets = {str(item.get("asset_id")): item for item in catalog("textures")}
    warnings, estimated_textures = [], set()
    if grid_overrides is None:
        try:
            grid_overrides = read_grid_overrides()
        except (OSError, ValueError) as error:
            grid_overrides = {}
            if include_infos:
                warnings.append({"node": None, "code": "grid_overrides_unavailable", "level": "info",
                                 "message": "Surcharges de grille ignorées : " + str(error)})
    defaults = CLASSES["ParticleEmitter"]["properties"]
    emitters = [node for node in project["nodes"] if node["class"] == "ParticleEmitter"]
    light_layers = []
    for candidate in emitters:
        get = lambda key: candidate["properties"].get(key, defaults[key]["default"])
        if get("LightEmission") >= THRESHOLDS["contrast_light_min_emission"] and max(luminance(c) for _, c in points(get("Color"))) >= THRESHOLDS["contrast_light_min_luminance"]:
            light_layers.extend(active_intervals(project, candidate))
    for node in project["nodes"]:
        if node["class"] != "ParticleEmitter":
            continue
        props = node["properties"]
        get = lambda key: props.get(key, defaults[key]["default"])

        def warn(code, message, *, level="warning", **details):
            warnings.append({"node": node["id"], "code": code, "level": level, "message": message, **details})

        if get("Orientation") == "VelocityParallel" and any(v > THRESHOLDS["parallel_squash"] for _, v in points(get("Squash"))):
            warn("positive_parallel_squash", "VelocityParallel + Squash positif étire en travers de la vitesse. Pour une traînée utilisez un Squash négatif ; un trait vertical avec Rotation 90 peut être intentionnel.")
        if get("Orientation") == "VelocityPerpendicular" and get("EmissionDirection") == "Top" and get("ZOffset") < 0:
            warn("flat_layer_negative_zoffset", "Couche à plat vers Top avec ZOffset négatif : elle peut passer sous le sol. Vérifiez ZOffset=0 dans Studio.", zoffset=get("ZOffset"))
        max_luminance = max(luminance(c) for _, c in points(get("Color")))
        if get("LightEmission") < THRESHOLDS["dark_light_emission"] and max_luminance < THRESHOLDS["dark_max_luminance"]:
            active = active_intervals(project, node)
            if active and not covered_intervals(active, light_layers):
                warn("dark_ground_contrast", "Couche presque noire et peu émissive sans couche claire couvrant la même période : risque de disparition sur sol sombre. Comparez --backgrounds roblox,dark puis vérifiez dans Studio.", max_luminance=round(max_luminance, 6), active_intervals=active)
        transparency, size = get("Transparency"), get("Size")
        end_transparency, end_size = points(transparency)[-1][1], points(size)[-1][1]
        peak = max(v for _, v in points(size))
        remaining_size = end_size > max(THRESHOLDS["end_size_studs"], peak * THRESHOLDS["end_size_peak_fraction"])
        if end_transparency < THRESHOLDS["end_transparency"] and remaining_size:
            # A size warning has exactly the same final-opacity prerequisite.
            # Merge it into this diagnostic to report one end-of-life issue.
            details = {"end_transparency": end_transparency}
            message = "Transparency finit sous 0,95 : disparition brusque en fin de vie."
            if remaining_size:
                message += " Size reste non nulle : la particule a encore une taille visible."
                details.update(end_size=end_size, abrupt_size=True)
            warn("abrupt_transparency", message, **details)
        colors = [value for _, value in points(get("Color"))]
        if get("LightEmission") >= THRESHOLDS["additive_light_emission"] and any(max(c) >= THRESHOLDS["additive_color_channel"] and (max(c) - min(c)) / max(c) >= THRESHOLDS["additive_saturation"] for c in colors):
            warn("additive_white", "LightEmission >= 0,6 et couleur saturée : risque de saturation en blanc sur un ciel clair. Vérifiez le fond roblox.")
        match = re.search(r"(?:^|rbxassetid://)(\d+)$|[?&]id=(\d+)$", str(get("Texture")))
        if not match:
            continue
        asset_id = next(group for group in match.groups() if group)
        asset = assets.get(asset_id, {})
        layout = get("FlipbookLayout")
        grid = re.fullmatch(r"Grid(2|4|8)x\1", str(layout))
        columns = rows = int(grid.group(1)) if grid else 1
        if layout == "Custom":
            columns, rows = get("FlipbookSizeX"), get("FlipbookSizeY")
            if int(columns) == columns:
                columns = int(columns)
            if int(rows) == rows:
                rows = int(rows)
        is_flipbook = layout != "None"
        confirmed = grid_overrides.get(asset_id) == columns == rows
        if include_infos and is_flipbook and str(asset.get("grid_source", "")).startswith("inferred") and not confirmed and asset_id not in estimated_textures:
            estimated_textures.add(asset_id)
            warn("estimated_grid", "Grille de flipbook estimated : la grille déduite peut être fausse. Vérifiez les cases dans la planche.", level="info", texture=asset_id)
        try:
            stats = stats_loader(asset_id, columns, rows)
        except (OSError, ValueError, struct.error, zlib.error) as error:
            warn("texture_stats_unavailable", "Couverture alpha indisponible pour la miniature : " + str(error), texture=asset_id)
            continue
        if not stats:
            continue
        frames = stats["frames"]
        one_shot = is_flipbook and get("FlipbookMode") == "OneShot"
        area = visible_area(frames, size, transparency, one_shot=one_shot)
        if area <= THRESHOLDS["visible_area_studs2"]:
            code = "flipbook_low_opacity" if one_shot else "pale_small_texture"
            warn(code, "Surface visible moyenne estimée <= 0,01 stud² (alpha × Size² × opacité) : risque de faible lisibilité. Vérifiez dans Studio.", texture=asset_id, estimated_visible_area_studs2=round(area, 7))
        if one_shot:
            prefix = frames[:max(1, int(len(frames) * THRESHOLDS["empty_start_life_fraction"]))]
            if max(get("Lifetime")) <= THRESHOLDS["empty_start_lifetime_seconds"] and sum(f["alpha_mean"] for f in prefix) / len(prefix) < THRESHOLDS["empty_start_alpha"]:
                warn("flipbook_empty_start", "Premières cases du OneShot presque vides avec une Lifetime courte : risque d’invisibilité observé en Play. Augmentez la Lifetime ou choisissez une autre texture ; vérifier dans Studio.", texture=asset_id)
    return warnings
