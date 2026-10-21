"""AI tooling: asset search, building blocks, command line and MCP protocol."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

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
        result = subprocess.run([shutil.which("python3") or shutil.which("python"), str(Path(fx_mcp.__file__))], input=stdin.encode(),
                                capture_output=True, timeout=60)
        lines = [json.loads(line) for line in result.stdout.decode().splitlines()]
        self.assertEqual([line.get("id") for line in lines], [1, 2, None])
        self.assertEqual(lines[2]["error"]["code"], -32700)


@unittest.skipUnless(shutil.which("node"), "Node.js absent")
class RenderTests(unittest.TestCase):
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
