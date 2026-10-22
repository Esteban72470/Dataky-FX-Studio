"""Dataky FX Studio · serveur MCP (stdio) pour Claude Desktop, Claude Code ou tout client MCP.

Il donne à Claude les outils de l’atelier : chercher des textures en les voyant,
assembler des briques, valider, rendre l’effet en images, comparer des variantes,
enregistrer et exporter vers Roblox. Bibliothèque standard seulement ; les rendus
utilisent Node.js et Playwright (tool/fx_render.cjs).

    python tool/fx_mcp.py                          lancé par le client MCP
    python tool/fx_mcp.py --install-claude-desktop ajoute le serveur à Claude Desktop
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx_modules  # noqa: E402
import fx_tools  # noqa: E402
from fx_schema import SCHEMA, ValidationError  # noqa: E402

VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
INSTRUCTIONS = """Dataky FX Studio crée des effets visuels Roblox (ParticleEmitter, Beam, Trail, lumières) décrits par une recette JSON.
Méthode : 1) search_assets pour VOIR les textures candidates (planche avec IDs) ; 2) compose_effect avec des briques (flash, sparks, shockwave,
smoke, slash, arc, swipe, fire, charge, orb) pour une base solide, ou écrire la recette à la main (get_schema) ; 3) render_effect et REGARDER
les images (mannequin de 5 studs pour l’échelle) ; corriger et recommencer ; comparer des variantes en passant plusieurs projets ;
4) save_effect puis export_effect (rbxmx à glisser dans Studio). Pièges : la courbe d’un Beam suit +X d’Attachment0 et -X d’Attachment1 ;
l’axe vertical d’une texture de Beam suit sa longueur ; Transparency doit finir à 1 pour éviter les disparitions sèches ; les instants de
timing doivent tenir dans duration ; Orientation et Axis/SecondaryAxis d’un Attachment s’excluent. guide donne le détail."""
GUIDE = (Path(__file__).resolve().parent.parent / "CLAUDE.md")

PROJECT = {"type": "object", "description": "Recette Dataky FX complète (version 1, nodes, animations, duration…)"}
PROJECT_INPUTS = {"project": PROJECT, "project_id": {"type": "string", "description": "ID d’un projet enregistré (list_effects)"}}
EXCLUSION_OPTIONS = {
    "exclude_ids": {"type": ["array", "string"], "items": {"type": "string"}, "description": "IDs déjà utilisés, liste ou texte séparé par virgules"},
    "exclude_file": {"type": "string", "description": "Fichier local d’IDs déjà utilisés"},
}
RENDER_OPTIONS = {
    "times": {"type": "array", "items": {"type": "number"}, "description": "Instants en secondes (défaut : 8 instants répartis)"},
    "frames": {"type": "integer", "minimum": 1, "maximum": 16},
    "size": {"type": "string", "description": "Taille d’une image, ex. 480x270"},
    "auto_camera": {"type": "boolean", "default": False, "description": "Cadrer toute l’étendue de l’effet ; sinon caméra de la recette"},
    "dummy": {"type": "boolean", "description": "Mannequin Roblox de 5 studs pour l’échelle (défaut true)"},
    "background": {"type": "string", "enum": ["sombre", "gris", "ciel", "noir", "roblox", "dark"]},
    "backgrounds": {"type": ["array", "string"], "items": {"type": "string", "enum": ["sombre", "gris", "ciel", "noir", "roblox", "dark"]},
                    "description": "Une ligne par recette et par fond, ex. [roblox,dark] ou roblox,dark ; exclusif avec background"},
    "ground": {"type": "boolean"},
    "camera": {"type": "array", "items": {"type": "number"}, "minItems": 6, "maxItems": 6, "description": "px,py,pz,tx,ty,tz"},
    "seed": {"type": "integer"},
    "fit": {"type": "string", "description": "Node à cadrer avec ses descendants"},
    "fit_percentile": {"type": "number", "exclusiveMinimum": 0, "maximum": 100, "default": 90,
                       "description": "Centile des particules vivantes aux instants rendus ; les tailles sont incluses"},
    "fit_all": {"type": "boolean", "default": False, "description": "Ancien cadrage de toute l’étendue simulée"},
    "focus": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
    "radius": {"type": "number", "exclusiveMinimum": 0},
}
TOOLS = [
    {"name": "guide", "description": "Guide complet : méthode de travail, format des recettes, pièges Roblox, limites de l’émulation.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_schema", "description": "Classes, propriétés, types, valeurs autorisées et limites des recettes. Préciser class pour une seule classe.",
     "inputSchema": {"type": "object", "properties": {"class": {"type": "string"}}}},
    {"name": "search_assets", "description": "Cherche des textures, textures de Beams ou meshes de la bibliothèque et renvoie une planche d’images avec leurs IDs.",
     "inputSchema": {"type": "object", "properties": {
         "collection": {"type": "string", "enum": ["textures", "beams", "meshes"]}, "tag": {"type": "string", "description": "Impact, Slash, Smoke, Fire, Circle, Flare, Lightning…"},
         "kind": {"type": "string", "enum": ["static", "flipbook", "mesh"]}, "query": {"type": "string", "description": "mots du nom ou ID exact"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 60}, "offset": {"type": "integer", "minimum": 0},
         "sheet": {"type": "boolean", "description": "joindre la planche d’images (défaut true)"},
         "compact": {"type": "boolean", "description": "tableau id | nom | kind/grille | taille, sans long JSON"}, **EXCLUSION_OPTIONS}}},
    {"name": "texture_sheet", "description": "Planche annotée d’IDs précis, avec grille de flipbook et badge USED pour les IDs exclus.",
     "inputSchema": {"type": "object", "required": ["ids"], "properties": {
         "ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
         "collection": {"type": "string", "enum": ["textures", "beams", "meshes"]},
         "columns": {"type": "integer", "minimum": 1, "maximum": 12}, **EXCLUSION_OPTIONS}}},
    {"name": "list_tags", "description": "Tags d’une collection avec leur nombre d’assets.",
     "inputSchema": {"type": "object", "properties": {"collection": {"type": "string", "enum": ["textures", "beams", "meshes"]}}}},
    {"name": "list_blocks", "description": "Briques réutilisables (flash, sparks, shockwave…) et leurs réglages.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "compose_effect", "description": "Assemble des briques en recette validée, éventuellement ajoutées à un projet enregistré, et la rend en images.",
     "inputSchema": {"type": "object", "required": ["plan"], "properties": {
         "plan": {"type": "object", "description": "{\"name\": \"…\", \"blocks\": [{\"block\": \"flash\", \"at\": 0, \"color\": [1,0.8,0.5]}, …]}"},
         "base_project_id": {"type": "string"}, "render": {"type": "boolean", "description": "joindre une planche (défaut true)"}, **RENDER_OPTIONS}}},
    {"name": "validate_effect", "description": "Valide une recette et renvoie sa forme normalisée, ou l’erreur précise.",
     "inputSchema": {"type": "object", "required": ["project"], "properties": {"project": PROJECT,
         "include_infos": {"type": "boolean", "default": False, "description": "Joindre les infos de grille, une par texture, séparées des avertissements"}}}},
    {"name": "grid_confirm", "description": "Confirme une grille contrôlée visuellement dans tool/grid_overrides.json, hors catalogue.",
     "inputSchema": {"type": "object", "required": ["id", "grid"], "properties": {
         "id": {"type": "string", "description": "ID ou URI rbxassetid:// de la texture"},
         "grid": {"type": "integer", "enum": [2, 4, 8], "description": "Nombre de cases par côté"}}}},
    {"name": "render_effect", "description": "Rend l’effet en planche d’images à des instants précis (émulation déterministe). "
                                             "Passer projects (2 à 8) pour comparer des variantes ligne par ligne avec la même caméra.",
     "inputSchema": {"type": "object", "properties": {**PROJECT_INPUTS, "projects": {"type": "array", "items": PROJECT, "minItems": 1, "maxItems": 8},
                                                      **RENDER_OPTIONS}}},
    {"name": "render_batch", "description": "Plusieurs jobs recettes × instants × caméras dans un seul lancement Chromium.",
     "inputSchema": {"type": "object", "required": ["jobs"], "properties": {"jobs": {"type": "array", "minItems": 1, "maxItems": 128,
         "items": {"type": "object", "description": "projects (recettes ou IDs), out, times, camera, fit/focus/radius ; options camelCase",
                   "properties": {"fitPercentile": RENDER_OPTIONS["fit_percentile"], "fitAll": RENDER_OPTIONS["fit_all"],
                                  "background": RENDER_OPTIONS["background"], "backgrounds": RENDER_OPTIONS["backgrounds"]}}}}}},
    {"name": "save_effect", "description": "Enregistre la recette dans l’atelier (editor/projects) ; l’ID vient du nom si absent.",
     "inputSchema": {"type": "object", "required": ["project"], "properties": {"project": PROJECT}}},
    {"name": "list_effects", "description": "Projets enregistrés dans l’atelier.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "load_effect", "description": "Lit un projet enregistré.",
     "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}}}},
    {"name": "export_effect", "description": "Exporte vers Roblox : rbxmx (modèle à glisser dans Studio, lecteur inclus), lua (ModuleScript autonome) ou json.",
     "inputSchema": {"type": "object", "properties": {**PROJECT_INPUTS, "format": {"type": "string", "enum": ["rbxmx", "lua", "json", "library"]},
         "recipes": {"type": "object", "additionalProperties": PROJECT, "description": "Noms courts vers recettes pour format library"}}}},
]


def text(value: Any) -> dict[str, str]:
    return {"type": "text", "text": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)}


def image(path: str | Path) -> dict[str, str]:
    return {"type": "image", "data": base64.b64encode(Path(path).read_bytes()).decode("ascii"), "mimeType": "image/png"}


def project_from(args: dict[str, Any]) -> dict[str, Any]:
    if isinstance(args.get("project"), dict):
        return args["project"]
    if args.get("project_id"):
        return fx_tools.load(args["project_id"])
    raise fx_tools.ToolError("project ou project_id requis")


def render_options(args: dict[str, Any]) -> dict[str, Any]:
    return {"times": args.get("times"), "frames": int(args.get("frames", 8)), "size": args.get("size", "480x270"),
            "auto_camera": args.get("auto_camera", False), "dummy": args.get("dummy", True), "background": args.get("background"),
            "ground": args.get("ground", True), "camera": args.get("camera"), "seed": int(args.get("seed", 1)),
            "fit": args.get("fit"), "focus": args.get("focus"), "radius": args.get("radius"),
            "fit_percentile": args.get("fit_percentile", 90), "fit_all": args.get("fit_all", False), "backgrounds": args.get("backgrounds")}


def call(name: str, args: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "guide":
        return [text(GUIDE.read_text(encoding="utf-8") if GUIDE.is_file() else INSTRUCTIONS)]
    if name == "get_schema":
        if args.get("class"):
            if args["class"] not in SCHEMA["classes"]:
                raise fx_tools.ToolError("classe inconnue : " + ", ".join(SCHEMA["classes"]))
            return [text({args["class"]: SCHEMA["classes"][args["class"]]})]
        compact = {cls: {key: {k: v for k, v in spec.items() if k in {"type", "default", "enum", "min", "max", "className"}}
                         for key, spec in data["properties"].items()} for cls, data in SCHEMA["classes"].items()}
        return [text({"classes": compact, "limits": SCHEMA["limits"], "sequenceFormat": SCHEMA["sequenceFormat"], "parameters": SCHEMA["parameters"],
                      "timing": "nodes[].timing = {start, duration, mode: burst|continuous, count} pour émetteurs, beams, trails, lumières",
                      "animations": "[{node, property, keyframes: [{time (s), value}]}] pour les propriétés animatables"})]
    if name == "search_assets":
        result = fx_tools.search_assets(args.get("collection", "textures"), args.get("tag"), args.get("kind"), args.get("query"),
                                        args.get("limit", 24), args.get("offset", 0), exclude_ids=args.get("exclude_ids"),
                                        exclude_file=args.get("exclude_file"), compact=args.get("compact", False))
        content = [text(result["table"] if args.get("compact") else result)]
        if result["items"] and args.get("sheet", True):
            content.append(image(fx_tools.texture_sheet(result["items"], "rendus/mcp-textures.png")))
        return content
    if name == "texture_sheet":
        items = fx_tools.assets_by_ids(args["ids"], args.get("collection"), exclude_ids=args.get("exclude_ids"), exclude_file=args.get("exclude_file"))
        path = fx_tools.texture_sheet(items, "rendus/mcp-selection-textures.png", args.get("columns", 6))
        return [text({"sheet": str(path), "items": [{"id": item["id"], "used": item["used"]} for item in items]}), image(path)]
    if name == "list_tags":
        return [text(fx_tools.tags(args.get("collection", "textures")))]
    if name == "list_blocks":
        return [text(fx_modules.list_blocks())]
    if name == "compose_effect":
        base = fx_tools.load(args["base_project_id"]) if args.get("base_project_id") else None
        project = fx_modules.compose(args["plan"], base)
        content = [text(project)]
        if args.get("render", True):
            result = fx_tools.render(project, "rendus/mcp-compose.png", **render_options(args))
            content += [text({"render": {k: result[k] for k in ("times", "camera", "warnings", "rows", "sheet") if k in result}}), image(result["image"])]
        return content
    if name == "validate_effect":
        project = fx_tools.validate(args["project"])
        diagnostics = fx_tools.warnings(project, include_infos=args.get("include_infos", False))
        warnings = [item for item in diagnostics if item.get("level", "warning") != "info"]
        infos = [item for item in diagnostics if item.get("level") == "info"]
        return [text({"valid": True, "summary": f"{project['name']} · {len(project['nodes'])} objets · {project['duration']} s", "project": project,
                      "warning_counts": fx_tools.diagnostic_counts(warnings), "warnings": warnings,
                      "info_counts": fx_tools.diagnostic_counts(infos), "infos": infos})]
    if name == "grid_confirm":
        return [text(fx_tools.grid_confirm(args["id"], args["grid"]))]
    if name == "render_effect":
        projects = args.get("projects") or [project_from(args)]
        result = fx_tools.render(projects, "rendus/mcp-rendu.png", **render_options(args))
        return [text({k: result[k] for k in ("times", "camera", "warnings", "rows", "sheet") if k in result}), image(result["image"])]
    if name == "save_effect":
        return [text(fx_tools.save(args["project"]))]
    if name == "render_batch":
        return [text(fx_tools.render_batch(args["jobs"]))]
    if name == "list_effects":
        return [text(fx_tools.list_projects())]
    if name == "load_effect":
        return [text(fx_tools.load(args["project_id"]))]
    if name == "export_effect":
        fmt = args.get("format", "rbxmx")
        if fmt == "library":
            paths = fx_tools.export_library(args.get("recipes") or {"Effect": project_from(args)})
            return [text({"files": [str(path) for path in paths], "usage": "FX.play(Recipes.NomCourt, CFrame.new(), options)"})]
        path = fx_tools.export(project_from(args), fmt)
        hint = {"rbxmx": "Glissez ce fichier dans Roblox Studio, puis : require(workspace.<NomDuModèle>.DatakyFX).play()",
                "lua": "Collez ce code dans un ModuleScript : fx.build(workspace, Vector3.new(0, 4, 0)); fx.play()",
                "json": "Recette validée, réutilisable dans l’atelier."}[fmt]
        return [text({"file": str(path), "usage": hint})]
    raise fx_tools.ToolError(f"outil inconnu : {name}")


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None  # notifications (initialized, cancelled…) need no answer
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        return {"jsonrpc": "2.0", "id": ident, "result": {
            "protocolVersion": requested if requested in VERSIONS else VERSIONS[0], "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "dataky-fx-studio", "title": "Dataky FX Studio", "version": "1.0.0"}, "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": ident, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": ident, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            content = call(params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": ident, "result": {"content": content, "isError": False}}
        except (ValidationError, fx_tools.ToolError, ValueError, KeyError, OSError) as error:
            return {"jsonrpc": "2.0", "id": ident, "result": {"content": [text(f"Erreur : {error}")], "isError": True}}
        except Exception:  # keep the server alive; the traceback helps the client fix its call
            traceback.print_exc(file=sys.stderr)
            return {"jsonrpc": "2.0", "id": ident, "result": {"content": [text("Erreur interne : voir le journal du serveur MCP.")], "isError": True}}
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Méthode inconnue : {method}"}}


def serve() -> None:
    out = sys.stdout.buffer
    for raw in sys.stdin.buffer:
        if not raw.strip():
            continue
        try:
            message = json.loads(raw.decode("utf-8"))
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON invalide"}}
        else:
            response = handle(message) if isinstance(message, dict) else {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Requête invalide"}}
        if response is not None:
            out.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            out.flush()


def claude_desktop_config() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def install(config: Path) -> None:
    data = json.loads(config.read_text(encoding="utf-8")) if config.is_file() and config.read_text(encoding="utf-8").strip() else {}
    if config.is_file():
        shutil.copy2(config, config.with_suffix(".json.bak"))
    data.setdefault("mcpServers", {})["dataky-fx"] = {"command": sys.executable, "args": [str(Path(__file__).resolve())]}
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Serveur Dataky FX ajouté à", config)
    print("Quittez puis relancez Claude Desktop : les outils Dataky FX apparaîtront dans la conversation.")
    if not shutil.which("node"):
        print("Node.js est introuvable : installez-le, puis `npm install -g playwright` et `npx playwright install chromium` pour les rendus.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--install-claude-desktop", action="store_true", help="ajouter ce serveur à la configuration de Claude Desktop")
    parser.add_argument("--config", type=Path, help="chemin de claude_desktop_config.json (détecté par défaut)")
    args = parser.parse_args()
    if args.install_claude_desktop:
        install(args.config or claude_desktop_config())
    else:
        serve()


if __name__ == "__main__":
    main()
