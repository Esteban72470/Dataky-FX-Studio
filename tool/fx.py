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
from fx_builder import load_recipe  # noqa: E402


def read_project(source: str) -> dict:
    path = Path(source)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    if path.suffix == ".json" or "/" in source or "\\" in source:
        raise fx_tools.ToolError(f"fichier introuvable : {source}")
    return fx_tools.load(source)


def show(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def show_diagnostics(diagnostics: list[dict]) -> None:
    for level, label, summary in (("warning", "Avertissement", "Résumé avertissements"),
                                  ("info", "Info", "Résumé infos")):
        records = [item for item in diagnostics if item.get("level", "warning") == level]
        for code, count in fx_tools.diagnostic_counts(records).items():
            print(f"{summary} [{code}] : {count}")
        for item in records:
            print(f"{label} [{item['code']}] {item['node']} : {item['message']}")


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
    textures.add_argument("--compact", action="store_true", help="tableau id | nom | kind/grille | taille")

    sheet = commands.add_parser("sheet", help="planche annotée des IDs choisis, y compris les textures marquées USED")
    sheet.add_argument("ids", nargs="+", help="IDs ou URI rbxassetid://, dans l’ordre de la planche")
    sheet.add_argument("--out", help="PNG produit (défaut : rendus/selection-textures.png)")
    sheet.add_argument("--columns", type=int, default=6)
    sheet.add_argument("--collection", choices=["textures", "beams", "meshes"], help="défaut : chercher dans toutes les collections")
    for asset_command in (textures, sheet):
        asset_command.add_argument("--exclude-file", help="fichier d’IDs déjà utilisés, séparés par espaces, lignes ou virgules")
        asset_command.add_argument("--exclude-ids", nargs="+", help="IDs déjà utilisés (liste ou valeurs séparées par des virgules)")

    tags = commands.add_parser("tags", help="tags d’une collection et leur nombre d’assets")
    tags.add_argument("--collection", default="textures", choices=["textures", "beams", "meshes"])

    commands.add_parser("blocks", help="briques réutilisables et leurs réglages")

    compose = commands.add_parser("compose", help="assembler des briques en recette")
    compose.add_argument("plan", help="plan JSON : {\"name\", \"blocks\": [{\"block\": \"flash\", \"at\": 0}, …]}")
    compose.add_argument("--base", help="recette ou ID à laquelle ajouter les briques")
    compose.add_argument("--out", help="recette produite (défaut : affichée)")

    validate = commands.add_parser("validate", help="valider une recette")
    validate.add_argument("project")
    validate.add_argument("--verbose", "--infos", dest="include_infos", action="store_true", help="afficher aussi les infos de grille, une par texture")

    grid_confirm = commands.add_parser("grid-confirm", help="confirmer une grille contrôlée visuellement, hors catalogue")
    grid_confirm.add_argument("id", help="ID ou URI rbxassetid:// de la texture")
    grid_confirm.add_argument("grid", type=int, choices=[2, 4, 8], help="nombre de cases par côté")

    render = commands.add_parser("render", help="planche de rendu ; plusieurs recettes = une ligne chacune")
    render.add_argument("projects", nargs="+")
    render.add_argument("--out")
    render.add_argument("--times", help="instants en secondes : 0,0.1,0.3")
    render.add_argument("--frames", type=int, default=8)
    render.add_argument("--columns", type=int, default=4)
    render.add_argument("--size", default="480x270")
    render.add_argument("--camera", help="px,py,pz,tx,ty,tz (défaut : caméra du projet)")
    render.add_argument("--auto-camera", action="store_true", help="cadrer toute l’étendue de l’effet")
    render.add_argument("--no-auto-camera", action="store_true", help="garder la caméra du projet")
    render.add_argument("--no-dummy", action="store_true", help="sans mannequin d’échelle")
    backgrounds = render.add_mutually_exclusive_group()
    backgrounds.add_argument("--background", choices=["sombre", "gris", "ciel", "noir", "roblox", "dark"],
                        help="preset forcé ; défaut : environment.background de la recette")
    backgrounds.add_argument("--backgrounds", help="une ligne par recette et par fond, par exemple roblox,dark")
    render.add_argument("--no-ground", action="store_true")
    render.add_argument("--seed", type=int, default=1)
    render.add_argument("--fit", help="cadrer cet objet et ses descendants")
    render.add_argument("--fit-percentile", type=float, default=90, help="centile des particules vivantes à cadrer (défaut : 90 ; > 0 et <= 100)")
    render.add_argument("--fit-all", action="store_true", help="ancien cadrage : toute l’étendue simulée, y compris hors des instants rendus")
    render.add_argument("--focus", help="centre x,y,z (avec --radius)")
    render.add_argument("--radius", type=float)

    batch = commands.add_parser("render-batch", help="plusieurs recettes × instants × caméras, un seul Chromium")
    batch.add_argument("manifest", help='JSON {"jobs":[{"projects":["a.json"],"out":"rendus/a.png","times":[0,.1],"camera":[10,6,12,0,1,0]}]}')

    save = commands.add_parser("save", help="enregistrer dans editor/projects (visible dans l’atelier)")
    save.add_argument("project")

    export = commands.add_parser("export", help="exporter : rbxmx (glisser dans Studio), lua (ModuleScript) ou json")
    export.add_argument("projects", nargs="+")
    export.add_argument("--format", default="rbxmx", choices=["rbxmx", "lua", "json", "library"])
    export.add_argument("--out")

    commands.add_parser("projects", help="projets enregistrés")
    artistry = commands.add_parser("artistry", help="direction, mouvements, assets et revue visuelle : action + requête JSON")
    import fx_agent_tools
    artistry.add_argument("action", choices=sorted(set(fx_agent_tools.ACTIONS.values())))
    artistry.add_argument("request", nargs="?", help="fichier JSON de paramètres ; optionnel pour schema/reference_list")
    args = parser.parse_args(argv)

    try:
        if args.command == "artistry":
            data = json.loads(Path(args.request).read_text(encoding="utf-8-sig")) if args.request else {}
            show(fx_agent_tools.perform(args.action, data))
        elif args.command == "textures":
            result = fx_tools.search_assets(args.collection, args.tag, args.kind, args.query, args.limit, args.offset,
                                            exclude_ids=args.exclude_ids, exclude_file=args.exclude_file)
            if result["items"] and not args.no_sheet:
                name = "-".join(filter(None, [args.collection, args.tag, args.kind, args.query])) or args.collection
                result["sheet"] = str(fx_tools.texture_sheet(result["items"], args.out or f"rendus/{fx_tools._slug(name)}.png"))
            if args.compact:
                print(fx_tools.compact_assets(result))
            else:
                show(result)
        elif args.command == "sheet":
            items = fx_tools.assets_by_ids(args.ids, args.collection, exclude_ids=args.exclude_ids, exclude_file=args.exclude_file)
            path = fx_tools.texture_sheet(items, args.out or "rendus/selection-textures.png", args.columns)
            show({"sheet": str(path), "items": [{"id": item["id"], "used": item["used"]} for item in items]})
        elif args.command == "tags":
            show(fx_tools.tags(args.collection))
        elif args.command == "blocks":
            show(fx_modules.list_blocks())
        elif args.command == "compose":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
            def include_recipe(source):
                candidate = Path(args.plan).resolve().parent / source if isinstance(source, (str, Path)) else None
                return load_recipe(candidate if candidate is not None and candidate.is_file() else source)
            project = fx_modules.compose(plan, read_project(args.base) if args.base else None, include_loader=include_recipe)
            if args.out:
                Path(args.out).write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(args.out)
            else:
                show(project)
        elif args.command == "validate":
            project = fx_tools.validate(read_project(args.project))
            print(f"Recette valide : {project['name']} · {len(project['nodes'])} objets · {project['duration']} s")
            show_diagnostics(fx_tools.warnings(project, include_infos=args.include_infos))
        elif args.command == "grid-confirm":
            show(fx_tools.grid_confirm(args.id, args.grid))
        elif args.command == "render":
            times = [float(t) for t in args.times.split(",")] if args.times else None
            camera = [float(v) for v in args.camera.split(",")] if args.camera else None
            focus = [float(v) for v in args.focus.split(",")] if args.focus else None
            show(fx_tools.render([read_project(p) for p in args.projects], args.out, times, args.frames, args.size,
                                 auto_camera=args.auto_camera and not args.no_auto_camera, dummy=not args.no_dummy, background=args.background,
                                 ground=not args.no_ground, seed=args.seed, camera=camera, columns=args.columns,
                                 fit=args.fit, focus=focus, radius=args.radius,
                                 fit_percentile=args.fit_percentile, fit_all=args.fit_all, backgrounds=args.backgrounds))
        elif args.command == "render-batch":
            manifest_path = Path(args.manifest).resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            jobs = manifest.get("jobs") if isinstance(manifest, dict) else manifest
            show(fx_tools.render_batch(jobs, base_dir=manifest_path.parent))
        elif args.command == "save":
            show(fx_tools.save(read_project(args.project)))
        elif args.command == "export":
            if args.format == "library":
                recipes = {}
                for source in args.projects:
                    recipe = read_project(source)
                    name = Path(source).stem if Path(source).is_file() else source
                    if name in recipes:
                        raise fx_tools.ToolError("nom court dupliqué : " + name)
                    recipes[name] = recipe
                for path in fx_tools.export_library(recipes, args.out):
                    print(path)
            else:
                if len(args.projects) != 1:
                    raise fx_tools.ToolError("plusieurs recettes exigent --format library")
                print(fx_tools.export(read_project(args.projects[0]), args.format, args.out))
        elif args.command == "projects":
            show(fx_tools.list_projects())
    except (ValidationError, fx_tools.ToolError, ValueError, OSError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
