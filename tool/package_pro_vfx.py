"""Assemble the three finished effects using Dataky's existing exporters.

    python -m tool.package_pro_vfx --check
    python -m tool.package_pro_vfx

--check validates and compiles in memory without writing any delivery folder.
The normal command reads the saved recipes; it never runs their generators or
captures a new revision. Run it after the final PhantomBloom review. No Studio,
network upload, zip archive or modification of the source effects is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import xml.etree.ElementTree as ET

if __package__:
    from .fx_schema import validate_project
    from .fx_artistry import create_plan
    from .fx_export import export_library, library_textures, KIT_PATH, RUNTIME_PATH
    from .fx_rbxmx import export_rbxmx
else:
    from fx_schema import validate_project
    from fx_artistry import create_plan
    from fx_export import export_library, library_textures, KIT_PATH, RUNTIME_PATH
    from fx_rbxmx import export_rbxmx

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("CelestialRiftSlash", "SolarSpear", "PhantomBloom")
DEFAULT_OUTPUT = ROOT / "livrables" / "ProfessionalVFX"
GENERATOR = "tool/package_pro_vfx.py"


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def png_bytes(path, folder):
    path = path.resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError("Capture outside its effect folder: " + str(path))
    blob = path.read_bytes()
    if len(blob) < 24 or blob[:8] != b"\x89PNG\r\n\x1a\n" or not all(struct.unpack(">II", blob[16:24])):
        raise ValueError("Invalid PNG capture: " + str(path))
    return blob


def capture_manifest(name, project):
    """Select only a completed render whose embedded recipe matches this source."""
    folder = ROOT / "rendus" / "pro" / name
    candidates = sorted(folder.glob("manifest*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    for path in candidates:
        manifest = read_json(path)
        jobs = manifest.get("jobs", [])
        if manifest.get("effect") != name or not jobs:
            continue
        if not all(job.get("projects") and validate_project(job["projects"][-1]) == project for job in jobs):
            continue
        rendered = manifest.get("renders", {})
        results = rendered.get("jobs", [])
        if len(results) != len(jobs):
            continue
        times = {round(time, 6) for result in results for time in result.get("times", [])
                 if isinstance(time, (int, float)) and not isinstance(time, bool) and math.isfinite(time)
                 and 0 <= time <= project["duration"] + 1e-6}
        if len(times) < 5:
            continue
        copies, views = {}, []
        for job, result in zip(jobs, results):
            source = Path(job["out"]).resolve()
            files = {Path(file).resolve() for file in result.get("files", [])}
            if source not in files:
                raise ValueError("Renderer has no result for " + str(source))
            kind = next((label for label in ("hero", "tower", "peak") if source.stem.startswith(label + "-")), None)
            if kind is None:
                raise ValueError("Unknown capture role: " + str(source))
            destination = "previews/" + name + "/" + kind + ".png"
            if destination in copies:
                raise ValueError("Duplicate capture role: " + kind)
            copies[destination] = png_bytes(source, folder)
            view = {"role": kind, "file": destination, "source": relative(source),
                    "times": result.get("times", []), "camera": result.get("camera"),
                    "backgrounds": job.get("backgrounds", [job.get("background", "dark")])}
            if kind in ("hero", "tower"):
                frames_dir = Path(job["framesDir"]).resolve()
                if not frames_dir.is_relative_to(folder.resolve()):
                    raise ValueError("Frame directory outside its effect folder: " + str(frames_dir))
                frames = sorted(files - {source})
                expected = len(result["times"]) * len(view["backgrounds"])
                if len(frames) != expected or expected != 12:
                    raise ValueError(name + " requires twelve individual " + kind + " captures (six times, two backgrounds)")
                view["frames"] = []
                for frame in frames:
                    if frame.parent != frames_dir:
                        raise ValueError("Unexpected frame directory: " + str(frame))
                    target = "previews/" + name + "/" + frames_dir.name + "/" + frame.name
                    copies[target] = png_bytes(frame, folder)
                    view["frames"].append({"file": target, "source": relative(frame)})
            views.append(view)
        if not all(any(view["role"] == role for view in views) for role in ("hero", "tower")):
            raise ValueError(name + " requires both hero and tower captures")
        return path, manifest, copies, views
    raise ValueError(name + ": no completed capture manifest matches the current saved recipe; render the final revision first")


README = """# ProfessionalVFX — Dataky FX Studio

Trois effets éditables : CelestialRiftSlash, SolarSpear et PhantomBloom.

- `recipes/` : recettes JSON version 1, réouvrables dans Dataky.
- `roblox/` : trois modèles `.rbxmx`, une bibliothèque de données
  `ProfessionalVFX.lua`, le lecteur `DatakyFXKit.lua` et un exemple client.
- `plans/` : direction artistique, six phases et rôle de chaque couche.
- `previews/` : planches hero, tower et peak, douze captures individuelles hero
  et douze captures tower par effet, du rendu correspondant à la recette.
  `preview.webm` et l'analyse visuelle `review.md` y sont ajoutés lorsqu'ils
  existent dans le dossier de rendu source.
- `manifest.json` : provenance des sources, révisions capturées et SHA-256 de
  chaque fichier livré. Le manifeste ne s'inclut pas dans sa propre empreinte.

## Jouer dans un jeu

Créer deux ModuleScripts voisins dans ReplicatedStorage : `ProfessionalVFX` et
`DatakyFXKit`, puis y coller les deux sources Lua correspondantes.
`roblox/Example.client.luau` donne un LocalScript minimal à placer dans
StarterPlayerScripts. `FX.preloadTextures(Recipes)` peut suspendre l'exécution ;
le préparer au chargement. `FX.play` crée des handles indépendants, avec
`Move`, `Release`, `Stop` et `onFinished`.

Les textures restent référencées par leurs IDs Roblox existants. Ce dossier ne
les republie pas et ne modifie pas leurs permissions. `assets.json` répertorie
les URI réellement présentes dans les recettes.

## Importer un modèle éditable

Glisser un `.rbxmx` dans Studio. Les objets restent éditables ; le ModuleScript
`DatakyFX` joue la timeline sur ces objets :

```luau
local fx = require(workspace.CelestialRiftSlash.DatakyFX)
fx.play()
-- fx.pause(), fx.resume(), fx.stop()
```

Le lecteur `.rbxmx` conserve le déplacement par translation de son pivot.
Pour plusieurs instances et la rotation de l'effet, utiliser la bibliothèque
et le kit. Le kit actuel met à l'échelle les positions des supports et attaches,
les tailles de particules et les portées de lumières ; les largeurs et courbures
des Beams ne sont pas multipliées par `options.scale`. L'exemple utilise scale=1.

Les aperçus proviennent de l'émulateur Dataky. L'assemblage vérifie schéma,
références XML, correspondance des captures et intégrité des fichiers. Il
n'exécute pas Roblox Studio et ne certifie pas un rendu natif ni une note
esthétique. Les vérifications runtime séparées se lancent depuis le dépôt :

```powershell
python -m unittest tool.test_pro_vfx -v
```

Pour reconstruire le dossier après une révision finale depuis le dépôt source :

```powershell
python -m tool.package_pro_vfx --check
python -m tool.package_pro_vfx
```

Les recettes et captures enregistrées sont les sources de l'assemblage ; aucun
générateur artistique n'est relancé. Le script peut remplacer ses propres
fichiers livrés, et refuse un dossier contenant des fichiers non répertoriés.
"""

EXAMPLE = """--!strict
-- LocalScript in StarterPlayerScripts. Install both ModuleScripts first.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local FX = require(ReplicatedStorage:WaitForChild("DatakyFXKit"))
local Recipes = require(ReplicatedStorage:WaitForChild("ProfessionalVFX"))

FX.preloadTextures(Recipes)
for _, recipe in pairs(Recipes) do
    FX.preload(recipe)
    FX.prepare(recipe)
end

-- Change the selected key to SolarSpear or PhantomBloom.
local handle = FX.play(Recipes.CelestialRiftSlash, CFrame.new(0, 0, 0), {
    scale = 1,
    quality = "High",
    parent = workspace,
})
-- handle:Move(otherCFrame)
-- handle:Release() -- stop emitters and let remaining particles expire
-- handle:Stop() -- destroy this handle immediately
"""


def prepare_package():
    """Compile all payloads before any output is written. No generator is invoked."""
    payload = {"README.md": README.encode("utf-8"), "roblox/Example.client.luau": EXAMPLE.encode("utf-8")}
    recipes, effects = {}, []
    snapshots = {KIT_PATH: KIT_PATH.read_bytes(), RUNTIME_PATH: RUNTIME_PATH.read_bytes()}
    for name in NAMES:
        source = ROOT / "editor" / "projects" / (name + ".json")
        snapshots[source] = source.read_bytes()
        project = validate_project(json.loads(snapshots[source].decode("utf-8-sig")))
        if project.get("id") != name or project["name"] != name or project["loop"]:
            raise ValueError("Expected named one-shot recipe: " + name)
        plan_path = ROOT / "editor" / "artistry" / "plans" / (name + ".json")
        snapshots[plan_path] = plan_path.read_bytes()
        plan = json.loads(snapshots[plan_path].decode("utf-8-sig"))
        checked_plan = create_plan(project, {**plan["brief"], "phases": plan["phases"],
                                            "layers": plan["layers"], "budget": plan["budget"]})
        assigned = {ident for layer in checked_plan["layers"] for ident in layer["nodes"]}
        if assigned != {node["id"] for node in project["nodes"]}:
            raise ValueError("Incomplete layer bindings in " + name)
        xml = export_rbxmx(project)
        root = ET.fromstring(xml)
        items = list(root.iter("Item"))
        refs = {item.get("referent"): item for item in items}
        if len(refs) != len(items):
            raise ValueError("Duplicate XML referent in " + name)
        for ref in root.iter("Ref"):
            if ref.text not in (None, "null", "nil") and (ref.text not in refs or refs[ref.text].get("class") != "Attachment"):
                raise ValueError("Unresolved XML attachment reference in " + name)
        manifest_path, capture, previews, views = capture_manifest(name, project)
        payload.update(previews)
        extras = []
        for filename in ("preview.webm", "review.md"):
            path = ROOT / "rendus" / "pro" / name / filename
            if path.is_file():
                before = path.stat()
                blob = path.read_bytes()
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Optional media changed during packaging: " + str(path))
                if filename.endswith(".webm") and (len(blob) < 32 or blob[:4] != b"\x1aE\xdf\xa3"):
                    raise ValueError("Invalid or unfinished WebM: " + str(path))
                target = "previews/" + name + "/" + filename
                payload[target] = blob
                snapshots[path] = blob
                extras.append({"file": target, "source": relative(path), "sha256": digest(blob)})
        payload["recipes/" + name + ".json"] = json_bytes(project)
        payload["roblox/" + name + ".rbxmx"] = xml.encode("utf-8")
        payload["plans/" + name + ".json"] = json_bytes(plan)
        effects.append({"name": name, "duration_seconds": project["duration"], "nodes": len(project["nodes"]),
                        "tracks": len(project["animations"]), "recipe_sha256": digest(json_bytes(project)),
                        "source": relative(source), "source_sha256": digest(snapshots[source]),
                        "capture_manifest": relative(manifest_path), "capture_stage": capture.get("stage"),
                        "views": views, "optional_media": extras})
        recipes[name] = project
    payload["roblox/ProfessionalVFX.lua"] = export_library(recipes).encode("utf-8")
    payload["roblox/DatakyFXKit.lua"] = snapshots[KIT_PATH].decode("utf-8-sig").encode("utf-8")
    payload["assets.json"] = json_bytes({"version": 1, "textures": library_textures(recipes),
                                         "by_effect": {name: library_textures({name: recipe}) for name, recipe in recipes.items()}})
    # Detect source edits racing the packaging pass; never silently combine revisions.
    if any(path.read_bytes() != blob for path, blob in snapshots.items()):
        raise ValueError("Sources changed during assembly; rerun after the final revision is saved")
    manifest = {"version": 1, "generator": GENERATOR, "effects": effects,
                "runtime_sources": {relative(path): digest(blob) for path, blob in snapshots.items()
                                    if path in (KIT_PATH, RUNTIME_PATH)},
                "checks": {"schema": True, "xml_references": True, "matching_completed_captures": True,
                           "studio_executed_by_packager": False, "runtime_tests_executed_by_packager": False},
                "files": {name: {"bytes": len(blob), "sha256": digest(blob)} for name, blob in sorted(payload.items())}}
    payload["manifest.json"] = json_bytes(manifest)
    return payload, manifest


def write_package(output, payload):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        previous_path = output / "manifest.json"
        if not previous_path.is_file() or read_json(previous_path).get("generator") != GENERATOR:
            raise ValueError("Output folder contains unrelated files; choose a new --out directory")
        existing = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        if existing != set(payload):
            raise ValueError("Output file set differs from this package; choose a new --out directory")
    output.mkdir(parents=True, exist_ok=True)
    # Manifest is committed last; its checksums expose an interrupted prior write.
    for name, blob in sorted(payload.items(), key=lambda item: (item[0] == "manifest.json", item[0])):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(blob)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    for name, blob in payload.items():
        if (output / name).read_bytes() != blob:
            raise ValueError("Written package verification failed: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate all sources and exports in memory; write nothing")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Destination folder (default: livrables/ProfessionalVFX)")
    args = parser.parse_args()
    payload, manifest = prepare_package()
    if not args.check:
        write_package(args.out, payload)
    print(json.dumps({"mode": "check_only" if args.check else "assembled", "output": str(args.out.resolve()),
                      "files": len(payload), "bytes": sum(len(blob) for blob in payload.values()),
                      "effects": [{"name": effect["name"], "stage": effect["capture_stage"],
                                   "nodes": effect["nodes"], "tracks": effect["tracks"]} for effect in manifest["effects"]]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
