"""AI tooling: asset search, building blocks, command line and MCP protocol."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    from . import fx, fx_mcp, fx_modules, fx_tools
    from .fx_schema import ValidationError, validate_project
except ImportError:
    import fx
    import fx_mcp
    import fx_modules
    import fx_tools
    from fx_schema import ValidationError, validate_project


class SearchTests(unittest.TestCase):
    def test_exclusions_apply_before_total_and_pagination_and_compact_table_has_dimensions(self):
        candidates = fx_tools.search_assets(tag="Slash", limit=4)
        ids = [item["id"] for item in candidates["items"]]
        with tempfile.TemporaryDirectory() as folder:
            used = Path(folder) / "used.txt"
            used.write_text(ids[0] + ",\nrbxassetid://" + ids[1] + " # déjà utilisé\n", encoding="utf-8-sig")
            result = fx_tools.search_assets(tag="Slash", limit=1, offset=1, exclude_file=used, exclude_ids=[ids[2]], compact=True)
        self.assertEqual(result["total"], candidates["total"] - 3)
        expected = fx_tools.search_assets(tag="Slash", limit=5)["items"][4]["id"]
        self.assertEqual(result["items"][0]["id"], expected, "pagination happens after removing excluded IDs")
        self.assertTrue(result["table"].startswith("id | nom | kind/grille | taille\n"))
        self.assertRegex(result["table"], r"\d+x\d+")
        self.assertNotIn('"uri":', result["table"])
        with self.assertRaisesRegex(fx_tools.ToolError, "ID d’asset invalide"):
            fx_tools.search_assets(exclude_ids="not-an-id")

    def test_explicit_sheet_selection_preserves_order_and_marks_excluded_ids_used(self):
        chosen = fx_tools.search_assets(kind="flipbook", limit=2)["items"]
        ids = [item["id"] for item in reversed(chosen)]
        items = fx_tools.assets_by_ids(ids, exclude_ids=ids[:1])
        self.assertEqual([item["id"] for item in items], ids)
        self.assertEqual([item["used"] for item in items], [True, False])
        self.assertGreater(items[0]["flipbook"]["grid"], 1)
        with self.assertRaisesRegex(fx_tools.ToolError, "IDs inconnus.*99999999999999999999999"):
            fx_tools.assets_by_ids(["99999999999999999999999"])
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "chosen.png"
            def renderer(args):
                source = Path(args[args.index("--textures") + 1])
                data = json.loads(source.read_text(encoding="utf-8"))
                self.assertTrue(data[0]["used"])
                self.assertFalse(data[1]["used"])
                self.assertEqual(data[0]["grid"], items[0]["flipbook"]["grid"])
                self.assertEqual(data[0]["id"], ids[0])
                return {"files": [str(out)]}
            with mock.patch.object(fx_tools, "_run_renderer", side_effect=renderer):
                self.assertEqual(fx_tools.texture_sheet(items, out), out)

    def test_filters_by_tag_kind_and_query_with_local_images(self):
        result = fx_tools.search_assets("textures", tag="Slash", kind="flipbook", limit=5)
        self.assertGreater(result["total"], 5)
        self.assertEqual(len(result["items"]), 5)
        for item in result["items"]:
            self.assertIn("Slash", item["tags"])
            self.assertEqual(item["kind"], "flipbook")
            self.assertTrue(item["uri"].startswith("rbxassetid://"))
            self.assertTrue(item["image"] is None or (fx_tools.ROOT / item["image"]).is_file())
            self.assertIn(item["flipbook"]["FlipbookLayout"], {"Grid2x2", "Grid4x4", "Grid8x8", "Custom", None})
        ring = fx_tools.search_assets(query="15268066299")
        self.assertEqual([item["id"] for item in ring["items"]], ["15268066299"])

    def test_beams_and_meshes_collections(self):
        beams = fx_tools.search_assets("beams", limit=3)
        self.assertTrue(all(item["image"].startswith("beams/images/") for item in beams["items"] if item["image"]))
        meshes = fx_tools.search_assets("meshes", limit=3)
        self.assertTrue(all(item.get("MeshId", "").startswith("rbxassetid://") for item in meshes["items"]))
        self.assertIn("Impact", fx_tools.tags("textures"))


class BlockTests(unittest.TestCase):
    def test_every_block_composes_alone_into_a_valid_recipe(self):
        for name in fx_modules.BLOCKS:
            with self.subTest(block=name):
                project = fx_modules.compose({"name": name, "blocks": [{"block": name, "at": 0.2, "scale": 1.5, "color": [1, 0.2, 0.2]}]})
                self.assertEqual(validate_project(project), project)
                for node in project["nodes"]:
                    timing = node.get("timing")
                    if timing:
                        self.assertGreaterEqual(timing["start"], 0.2 - 1e-9)
                        self.assertLessEqual(timing["start"] + timing["duration"], project["duration"])

    def test_blocks_stack_with_unique_ids_and_can_extend_a_project(self):
        plan = {"name": "Pile", "blocks": [{"block": "flash"}, {"block": "flash", "at": 0.5}, {"block": "arc", "style": "lightning"}]}
        project = fx_modules.compose(plan)
        ids = [node["id"] for node in project["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(i.startswith("flash2_") for i in ids))
        extended = fx_modules.compose({"blocks": [{"block": "smoke", "at": 1}]}, project)
        self.assertEqual(extended["name"], "Pile")
        self.assertEqual(len(extended["nodes"]), len(project["nodes"]) + 2)
        self.assertGreaterEqual(extended["duration"], 2.2)

    def test_arc_attachments_tilt_their_x_axis_so_the_beam_bends(self):
        project = fx_modules.compose({"blocks": [{"block": "arc"}]})
        beam = next(n for n in project["nodes"] if n["class"] == "Beam")
        start = next(n for n in project["nodes"] if n["id"] == beam["properties"]["Attachment0"])
        self.assertGreater(start["properties"]["Axis"][1], 0.5, "+X of Attachment0 points upward")
        self.assertGreater(beam["properties"]["CurveSize0"], 0)

    def test_invalid_plans_are_explained(self):
        for plan in ({}, {"blocks": []}, {"blocks": [{"block": "nope"}]}, {"blocks": [{"block": "flash", "scale": "big"}]}):
            with self.assertRaises(ValidationError):
                fx_modules.compose(plan)
        self.assertEqual({b["block"] for b in fx_modules.list_blocks()}, set(fx_modules.BLOCKS))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fx.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_validate_info_aliases_group_by_code_and_confirm_grid_outside_catalogue(self):
        fixture = Path(__file__).parent / "fixtures" / "bulbito" / "Walk_Dust.json"
        fixture_bytes = fixture.read_bytes()
        overrides = fx.fx_tools._sibling("fx_grid_overrides")
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(overrides, "DEFAULT_PATH", Path(folder) / "grid_overrides.json"):
            code, output, error = self.run_cli("validate", str(fixture))
            self.assertEqual(code, 0, error)
            self.assertNotIn("estimated_grid", output)
            for alias in ("--verbose", "--infos"):
                code, output, error = self.run_cli("validate", str(fixture), alias)
                self.assertEqual(code, 0, error)
                self.assertIn("Résumé infos [estimated_grid] : 1", output)
                self.assertEqual(output.count("Info [estimated_grid]"), 1, "two emitters share one informational texture diagnostic")
                self.assertLess(output.index("Résumé infos"), output.index("Info [estimated_grid]"))
                self.assertNotIn("Avertissement [estimated_grid]", output)
            code, output, error = self.run_cli("grid-confirm", "rbxassetid://11844402871", "4")
            self.assertEqual(code, 0, error)
            result = json.loads(output)
            self.assertTrue(result["confirmed"])
            self.assertEqual(result["grid"], 4)
            self.assertEqual(result["texture"], "11844402871")
            self.assertTrue(Path(result["path"]).is_relative_to(Path(folder)))
            self.assertNotIn("estimated_grid", self.run_cli("validate", str(fixture), "--infos")[1])
            asset = fx.fx_tools.search_assets(query="11844402871")["items"][0]
            self.assertEqual(asset["flipbook"]["grid"], 4)
            self.assertFalse(asset["flipbook"]["estimated"])
        self.assertEqual(fixture.read_bytes(), fixture_bytes)

    def test_validate_warning_summaries_precede_details_and_keep_success_exit_code(self):
        project = fx_modules.compose({"blocks": [{"block": "flash"}, {"block": "flash"}]})
        for node in project["nodes"]:
            if node["class"] == "ParticleEmitter":
                node["properties"]["Transparency"] = [{"time": 0, "value": 0}, {"time": 1, "value": .5}]
                node["properties"]["Size"] = [{"time": 0, "value": 1}, {"time": 1, "value": 1}]
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "abrupt.json"
            file.write_text(json.dumps(project), encoding="utf-8")
            code, output, error = self.run_cli("validate", str(file))
        self.assertEqual(code, 0, error)
        self.assertIn("Résumé avertissements [abrupt_transparency] : 4", output)
        self.assertEqual(output.count("Avertissement [abrupt_transparency]"), 4)
        self.assertIn("Size reste non nulle", output)
        self.assertLess(output.index("Résumé avertissements [abrupt_transparency]"), output.index("Avertissement ["))

    def test_render_cli_forwards_fit_controls(self):
        fixture = Path(__file__).parent / "fixtures" / "bulbito" / "A1_Muzzle.json"
        with mock.patch.object(fx.fx_tools, "render", return_value={"image": "fit.png"}) as render:
            code, output, error = self.run_cli("render", str(fixture), "--fit", "Muzzle", "--times", "0.02,0.06", "--fit-percentile", "85", "--fit-all")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["image"], "fit.png")
        self.assertEqual(render.call_args.kwargs["fit_percentile"], 85)
        self.assertTrue(render.call_args.kwargs["fit_all"])
        self.assertEqual(render.call_args.args[2], [.02, .06])

    def test_compact_search_exclusions_and_explicit_sheet_command(self):
        first = fx_tools.search_assets(query="star", limit=2)["items"]
        self.assertEqual(len(first), 2)
        code, output, error = self.run_cli("textures", "--query", "star", "--compact", "--no-sheet", "--exclude-ids", first[0]["id"], "--limit", "1")
        self.assertEqual(code, 0, error)
        self.assertIn("id | nom | kind/grille | taille", output)
        self.assertIn(first[1]["id"], output)
        self.assertNotIn(first[0]["id"], output)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sheet.png"
            with mock.patch.object(fx.fx_tools, "texture_sheet", return_value=target) as sheet:
                code, output, error = self.run_cli("sheet", *(item["id"] for item in first), "--out", str(target), "--exclude-ids", first[1]["id"])
            self.assertEqual(code, 0, error)
            self.assertTrue(sheet.call_args.args[0][1]["used"])
            self.assertEqual(json.loads(output)["sheet"], str(target))
        code, _, error = self.run_cli("sheet", "99999999999999999999999")
        self.assertEqual(code, 1)
        self.assertIn("IDs inconnus", error)

    def test_compose_resolves_includes_relative_to_the_plan_file(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "pieces").mkdir()
            piece = fx_modules.compose({"blocks": [{"block": "flash"}]})
            (base / "pieces" / "muzzle.json").write_text(json.dumps(piece), encoding="utf-8")
            plan = base / "plan.json"
            plan.write_text(json.dumps({"blocks": [{"include": "pieces/muzzle.json", "position": [2, 0, 0], "at": .4}]}), encoding="utf-8")
            code, output, error = self.run_cli("compose", str(plan))
            self.assertEqual(code, 0, error)
            result = json.loads(output)
            self.assertEqual(len(result["nodes"]), len(piece["nodes"]))
            self.assertTrue(all(node["timing"]["start"] >= .4 for node in result["nodes"] if node.get("timing")))

    def test_library_cli_exports_multiple_named_recipes_and_kit(self):
        with tempfile.TemporaryDirectory() as folder:
            files = [Path(folder) / (name + ".json") for name in ("A1_Muzzle", "A2_Impact")]
            for file in files:
                file.write_text(json.dumps(fx_modules.compose({"blocks": [{"block": "flash"}]})), encoding="utf-8")
            target = Path(folder) / "MesEffets.lua"
            code, output, error = self.run_cli("export", *(str(file) for file in files), "--format", "library", "--out", str(target))
            self.assertEqual(code, 0, error)
            self.assertIn("DatakyFXKit.lua", output)
            self.assertTrue(target.with_name("DatakyFXKit.lua").is_file())
            self.assertIn('["A1_Muzzle"]=', target.read_text(encoding="utf-8"))
            self.assertIn('["A2_Impact"]=', target.read_text(encoding="utf-8"))
            self.assertEqual(self.run_cli("export", str(files[0]), str(files[0]), "--format", "library", "--out", str(target))[0], 1)
            self.assertEqual(self.run_cli("export", *(str(file) for file in files), "--format", "lua")[0], 1)

    def test_compose_validate_and_export_rbxmx(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = Path(folder) / "plan.json"
            plan.write_text(json.dumps({"name": "CLI", "blocks": [{"block": "shockwave"}]}), encoding="utf-8")
            recipe = Path(folder) / "recette.json"
            self.assertEqual(self.run_cli("compose", str(plan), "--out", str(recipe))[0], 0)
            code, out, _ = self.run_cli("validate", str(recipe))
            self.assertEqual(code, 0)
            self.assertIn("Recette valide", out)
            target = Path(folder) / "cli.rbxmx"
            self.assertEqual(self.run_cli("export", str(recipe), "--out", str(target))[0], 0)
            self.assertIn("<roblox", target.read_text(encoding="utf-8"))
        code, _, err = self.run_cli("validate", "absent.json")
        self.assertEqual(code, 1)
        self.assertIn("introuvable", err)
        code, out, _ = self.run_cli("textures", "--tag", "Fire", "--limit", "2", "--no-sheet")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["items"]), 2)


class McpTests(unittest.TestCase):
    def call(self, name, arguments=None, ident=1):
        return fx_mcp.handle({"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})["result"]

    def test_validation_keeps_infos_separate_and_grid_confirmation_uses_overrides(self):
        fixture = Path(__file__).parent / "fixtures" / "bulbito" / "Pillar_InvisibleInPlay.json"
        project = json.loads(fixture.read_text(encoding="utf-8"))
        overrides = fx_mcp.fx_tools._sibling("fx_grid_overrides")
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(overrides, "DEFAULT_PATH", Path(folder) / "grid_overrides.json"):
            ordinary = self.call("validate_effect", {"project": project})
            self.assertFalse(ordinary["isError"])
            normal_data = json.loads(ordinary["content"][0]["text"])
            self.assertFalse(normal_data["infos"])
            self.assertIn("flipbook_empty_start", normal_data["warning_counts"])
            with_infos = self.call("validate_effect", {"project": project, "include_infos": True})
            data = json.loads(with_infos["content"][0]["text"])
            self.assertEqual(data["warnings"], normal_data["warnings"])
            self.assertTrue(all(item["level"] == "info" for item in data["infos"]))
            self.assertTrue(all(item["level"] == "warning" for item in data["warnings"]))
            self.assertEqual(data["info_counts"]["estimated_grid"], len(data["infos"]))
            confirmed = self.call("grid_confirm", {"id": "70418763522849", "grid": 4})
            self.assertFalse(confirmed["isError"])
            self.assertTrue(Path(json.loads(confirmed["content"][0]["text"])["path"]).is_relative_to(Path(folder)))
            data = json.loads(self.call("validate_effect", {"project": project, "include_infos": True})["content"][0]["text"])
            self.assertNotIn("70418763522849", {item.get("texture") for item in data["infos"]})

    def test_fit_and_info_options_have_typed_mcp_schemas_and_forwarded_values(self):
        tools = {tool["name"]: tool for tool in fx_mcp.TOOLS}
        for name in ("render_effect", "compose_effect"):
            options = tools[name]["inputSchema"]["properties"]
            self.assertEqual(options["fit_percentile"]["type"], "number")
            self.assertEqual(options["fit_all"]["type"], "boolean")
        batch_options = tools["render_batch"]["inputSchema"]["properties"]["jobs"]["items"]["properties"]
        self.assertEqual(batch_options["fitPercentile"]["maximum"], 100)
        self.assertEqual(batch_options["fitAll"]["type"], "boolean")
        self.assertEqual(tools["validate_effect"]["inputSchema"]["properties"]["include_infos"]["type"], "boolean")
        self.assertEqual(fx_mcp.render_options({"fit_percentile": 82, "fit_all": True})["fit_percentile"], 82)
        self.assertTrue(fx_mcp.render_options({"fit_all": True})["fit_all"])

    def test_compact_search_and_exclusions_are_exposed_over_mcp(self):
        first = fx_tools.search_assets(query="star", limit=2)["items"]
        result = self.call("search_assets", {"query": "star", "limit": 1, "sheet": False, "compact": True, "exclude_ids": [first[0]["id"]]})
        self.assertFalse(result["isError"])
        self.assertTrue(result["content"][0]["text"].startswith("id | nom | kind/grille | taille\n"))
        self.assertIn(first[1]["id"], result["content"][0]["text"])
        self.assertNotIn(first[0]["id"], result["content"][0]["text"])
        tools = {tool["name"]: tool for tool in fx_mcp.TOOLS}
        self.assertIn("exclude_file", tools["search_assets"]["inputSchema"]["properties"])
        self.assertIn("texture_sheet", tools)
        self.assertTrue(self.call("texture_sheet", {"ids": ["99999999999999999999999"]})["isError"])

    def test_handshake_listing_and_unknown_methods(self):
        init = fx_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", init["result"]["capabilities"])
        self.assertIn("compose_effect", init["result"]["instructions"])
        self.assertIsNone(fx_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = fx_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual(len({t["name"] for t in tools}), len(tools))
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
        self.assertEqual(fx_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})["error"]["code"], -32601)

    def test_tools_return_content_or_explained_errors(self):
        result = self.call("list_blocks")
        self.assertFalse(result["isError"])
        self.assertEqual(len(json.loads(result["content"][0]["text"])), len(fx_modules.BLOCKS))
        result = self.call("search_assets", {"tag": "Smoke", "limit": 3, "sheet": False})
        self.assertEqual(len(json.loads(result["content"][0]["text"])["items"]), 3)
        result = self.call("compose_effect", {"plan": {"blocks": [{"block": "orb"}]}, "render": False})
        project = json.loads(result["content"][0]["text"])
        self.assertTrue(self.call("validate_effect", {"project": project})["content"][0]["text"].count('"valid": true'))
        broken = self.call("validate_effect", {"project": {"version": 1, "name": "x", "nodes": [{"id": "b", "class": "Beam", "parent": None}]}})
        self.assertTrue(broken["isError"])
        self.assertIn("parent", broken["content"][0]["text"])
        self.assertTrue(self.call("export_effect", {})["isError"])
        self.assertIn("Beam", json.loads(self.call("get_schema", {"class": "Beam"})["content"][0]["text"]))
        self.assertTrue(self.call("unknown_tool")["isError"])

    def test_claude_desktop_install_keeps_other_servers(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "claude_desktop_config.json"
            config.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                fx_mcp.install(config)
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(set(data["mcpServers"]), {"other", "dataky-fx"})
            self.assertEqual(data["theme"], "dark")
            self.assertTrue(data["mcpServers"]["dataky-fx"]["args"][0].endswith("fx_mcp.py"))
            self.assertTrue(config.with_suffix(".json.bak").is_file())

    def test_stdio_transport_answers_line_by_line(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "ping"}]
        stdin = "\n".join(json.dumps(m) for m in messages) + "\nnot json\n"
        result = subprocess.run([sys.executable, str(Path(fx_mcp.__file__))], input=stdin.encode(),
                                capture_output=True, timeout=60)
        lines = [json.loads(line) for line in result.stdout.decode().splitlines()]
        self.assertEqual([line.get("id") for line in lines], [1, 2, None])
        self.assertEqual(lines[2]["error"]["code"], -32700)


@unittest.skipUnless(shutil.which("node"), "Node.js absent")
class RenderTests(unittest.TestCase):
    def test_background_options_reach_cli_mcp_and_batch_and_reject_invalid_lists(self):
        recipe = fx_modules.compose({"blocks": [{"block": "flash"}]})
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "recipe.json"
            source.write_text(json.dumps(recipe), encoding="utf-8")
            with mock.patch.object(fx_tools, "render", return_value={"files": []}) as render, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fx.main(["render", str(source), "--background", "dark"]), 0)
                self.assertEqual(render.call_args.kwargs["background"], "dark")
                self.assertEqual(fx.main(["render", str(source), "--backgrounds", "roblox,dark"]), 0)
                self.assertEqual(render.call_args.kwargs["backgrounds"], "roblox,dark")
            for options in ({"background": "dark"}, {"backgrounds": ["roblox", "dark"]}):
                with mock.patch.object(fx_tools, "render", return_value={"image": "ignored", "rows": [{"background": "dark"}]}) as render, mock.patch.object(fx_mcp, "image", return_value={}):
                    result = fx_mcp.call("render_effect", {"project": recipe, **options})
                    for key, value in options.items():
                        self.assertEqual(render.call_args.kwargs[key], value)
                    self.assertIn('"rows"', result[0]["text"])
            def manifest(args, **kwargs):
                value = json.loads(Path(args[1]).read_text(encoding="utf-8"))["jobs"][0]
                self.assertEqual(value["backgrounds"], ["roblox", "dark"])
                return {"jobs": []}
            with mock.patch.object(fx_tools, "_run_renderer", side_effect=manifest):
                fx_mcp.call("render_batch", {"jobs": [{"projects": [recipe], "backgrounds": ["roblox", "dark"]}]})
            for backgrounds in ([], "dark,", ["bad"], 42, [True], ["dark"] * 9):
                with self.subTest(backgrounds=backgrounds), mock.patch.object(fx_tools, "_run_renderer") as renderer:
                    with self.assertRaises(fx_tools.ToolError):
                        fx_tools.render(recipe, backgrounds=backgrounds)
                    renderer.assert_not_called()
        for tool in fx_mcp.TOOLS:
            if tool["name"] in {"render_effect", "compose_effect"}:
                props = tool["inputSchema"]["properties"]
                self.assertIn("dark", props["background"]["enum"])
                self.assertIn("backgrounds", props)

    def test_real_backgrounds_work_through_cli_mcp_and_batch_reports(self):
        recipe = fx_modules.compose({"blocks": [{"block": "flash"}]})
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "recipe.json"
            source.write_text(json.dumps(recipe), encoding="utf-8")
            cli, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(cli), contextlib.redirect_stderr(errors):
                code = fx.main(["render", str(source), "--background", "dark", "--times", "0", "--size", "80x60", "--no-dummy", "--out", str(Path(folder) / "cli.png")])
            if code and ("Playwright est introuvable" in errors.getvalue() or "inaccessible dans le bac à sable" in errors.getvalue()):
                self.skipTest(errors.getvalue())
            self.assertEqual(code, 0, errors.getvalue() + cli.getvalue())
            self.assertEqual(json.loads(cli.getvalue())["rows"][0]["background"], "dark")
            batch = fx_tools.render_batch([{"projects": [recipe], "times": [0], "size": "80x60", "dummy": False, "backgrounds": ["roblox", "dark"], "out": str(Path(folder) / "batch.png")}])
            original = fx_tools.render
            def render(projects, out, **kwargs):
                return original(projects, Path(folder) / "mcp.png", **kwargs)
            with mock.patch.object(fx_tools, "render", side_effect=render):
                mcp = fx_mcp.call("render_effect", {"project": recipe, "times": [0], "size": "80x60", "dummy": False, "backgrounds": "roblox,dark"})
            for result in (batch["jobs"][0], json.loads(mcp[0]["text"])):
                self.assertEqual([r["background"] for r in result["rows"]], ["roblox", "dark"])
                self.assertEqual(result["sheet"]["rows"], 2)
            self.assertEqual(mcp[1]["type"], "image")
            self.assertEqual(batch["browser_launches"], 1)

    def test_blueberrinni_camera_reports_match_request_single_and_batch(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "blueberrinni"
        jobs = json.loads((fixture_dir / "jobs_camera_ignored.json").read_text(encoding="utf-8"))["jobs"]
        requested = jobs[0]["camera"]
        recipe = json.loads((fixture_dir / jobs[0]["projects"][0]).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            jobs[0]["out"] = str(Path(folder) / "batch.png")
            jobs += [{"projects": [recipe], "out": str(Path(folder) / "recipe.png"), "times": [.1]}]
            try:
                batch = fx_tools.render_batch(jobs, base_dir=fixture_dir)
                single = fx_tools.render(recipe, Path(folder) / "single.png", times=[.1], camera=requested)
                default = fx_tools.render(recipe, Path(folder) / "default.png", times=[.1])
            except fx_tools.ToolError as error:
                if "Playwright est introuvable" in str(error) or "inaccessible dans le bac à sable" in str(error):
                    self.skipTest(str(error))
                raise
        expected = {"position": requested[:3], "target": requested[3:], "fov": recipe["camera"].get("fov", 50)}
        self.assertEqual(batch["jobs"][0]["camera"], expected)
        self.assertEqual(single["camera"], expected)
        self.assertEqual(batch["jobs"][1]["camera"], recipe["camera"])
        self.assertEqual(default["camera"], recipe["camera"])

    def test_targeted_render_flags_and_batch_manifest_reach_one_renderer_call(self):
        from unittest.mock import patch
        project = fx_modules.compose({"blocks": [{"block": "flash"}]})
        with tempfile.TemporaryDirectory() as folder:
            def fake_render(args, **kwargs):
                return {"files": [], "times": [0], "camera": {}, "warnings": []}
            with patch.object(fx_tools, "_run_renderer", side_effect=fake_render) as renderer:
                fx_tools.render(project, Path(folder) / "fit.png", fit=project["nodes"][0]["id"], fit_percentile=85, fit_all=True)
                self.assertIn("--fit", renderer.call_args.args[0])
                args = renderer.call_args.args[0]
                self.assertEqual(args[args.index("--fit-percentile") + 1], "85.0")
                self.assertIn("--fit-all", args)
                fx_tools.render(project, Path(folder) / "focus.png", focus=[1, 2, 3], radius=4)
                args = renderer.call_args.args[0]
                self.assertEqual(args[args.index("--focus") + 1], "1.0,2.0,3.0")
                self.assertEqual(args[args.index("--radius") + 1], "4.0")
            recipe_file = Path(folder) / "a.json"
            recipe_file.write_text(json.dumps(project), encoding="utf-8")
            captured = []
            def read_manifest(args, **kwargs):
                self.assertEqual(args[0], "--batch")
                captured.append(json.loads(Path(args[1]).read_text(encoding="utf-8")))
                return {"jobs": [], "files": [], "browser_launches": 1}
            with patch.object(fx_tools, "_run_renderer", side_effect=read_manifest) as renderer:
                result = fx_tools.render_batch([
                    {"projects": ["a.json"], "out": str(Path(folder) / "front.png"), "camera": [10, 6, 12, 0, 1, 0]},
                    {"projects": [project], "out": str(Path(folder) / "side.png"), "focus": [0, 1, 0], "radius": 2, "fitPercentile": 95, "fitAll": True},
                ], base_dir=folder)
                self.assertEqual(renderer.call_count, 1)
                self.assertEqual(result["browser_launches"], 1)
                self.assertEqual(len(captured[0]["jobs"]), 2)
                self.assertEqual(captured[0]["jobs"][0]["projects"][0], project)
                self.assertFalse(captured[0]["jobs"][1]["autoCamera"])
                self.assertEqual(captured[0]["jobs"][1]["fitPercentile"], 95)
                self.assertTrue(captured[0]["jobs"][1]["fitAll"])
            with self.assertRaises(fx_tools.ToolError):
                fx_tools.render_batch([])

    def test_fit_percentile_requires_finite_valid_range_before_starting_renderer(self):
        project = fx_modules.compose({"blocks": [{"block": "flash"}]})
        for percentile in (True, "90", 0, -1, 101, float("inf"), float("nan")):
            with self.subTest(percentile=percentile), mock.patch.object(fx_tools, "_run_renderer") as renderer:
                with self.assertRaisesRegex(fx_tools.ToolError, "fit_percentile"):
                    fx_tools.render(project, fit_percentile=percentile)
                renderer.assert_not_called()

    def test_render_and_texture_sheet_produce_png(self):
        try:
            with tempfile.TemporaryDirectory() as folder:
                project = fx_modules.compose({"name": "Rendu", "blocks": [{"block": "flash"}]})
                result = fx_tools.render([project, project], Path(folder) / "comparaison.png", times=[0.05], size="160x90")
                self.assertTrue(Path(result["image"]).read_bytes().startswith(b"\x89PNG"))
                sheet = fx_tools.texture_sheet(fx_tools.search_assets(tag="Circle", limit=2)["items"], Path(folder) / "t.png")
                self.assertTrue(sheet.read_bytes().startswith(b"\x89PNG"))
        except fx_tools.ToolError as error:
            if "Playwright" in str(error):
                self.skipTest(str(error))
            raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
