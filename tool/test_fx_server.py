"""Local API and validation regressions. All written files live in temp folders."""
from copy import deepcopy
import base64
import binascii
import http.client
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zlib

if __package__:
    from .fx_schema import CLASSES, ValidationError, validate_project, validate_value
    from .fx_server import APP, create_server, png_dimensions
else:
    from fx_schema import CLASSES, ValidationError, validate_project, validate_value
    from fx_server import APP, create_server, png_dimensions


def project():
    return {"version": 1, "name": "Éclair Dataky", "duration": 3, "loop": False,
            "nodes": [
                {"id": "part", "class": "Part", "parent": None, "properties": {"Position": [0, 1, 0], "Transparency": 1}},
                {"id": "a0", "class": "Attachment", "parent": "part", "properties": {"Position": [-2, 0, 0]}},
                {"id": "a1", "class": "Attachment", "parent": "part", "properties": {"Position": [2, 0, 0]}},
                {"id": "beam", "class": "Beam", "parent": "part", "properties": {"Attachment0": "a0", "Attachment1": "a1", "Width0": 0.3}},
                {"id": "emitter", "class": "ParticleEmitter", "parent": "a0", "properties": {"Size": [[0, 1, 0], [1, 0, 0]], "Texture": "rbxassetid://123"}, "timing": {"mode": "burst", "start": 0.2, "duration": 0.5, "count": 30}},
            ], "animations": [{"node": "a1", "property": "Position", "keyframes": [{"time": 0, "value": [2, 0, 0]}, {"time": 3, "value": [5, 0, 0]}]}],
            "camera": {"position": [10, 6, 12], "target": [0, 1, 0]}}


def tiny_png():
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x80\xff")) + chunk(b"IEND", b"")


class SchemaTests(unittest.TestCase):
    def test_normalizes_both_sequence_forms_without_mutating(self):
        original = project()
        clean = validate_project(original)
        self.assertIsInstance(original["nodes"][-1]["properties"]["Size"][0], list)
        self.assertEqual(clean["nodes"][-1]["properties"]["Size"][0], {"time": 0, "value": 1, "envelope": 0})
        self.assertEqual(clean, validate_project(clean))

    def reject(self, data, contains=None):
        with self.assertRaises(ValidationError) as result:
            validate_project(data)
        if contains:
            self.assertIn(contains, str(result.exception))

    def test_incorrect_reference_and_parent_rejected(self):
        for reference in ("missing", "part"):
            data = project()
            data["nodes"][3]["properties"]["Attachment0"] = reference
            self.reject(data, "Attachment")
        data = project()
        data["nodes"][-1]["parent"] = None
        self.reject(data, "parent")
        data = project()
        data["nodes"][1]["parent"] = "beam"
        self.reject(data, "incompatible")

    def test_cycle_duplicate_and_unknown_properties_rejected(self):
        data = project()
        data["nodes"][0]["parent"] = "part"
        self.reject(data, "cycle")
        data = project()
        data["nodes"][2]["id"] = "a0"
        self.reject(data, "utilisé")
        data = project()
        data["nodes"][-1]["properties"]["PretendRobloxProperty"] = 1
        self.reject(data, "inconnu")

    def test_ranges_enums_finite_types_and_timings_rejected(self):
        for prop, value in (("Rate", float("nan")), ("Lifetime", [4, 2]), ("LightInfluence", 1.1), ("Enabled", "true"), ("FlipbookLayout", "Grid17"), ("Texture", "https://evil.test/file")):
            data = project()
            data["nodes"][-1]["properties"][prop] = value
            self.reject(data)
        data = project()
        data["nodes"][-1]["timing"]["start"] = 2.8
        self.reject(data, "dépasse")
        data = project()
        data["nodes"][0]["timing"] = {"start": 0}
        self.reject(data, "timing")

    def test_sequences_and_animations_require_ordered_endpoints(self):
        for sequence in ([[0.1, 1, 0], [1, 0, 0]], [[0, 1, 0], [0.7, 2, 0], [0.5, 1, 0], [1, 0, 0]]):
            data = project()
            data["nodes"][-1]["properties"]["Size"] = sequence
            self.reject(data)
        data = project()
        data["animations"][0]["keyframes"][1]["time"] = 0
        self.reject(data, "croissants")
        data = project()
        data["animations"][0]["property"] = "Visible"
        data["animations"][0]["keyframes"] = [{"time": 0, "value": True}]
        self.assertEqual(validate_project(data)["animations"][0]["property"], "Visible")

    def test_public_schema_values_are_valid(self):
        for cls, spec in CLASSES.items():
            for key, prop in spec["properties"].items():
                validate_value(prop["default"], prop, cls + "." + key)

    def test_environment_plan_metadata_is_validated_and_preserved(self):
        data = project()
        data["environment"] = {"background": "#19aB22"}
        clean = validate_project(data)
        self.assertEqual(clean["environment"], data["environment"])
        self.assertEqual(validate_project(clean), clean)
        for invalid in ("red", "#fff", "#12345678", "url(javascript:evil)", None, 12):
            data["environment"]["background"] = invalid
            self.reject(data, "environment.background")
        data["environment"] = {"background": "#123456", "Lighting": {"Brightness": 100}}
        self.reject(data, "inconnu")

    def test_curve_editor_metadata_preserves_handles_and_rejects_unsafe_values(self):
        data = project()
        data["editor"] = {"version": 1, "curves": {"emitter::Size": {"version": 1, "mode": "bezier", "handles": [{"time": 0, "value": 1, "out": [0.3, 1.2]}, {"time": 1, "value": 0, "in": [0.8, 0.2]}]}}}
        clean = validate_project(data)
        self.assertEqual(clean["editor"], data["editor"])
        self.assertEqual(validate_project(clean), clean)
        invalid = deepcopy(data)
        invalid["editor"]["execute"] = "anything"
        self.reject(invalid, "inconnu")
        for dangerous in ({"x": float("nan")}, {"__proto__": {}}, {"mode": "x" * 20001}):
            invalid = deepcopy(data)
            invalid["editor"]["curves"]["emitter::Size"] = dangerous
            self.reject(invalid)
        nested = {}
        for _ in range(10):
            nested = {"nested": nested}
        invalid = deepcopy(data)
        invalid["editor"]["curves"]["emitter::Size"] = nested
        self.reject(invalid, "imbriquée")
        invalid["editor"]["curves"] = {f"emitter::Property{i}": {"description": "x" * 19000} for i in range(3)}
        self.reject(invalid, "50 Ko")

    def test_png_decode_rejects_corruption_and_decompression_bomb(self):
        valid = tiny_png()
        self.assertEqual(png_dimensions(valid), (1, 1))
        damaged = bytearray(valid)
        damaged[-7] ^= 8
        with self.assertRaises(ValidationError):
            png_dimensions(bytes(damaged))
        with self.assertRaises(ValidationError):
            png_dimensions(valid + b"trailing")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dataky-fx-test-")
        self.root = Path(self.temp.name)
        (self.root / "editor").mkdir()
        (self.root / "editor" / "index.html").write_text("<h1>Dataky FX</h1>", encoding="utf-8")
        (self.root / "editor" / "curves.js").write_text("globalThis.DatakyCurves = {};", encoding="utf-8")
        for name in ("emulator.js", "render.html", "render.js"):
            (self.root / "editor" / name).write_text("// " + name, encoding="utf-8")
        (self.root / "tool").mkdir()
        (self.root / "tool" / "fx_plugin.lua").write_text("return true", encoding="utf-8")
        (self.root / "images").mkdir()
        (self.root / "images" / "1.png").write_bytes(tiny_png())
        (self.root / "textures.json").write_text('[{"asset_id":"1"}]', encoding="utf-8")
        (self.root / "secret.json").write_text('{"secret":true}', encoding="utf-8")
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(data).encode("utf-8") if data is not None else None
        conn.request(method, path, body, request_headers)
        response = conn.getresponse()
        raw = response.read()
        status, kind = response.status, response.getheader("Content-Type", "")
        conn.close()
        return status, json.loads(raw) if kind.startswith("application/json") else raw

    def start_frames(self, project_id="native-effect"):
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "studio-a", "version": 2, "capabilities": {"native_preview": True}})[0], 200)
        recipe = project()
        recipe["id"] = project_id
        self.assertEqual(self.request("POST", "/api/preview", {"action": "apply", "project": recipe})[0], 202)
        self.assertEqual(self.request("POST", "/api/preview", {"action": "preview_start", "fps": 2})[0], 202)
        generation = self.request("GET", "/api/status")[1]["preview"]["generation"]
        self.assertEqual(self.request("POST", "/bridge/preview_status", {"client_id": "studio-a", "generation": generation, "enabled": True, "available": True, "permission": True, "fps": 2})[0], 200)
        return {"client_id": "studio-a", "generation": generation, "image": "data:image/png;base64," + base64.b64encode(tiny_png()).decode(), "project_id": project_id, "time": 0.75}

    def test_native_frame_is_memory_only_and_exposes_status_metadata(self):
        payload = self.start_frames()
        status, result = self.request("POST", "/bridge/frame", payload)
        self.assertEqual(status, 200)
        metadata = result["frame"]
        self.assertEqual(metadata["width"], 1)
        self.assertEqual(metadata["project_id"], "native-effect")
        self.assertEqual(metadata["project_name"], "Éclair Dataky")
        self.assertEqual(metadata["time"], 0.75)
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[1], tiny_png())
        exposed = self.request("GET", "/api/preview/frame")[1]
        self.assertEqual(exposed["frame"]["sequence"], metadata["sequence"])
        self.assertGreaterEqual(exposed["frame"]["age"], 0)
        self.assertEqual(self.request("GET", "/api/status")[1]["preview"]["frame"]["sequence"], metadata["sequence"])
        self.assertFalse(self.server.snapshots.exists())
        payload["time"] = 1.25
        second = self.request("POST", "/bridge/frame", payload)[1]["frame"]
        self.assertEqual(second["sequence"], metadata["sequence"] + 1)
        self.assertEqual(self.server.latest_frame["metadata"]["time"], 1.25)

    def test_native_frames_reject_unknown_clients_corruption_and_oversize(self):
        payload = self.start_frames()
        wrong = {**payload, "client_id": "studio-b"}
        self.assertEqual(self.request("POST", "/bridge/frame", wrong)[0], 409)
        invalid = {**payload, "image": "data:image/png;base64,bm90LXBuZw=="}
        self.assertEqual(self.request("POST", "/bridge/frame", invalid)[0], 400)
        huge = {**payload, "image": "data:image/png;base64," + "A" * 5_333_340}
        self.assertEqual(self.request("POST", "/bridge/frame", huge)[0], 413)
        self.assertIsNone(self.server.latest_frame)
        self.assertFalse(self.server.snapshots.exists())

    def test_native_preview_state_requires_strict_bool_and_active_generation(self):
        payload = self.start_frames()
        valid = {"client_id": "studio-a", "generation": payload["generation"], "enabled": True, "available": True, "permission": True, "fps": 2}
        self.assertEqual(self.request("POST", "/bridge/preview_status", {**valid, "permission": "yes"})[0], 400)
        self.assertEqual(self.request("POST", "/bridge/preview_status", {**valid, "client_id": "studio-b"})[0], 409)
        self.assertEqual(self.request("POST", "/bridge/preview_status", {**valid, "generation": payload["generation"] - 1})[0], 409)
        self.request("POST", "/bridge/frame", payload)
        self.assertEqual(self.request("POST", "/bridge/preview_status", {**valid, "enabled": False})[0], 200)
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[0], 404)

    def test_native_fps_is_bounded_and_curves_script_is_served(self):
        payload = self.start_frames()
        self.assertEqual(self.request("GET", "/curves.js")[0], 200)
        status, result = self.request("POST", "/api/preview", {"action": "preview_start", "fps": 15})
        self.assertEqual(status, 202)
        self.assertEqual(result["command"]["fps"], 15)
        self.assertEqual(self.request("POST", "/api/preview", {"action": "preview_start", "fps": 16})[0], 400)

    def test_native_frame_expires_with_frame_age_or_client_lease(self):
        payload = self.start_frames()
        self.request("POST", "/bridge/frame", payload)
        self.server.latest_frame["received"] -= 6
        self.assertIsNone(self.request("GET", "/api/preview/frame")[1]["frame"])
        self.assertEqual(self.request("POST", "/api/snapshot", {"native": True})[0], 409)
        self.request("POST", "/bridge/frame", payload)
        self.server.client["seen_monotonic"] -= 21
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[0], 404)
        self.assertFalse(self.request("GET", "/api/status")[1]["connected"])
        self.assertEqual(self.request("POST", "/bridge/frame", payload)[0], 409)

    def test_project_change_and_stop_discard_inflight_native_images(self):
        payload = self.start_frames()
        self.request("POST", "/bridge/frame", payload)
        recipe = project()
        recipe["id"] = "new-composition"
        status, command = self.request("POST", "/api/preview", {"action": "play", "project": recipe})
        self.assertEqual(status, 202)
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[0], 404)
        self.assertEqual(self.request("POST", "/bridge/frame", payload)[0], 409)
        wrong_project = {**payload, "generation": command["command"]["capture_generation"]}
        self.assertEqual(self.request("POST", "/bridge/frame", wrong_project)[0], 409)
        current = {**wrong_project, "project_id": "new-composition"}
        self.assertEqual(self.request("POST", "/bridge/frame", current)[0], 200)
        self.assertEqual(self.request("POST", "/api/preview", {"action": "stop"})[0], 202)
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[0], 404)
        self.assertEqual(self.request("POST", "/bridge/frame", current)[0], 409)

    def test_native_snapshot_uses_actual_capture_identity_and_time(self):
        payload = self.start_frames()
        self.assertEqual(self.request("POST", "/bridge/frame", payload)[0], 200)
        metadata = self.server.latest_frame["metadata"]
        for override in ({"project_id": "different-draft"}, {"time": 2.5}):
            self.assertEqual(self.request("POST", "/api/snapshot", {"native": True, **override})[0], 409)
        status, saved = self.request("POST", "/api/snapshot", {"native": True})
        self.assertEqual(status, 201)
        self.assertEqual(saved["capture_source"], "studio-native")
        self.assertEqual(saved["captured_at"], metadata["at"])
        self.assertEqual(saved["frame_sequence"], metadata["sequence"])
        self.assertEqual(saved["project_id"], "native-effect")
        self.assertEqual(saved["time"], 0.75)
        self.assertEqual(self.request("GET", saved["url"])[1], tiny_png())
        self.assertEqual(len(list(self.server.snapshots.glob("*.png"))), 1)

    def test_native_goodbye_discards_last_frame_for_future_clients(self):
        payload = self.start_frames()
        self.request("POST", "/bridge/frame", payload)
        self.assertEqual(self.request("POST", "/bridge/goodbye", {"client_id": "studio-a"})[0], 200)
        self.assertEqual(self.request("GET", "/api/preview/frame.png")[0], 404)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "studio-b"})[0], 200)
        self.assertIsNone(self.request("GET", "/api/preview/frame")[1]["frame"])

    def test_old_bridge_native_actions_rejected_before_dispatch_but_edit_still_works(self):
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "old-bridge", "version": 1})[0], 200)
        status = self.request("GET", "/api/status")[1]
        self.assertTrue(status["bridge_update_required"])
        self.assertEqual(status["bridge_capabilities"], {})
        for action in ("preview_start", "preview_stop", "capture_status"):
            code, error = self.request("POST", "/api/preview", {"action": action})
            self.assertEqual(code, 409)
            self.assertIn("ancien", error["error"])
            self.assertIn("Plugins > Dataky FX > Connexion", error["error"])
        self.assertEqual(len(self.server.commands), 0)
        for action in ("apply", "play", "stop", "clear"):
            payload = {"action": action, "project": project()} if action in {"apply", "play"} else {"action": action}
            self.assertEqual(self.request("POST", "/api/preview", payload)[0], 202)
        self.assertEqual(self.request("GET", "/api/runtime")[1]["current_bridge_version"], 2)

    def test_native_capability_handshake_accepts_updated_bridge(self):
        capabilities = {"native_preview": True, "capture_permission": False, "capture_context": "plugin", "capture_permission_request": True, "commands": ["preview_start", "preview_stop", "capture_status"]}
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "bridge-v2", "version": 2, "capabilities": capabilities})[0], 200)
        status = self.request("GET", "/api/status")[1]
        self.assertEqual(status["bridge_capabilities"], capabilities)
        self.assertFalse(status["bridge_update_required"])
        self.assertEqual(self.request("POST", "/api/preview", {"action": "preview_start"})[0], 202)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "bridge-v2", "capabilities": {"native_preview": "yes"}})[0], 400)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "bridge-v2", "capabilities": {"capture_context": "browser"}})[0], 400)

    def test_new_client_lease_clears_old_errors_and_acknowledgements(self):
        self.request("POST", "/bridge/hello", {"client_id": "old-bridge"})
        self.server.last_error = "Action interdite preview_start"
        self.server.last_ack = {"id": "old-command", "ok": False, "error": self.server.last_error}
        self.server.client["seen_monotonic"] -= 21
        self.request("POST", "/bridge/hello", {"client_id": "updated-bridge", "version": 2, "capabilities": {"native_preview": True}})
        status = self.request("GET", "/api/status")[1]
        self.assertIsNone(status["last_error"])
        self.assertIsNone(status["last_ack"])
        self.assertFalse(status["bridge_update_required"])

    def test_create_list_load_delete_and_invalid_overwrite(self):
        status, saved = self.request("POST", "/api/project", project())
        self.assertEqual(status, 201)
        ident = saved["id"]
        self.assertEqual(self.request("GET", "/api/project/" + ident)[1], saved)
        listed = self.request("GET", "/api/projects")[1]["projects"]
        self.assertEqual(listed[0]["id"], ident)
        invalid = deepcopy(saved)
        invalid["nodes"][-1]["properties"]["Rate"] = -1
        self.assertEqual(self.request("POST", "/api/project", invalid)[0], 400)
        self.assertEqual(self.request("GET", "/api/project/" + ident)[1], saved)
        self.assertEqual(self.request("GET", "/api/export/" + ident + ".json")[1], saved)
        self.assertEqual(self.request("DELETE", "/api/project/" + ident)[0], 200)
        self.assertEqual(self.request("GET", "/api/project/" + ident)[0], 404)

    def test_catalog_schema_runtime_and_host_origin_guards(self):
        self.assertEqual(self.request("GET", "/api/catalog")[1]["textures"][0]["asset_id"], "1")
        self.assertIn("Beam", self.request("GET", "/api/schema")[1]["classes"])
        self.assertEqual(self.request("GET", "/api/status")[1]["app"], APP)
        self.assertIn(str(self.server.server_port), self.request("GET", "/api/runtime")[1]["bootstrap_url"])
        for headers in ({"Host": "evil.test:" + str(self.server.server_port)}, {"Origin": "https://evil.test"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("POST", "/api/project", project(), headers)[0], 403)
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.request("GET", "/api/schema", headers={"Origin": origin})[0], 200)

    def test_static_allowlist_blocks_secrets_sources_and_traversal(self):
        self.assertEqual(self.request("GET", "/library/images/1.png")[0], 200)
        for path in ("/library/secret.json", "/library/tool/fx_plugin.lua", "/library/source/All.json", "/library/../secret.json", "/library/images/%2e%2e/secret.json", "/library/%2e%2e/secret.json", "/api/project/../../secret"):
            self.assertIn(self.request("GET", path)[0], {400, 403, 404})
        self.assertEqual(self.request("GET", "/bridge/bootstrap.lua")[0], 200)

    def test_external_navigation_can_open_app_without_enabling_cross_site_api(self):
        headers = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        self.assertEqual(self.request("GET", "/", headers=headers)[0], 200)
        self.assertEqual(self.request("GET", "/api/schema", headers=headers)[0], 403)
        self.assertEqual(self.request("POST", "/api/project", project(), headers=headers)[0], 403)

    def test_bridge_requires_single_registered_client_and_matching_ack(self):
        self.assertEqual(self.request("POST", "/api/preview", {"action": "play", "project": project()})[0], 409)
        self.assertEqual(self.request("GET", "/bridge/poll?client_id=unknown")[0], 409)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "studio-a", "studio": "vfx.rbxl", "version": 1})[0], 200)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "studio-b"})[0], 409)
        status, queued = self.request("POST", "/api/preview", {"action": "play", "project": project()})
        self.assertEqual(status, 202)
        self.assertEqual(self.request("GET", "/bridge/poll?client_id=studio-b")[0], 409)
        command = self.request("GET", "/bridge/poll?client_id=studio-a")[1]["command"]
        self.assertEqual(command["id"], queued["id"])
        self.assertEqual(self.request("POST", "/bridge/ack", {"client_id": "studio-a", "id": "unknown", "ok": True})[0], 409)
        self.assertEqual(self.request("POST", "/bridge/ack", {"client_id": "studio-a", "id": command["id"], "ok": True, "details": {"count": 5}})[0], 200)
        self.assertEqual(self.request("GET", "/api/status")[1]["last_ack"]["details"]["count"], 5)
        self.assertIsNone(self.request("GET", "/bridge/poll?client_id=studio-a")[1]["command"])

    def test_new_client_after_timeout_discards_stale_commands(self):
        self.request("POST", "/bridge/hello", {"client_id": "old-studio"})
        self.request("POST", "/api/preview", {"action": "play", "project": project()})
        self.server.client["seen_monotonic"] -= 30
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "new-studio"})[0], 200)
        self.assertIsNone(self.request("GET", "/bridge/poll?client_id=new-studio")[1]["command"])

    def test_runtime_heartbeat_details_are_exposed_for_playback_status(self):
        details = {"playing": True, "paused": False, "elapsed": 0.3}
        self.request("POST", "/bridge/hello", {"client_id": "studio-a", "details": details})
        self.assertEqual(self.request("GET", "/api/status")[1]["runtime"], details)
        details["paused"] = True
        self.request("POST", "/bridge/hello", {"client_id": "studio-a", "details": details})
        self.assertTrue(self.request("GET", "/api/status")[1]["runtime"]["paused"])

    def test_lua_export_quotes_project_data_and_refuses_false_seek(self):
        data = project()
        data["name"] = 'Dataky "]]; error("not code") --'
        status, saved = self.request("POST", "/api/project", data)
        self.assertEqual(status, 201)
        status, source = self.request("GET", "/api/export/" + saved["id"] + ".lua")
        self.assertEqual(status, 200)
        self.assertIn(b"Dataky", source)
        self.assertEqual(self.request("POST", "/api/preview", {"action": "play", "project": data, "time": 1})[0], 422)

    def test_unacknowledged_command_is_redelivered_only_to_same_client(self):
        self.request("POST", "/bridge/hello", {"client_id": "studio-a"})
        self.request("POST", "/api/preview", {"action": "play", "project": project()})
        first = self.request("GET", "/bridge/poll?client_id=studio-a")[1]["command"]
        self.server.pending[first["id"]]["delivered"] -= 3
        second = self.request("GET", "/bridge/poll?client_id=studio-a")[1]["command"]
        self.assertEqual(first, second)
        self.assertEqual(self.request("POST", "/bridge/ack", {"client_id": "studio-a", "id": second["id"], "ok": True})[0], 200)
        self.assertEqual(self.request("GET", "/api/status")[1]["pending"], 0)

    def test_goodbye_only_current_client_and_no_stale_ack_or_delivery(self):
        self.request("POST", "/bridge/hello", {"client_id": "studio-a"})
        self.request("POST", "/api/preview", {"action": "play", "project": project()})
        command = self.request("GET", "/bridge/poll?client_id=studio-a")[1]["command"]
        self.request("POST", "/api/preview", {"action": "stop"})
        self.assertEqual(self.request("POST", "/bridge/goodbye", {"client_id": "studio-b"})[0], 409)
        self.assertTrue(self.request("GET", "/api/status")[1]["connected"])
        self.assertEqual(self.request("POST", "/bridge/goodbye", {"client_id": "studio-a"})[0], 200)
        self.assertFalse(self.request("GET", "/api/status")[1]["connected"])
        self.assertEqual(self.request("POST", "/bridge/ack", {"client_id": "studio-a", "id": command["id"], "ok": True})[0], 409)
        self.assertEqual(self.request("POST", "/bridge/hello", {"client_id": "studio-b"})[0], 200)
        self.assertIsNone(self.request("GET", "/bridge/poll?client_id=studio-b")[1]["command"])

    def test_snapshot_saved_once_and_invalid_png_rejected(self):
        png = tiny_png()
        data = {"image": "data:image/png;base64," + base64.b64encode(png).decode(), "project_id": "test-project", "time": 0.5}
        status, saved = self.request("POST", "/api/snapshot", data)
        self.assertEqual(status, 201)
        self.assertEqual(saved["width"], 1)
        self.assertEqual(self.request("GET", saved["url"])[1], png)
        self.assertEqual(len(self.request("GET", "/api/snapshots")[1]["snapshots"]), 1)
        data["image"] = "data:image/png;base64," + base64.b64encode(b"fake").decode()
        self.assertEqual(self.request("POST", "/api/snapshot", data)[0], 400)
        self.assertEqual(len(list(self.server.snapshots.glob("*.png"))), 1)

    def test_blocks_compose_and_rbxmx_export(self):
        status, listed = self.request("GET", "/api/blocks")
        self.assertEqual(status, 200)
        self.assertIn("shockwave", {block["block"] for block in listed["blocks"]})
        base = project()
        status, composed = self.request("POST", "/api/compose", {"project": base, "blocks": [{"block": "flash", "at": 0.2}]})
        self.assertEqual(status, 200)
        self.assertEqual(len(composed["nodes"]), len(base["nodes"]) + 5)
        self.assertEqual(self.request("POST", "/api/compose", {"blocks": [{"block": "inconnue"}]})[0], 400)
        status, saved = self.request("POST", "/api/project", composed)
        self.assertEqual(status, 201)
        status, model = self.request("GET", "/api/export/" + saved["id"] + ".rbxmx")
        self.assertEqual(status, 200)
        self.assertTrue(model.startswith(b"<?xml"))
        self.assertIn(b'<Item class="ModuleScript"', model)

    def test_emulator_scripts_are_served_and_emulator_snapshots_are_labelled(self):
        for path in ("/emulator.js", "/render.html", "/render.js"):
            self.assertEqual(self.request("GET", path)[0], 200, path)
        image = "data:image/png;base64," + base64.b64encode(tiny_png()).decode()
        status, saved = self.request("POST", "/api/snapshot", {"image": image, "time": 0.25, "source": "emulator"})
        self.assertEqual(status, 201)
        self.assertEqual(saved["capture_source"], "browser-emulator")
        self.assertEqual(saved["time"], 0.25)
        self.assertEqual(self.request("POST", "/api/snapshot", {"image": image, "source": "studio-native"})[0], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
