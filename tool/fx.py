"""Dataky FX Studio · ligne de commande pour créer des effets avec une IA.

    python tool/fx.py textures --tag Slash --kind flipbook      planche des textures + IDs
    python tool/fx.py blocks                                    briques disponibles
    python tool/fx.py compose plan.json --out recette.json      briques → recette
    python tool/fx.py render recette.json [autre.json…]         planche de rendu (comparaison si plusieurs)
    python tool/fx.py validate recette.json                     vérifie la recette
    python tool/fx.py save recette.json                         enregistre dans l’atelier
    python tool/fx.py export recette.json --format rbxmx        modèle à glisser dans Studio

Une recette peut être un fichier JSON ou l’ID d’un projet enregistré. Les images
sont écrites dans rendus/ et les exports dans exports/ (chemins affichés en sortie).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx_modules  # noqa: E402
import fx_tools  # noqa: E402
from fx_schema import ValidationError  # noqa: E402


def read_project(source: str) -> dict:
    path = Path(source)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    if path.suffix == ".json" or "/" in source or "\\" in source:
        raise fx_tools.ToolError(f"fichier introuvable : {source}")
    return fx_tools.load(source)


def show(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fx.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    textures = commands.add_parser("textures", help="chercher des textures, beams ou meshes et produire leur planche")
    textures.add_argument("--collection", default="textures", choices=["textures", "beams", "meshes"])
    textures.add_argument("--tag")
    textures.add_argument("--kind", choices=["static", "flipbook", "mesh"])
    textures.add_argument("--query", help="mots du nom, ou ID exact")
    textures.add_argument("--limit", type=int, default=24)
    textures.add_argument("--offset", type=int, default=0)
    textures.add_argument("--out", help="planche PNG (défaut : rendus/textures-….png)")
    textures.add_argument("--no-sheet", action="store_true", help="liste seulement, sans image")

    tags = commands.add_parser("tags", help="tags d’une collection et leur nombre d’assets")
    tags.add_argument("--collection", default="textures", choices=["textures", "beams", "meshes"])

    commands.add_parser("blocks", help="briques réutilisables et leurs réglages")

    compose = commands.add_parser("compose", help="assembler des briques en recette")
    compose.add_argument("plan", help="plan JSON : {\"name\", \"blocks\": [{\"block\": \"flash\", \"at\": 0}, …]}")
    compose.add_argument("--base", help="recette ou ID à laquelle ajouter les briques")
    compose.add_argument("--out", help="recette produite (défaut : affichée)")

    validate = commands.add_parser("validate", help="valider une recette")
    validate.add_argument("project")

    render = commands.add_parser("render", help="planche de rendu ; plusieurs recettes = une ligne chacune")
    render.add_argument("projects", nargs="+")
    render.add_argument("--out")
    render.add_argument("--times", help="instants en secondes : 0,0.1,0.3")
    render.add_argument("--frames", type=int, default=8)
    render.add_argument("--columns", type=int, default=4)
    render.add_argument("--size", default="480x270")
    render.add_argument("--camera", help="px,py,pz,tx,ty,tz (désactive le cadrage automatique)")
    render.add_argument("--no-auto-camera", action="store_true", help="garder la caméra du projet")
    render.add_argument("--no-dummy", action="store_true", help="sans mannequin d’échelle")
    render.add_argument("--background", choices=["sombre", "gris", "ciel", "noir"])
    render.add_argument("--no-ground", action="store_true")
    render.add_argument("--seed", type=int, default=1)

    save = commands.add_parser("save", help="enregistrer dans editor/projects (visible dans l’atelier)")
    save.add_argument("project")

    export = commands.add_parser("export", help="exporter : rbxmx (glisser dans Studio), lua (ModuleScript) ou json")
    export.add_argument("project")
    export.add_argument("--format", default="rbxmx", choices=["rbxmx", "lua", "json"])
    export.add_argument("--out")

    commands.add_parser("projects", help="projets enregistrés")
    args = parser.parse_args(argv)

    try:
        if args.command == "textures":
            result = fx_tools.search_assets(args.collection, args.tag, args.kind, args.query, args.limit, args.offset)
            if result["items"] and not args.no_sheet:
                name = "-".join(filter(None, [args.collection, args.tag, args.kind, args.query])) or args.collection
                result["sheet"] = str(fx_tools.texture_sheet(result["items"], args.out or f"rendus/{fx_tools._slug(name)}.png"))
            show(result)
        elif args.command == "tags":
            show(fx_tools.tags(args.collection))
        elif args.command == "blocks":
            show(fx_modules.list_blocks())
        elif args.command == "compose":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
            project = fx_modules.compose(plan, read_project(args.base) if args.base else None)
            if args.out:
                Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(args.out)
            else:
                show(project)
        elif args.command == "validate":
            project = fx_tools.validate(read_project(args.project))
            print(f"Recette valide : {project['name']} · {len(project['nodes'])} objets · {project['duration']} s")
        elif args.command == "render":
            times = [float(t) for t in args.times.split(",")] if args.times else None
            camera = [float(v) for v in args.camera.split(",")] if args.camera else None
            show(fx_tools.render([read_project(p) for p in args.projects], args.out, times, args.frames, args.size,
                                 auto_camera=not args.no_auto_camera, dummy=not args.no_dummy, background=args.background,
                                 ground=not args.no_ground, seed=args.seed, camera=camera, columns=args.columns))
        elif args.command == "save":
            show(fx_tools.save(read_project(args.project)))
        elif args.command == "export":
            print(fx_tools.export(read_project(args.project), args.format, args.out))
        elif args.command == "projects":
            show(fx_tools.list_projects())
    except (ValidationError, fx_tools.ToolError, ValueError, OSError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
