"""Offline checks for the macro protocol. Never sends native input."""
from pathlib import Path
import json
import tempfile
import unittest
import contextlib
import io
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from types import SimpleNamespace
from unittest.mock import patch
from macro import Calibration, CaptureStore, CommandBus, discovered_tags, capture_name, StopMacro, Macro, COLLECTION_NAMES, make_handler

class MacroTests(unittest.TestCase):
    def test_coordinate_calibration(self):
        calibration = Calibration.from_header({"x": 285.5, "y": 30}, (800, 230))
        self.assertEqual(calibration.screen({"x": 10, "y": 110}), (524, 310))

    def test_command_delivery_and_unknown_reply(self):
        bus = CommandBus()
        identifier, event, holder = bus.submit("layout", tag="Circle")
        self.assertEqual(bus.next(), {"id": identifier, "op": "layout", "tag": "Circle"})
        self.assertTrue(bus.connected.is_set())
        self.assertFalse(event.is_set())
        self.assertTrue(bus.reply({"id": identifier, "ok": True, "result": {"selected": "Circle"}}))
        self.assertTrue(event.is_set())
        self.assertEqual(holder["result"]["selected"], "Circle")
        self.assertFalse(bus.reply({"id": identifier, "ok": True}))
        self.assertEqual(bus.next(), {"op": "idle"})

    def test_chunks_publish_only_complete_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(temporary)
            path = Path(temporary) / "Circle.json"
            path.write_text('{"preserved":true}', encoding="utf-8")
            first = {"label": "Circle", "records": [{"index": 3}], "part": 1, "total_parts": 2, "captured_at": "2026-10-21T12:00:00Z"}
            second = {**first, "records": [{"index": 4}], "part": 2}
            store.save(second)
            self.assertTrue(json.loads(path.read_text())["preserved"])
            store.save(first)
            data = json.loads(path.read_text())
            self.assertEqual(data["records"], [{"index": 3}, {"index": 4}])
            self.assertNotIn("part", data)
            # A new incomplete capture must not mix with previous capture parts.
            new = {**first, "captured_at": "2026-10-21T12:01:00Z", "records": [{"index": 99}]}
            store.save(new)
            self.assertEqual(json.loads(path.read_text())["records"], data["records"])

    def test_dynamic_tag_discovery(self):
        values = ["Circle", "Lightning", "Custom lightning", "Personal", "Recently Used"]
        self.assertEqual(discovered_tags(values), ["Circle", "Custom lightning", "Lightning"])
        self.assertEqual(len(discovered_tags(values, include_personal=True)), 5)
        with self.assertRaises(StopMacro):
            discovered_tags(["All", "Circle"])

    def test_capture_label_and_part_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(temporary)
            store.save({"label": "../outside", "records": []})
            self.assertTrue((Path(temporary) / (capture_name("../outside") + ".json")).exists())
            self.assertEqual(len(list(Path(temporary).glob("*.json"))), 1)
            self.assertTrue(capture_name("Éclair personnalisé"))
            self.assertNotEqual(capture_name("slash/test"), capture_name("slash:test"))
            self.assertNotEqual(capture_name("A B"), capture_name("A_B"))
            self.assertNotEqual(capture_name("Fire").casefold(), capture_name("fire").casefold())
            with self.assertRaises(ValueError):
                store.save({"label": "All", "records": [], "part": 3, "total_parts": 2})
            with self.assertRaises(ValueError):
                store.save({"label": "Circle", "records": [], "active_filter": "crescent, circle"})
            store.save({"label": "All", "records": [], "active_filter": "Tags", "captured_at": "now"})
            self.assertTrue((Path(temporary) / "All.json").exists())


    def test_type_capture_requires_complete_unfiltered_exact_type(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(temporary)
            complete = {"label": "Statics", "records": [{"index": 3}, {"index": 4}],
                        "active_filter": "tags", "active_type": "Statics", "search": "",
                        "max_index": 4, "missing_indexes": [], "captured_at": "now"}
            store.save(complete)
            destination = Path(temporary) / "Statics.json"
            previous = destination.read_bytes()
            for invalid in (
                {**complete, "records": [{"index": 3}], "missing_indexes": [4]},
                {**complete, "records": [{"index": 3}, {"index": 3}]},
                {**complete, "active_type": "Flipbooks"},
                {**complete, "active_filter": "circle"},
            ):
                with self.assertRaises(ValueError):
                    store.save(invalid)
                self.assertEqual(destination.read_bytes(), previous)

    def test_full_flow_captures_types_with_native_inputs_replaced(self):
        fake = SimulatedMacro()
        with patch("macro.time.sleep", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            fake.run()
        self.assertEqual(fake.captures, ["Circle", "Custom tag", "All", "Statics", "Flipbooks"])
        self.assertEqual(fake.restores, 1)
        self.assertEqual(fake.active_type, "All")
        self.assertIsNone(fake.selected)
        self.assertEqual(len(fake.native.clicks), 8)

    def test_type_selection_guard_stops_before_contaminated_capture(self):
        fake = SimulatedMacro(contaminate_type=True)
        with patch("macro.time.sleep", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopMacro):
                fake.run()
        self.assertNotIn("Statics", fake.captures)



    def test_three_collections_use_their_own_tags_and_restore_sidebar(self):
        fake = SimulatedMacro(collections=("textures", "beams", "meshes"))
        with patch("macro.time.sleep", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            fake.run()
        self.assertEqual(fake.capture_ids, [
            ("textures", "Circle"), ("textures", "Custom tag"), ("textures", "All"),
            ("textures", "Statics"), ("textures", "Flipbooks"),
            ("beams", "Arc"), ("beams", "Beam custom"), ("beams", "All"),
            ("meshes", "Mesh custom"), ("meshes", "Ring"), ("meshes", "All")])
        self.assertEqual(fake.manifests, fake.tags_by_collection)
        self.assertEqual(fake.collection, "textures")
        self.assertEqual(fake.restores, 1)
        self.assertEqual(len(fake.native.clicks), 19)

    def test_mesh_only_selection_does_not_capture_texture_types(self):
        fake = SimulatedMacro(collections=("meshes",))
        with patch("macro.time.sleep", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            fake.run()
        self.assertTrue(all(collection == "meshes" for collection, label in fake.capture_ids))
        self.assertEqual(fake.captures, ["Mesh custom", "Ring", "All"])
        self.assertEqual(fake.collection, "textures")

    def test_asset_captures_route_separately_and_reject_partial_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CaptureStore(root / "source", {key: root / key / "source" for key in ("beams", "meshes")})
            store.save({"label": "All", "records": []})
            base = {"label": "All", "first_index": 3, "max_index": 3, "missing_indexes": [],
                    "search": "", "active_filter": "tags", "records": [{"index": 3, "raw_uri": "rbxassetid://123"}],
                    "expected_tags": ["Ring"], "captured_at": "now"}
            for collection in ("beams", "meshes"):
                payload = {**base, "collection": collection, "active_collection": COLLECTION_NAMES[collection]}
                store.save(payload)
                destination = root / collection / "source" / "All.json"
                previous = destination.read_bytes()
                with self.assertRaises(ValueError):
                    store.save({**payload, "max_index": 4, "missing_indexes": [4]})
                self.assertEqual(destination.read_bytes(), previous)
                self.assertEqual(json.loads(destination.read_text())["collection"], collection)
            self.assertEqual(json.loads((root / "source" / "All.json").read_text())["records"], [])



    def test_local_bootstrap_contains_both_helpers_and_requires_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            bus = CommandBus()
            store = CaptureStore(Path(temporary) / "source")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bus, store, "test-token"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/bootstrap?token=wrong")
                self.assertEqual(error.exception.code, 403)
                with urlopen(base + "/bootstrap?token=test-token") as response:
                    body = response.read().decode("utf-8")
                self.assertIn("ZonitoAssetCapture = function", body)
                self.assertIn("ZonitoCapture = function", body)
                self.assertIn('local TOKEN = "test-token"', body)
                self.assertNotIn("__TOKEN__", body)
                self.assertIn("end)();\n(function()", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


class FakeNative:
    def __init__(self, owner):
        self.owner = owner
        self.clicks = []

    def check_cancel(self): pass
    def foreground(self, remember=False): return 1
    def cursor(self): return (100, 10)
    def f8(self): return True
    def validate_panel(self, *args): pass

    def click(self, position):
        self.clicks.append(position)
        for name, point in self.owner.current_points().items():
            if position == (point["x"], point["y"]):
                if name.startswith("@"):
                    self.owner.collection = name[1:]
                    self.owner.selected = None
                elif name in {"All", "Statics", "Flipbooks"} and self.owner.collection == "textures":
                    self.owner.active_type = "Statics, Flipbooks" if self.owner.contaminate_type and name == "Statics" else name
                elif self.owner.selected == name:
                    self.owner.selected = None
                else:
                    assert self.owner.selected is None, "Previous tag was not cleared"
                    self.owner.selected = name
                return
        raise AssertionError("Unknown fake click point")


class SimulatedMacro(Macro):
    """Exercise orchestration without constructing WindowsInput or calling Studio."""
    def __init__(self, contaminate_type=False, collections=("textures",)):
        self.collection = "textures"
        self.selected = None
        self.active_type = "All"
        self.contaminate_type = contaminate_type
        self.captures, self.capture_ids, self.manifests = [], [], {}
        self.restores = 0
        self.tags_by_collection = {"textures": ["Circle", "Custom tag"], "beams": ["Arc", "Beam custom"], "meshes": ["Mesh custom", "Ring"]}
        connected = threading.Event()
        connected.set()
        super().__init__(SimpleNamespace(connected=connected), FakeNative(self), collections=collections)

    def current_points(self):
        points = {"@textures": {"x": 210, "y": 30}, "@beams": {"x": 220, "y": 30}, "@meshes": {"x": 230, "y": 30}}
        if self.collection == "textures":
            points.update({"All": {"x": 10, "y": 30}, "Statics": {"x": 20, "y": 30}, "Flipbooks": {"x": 30, "y": 30}})
        points.update({name: {"x": 60 + index * 10, "y": 100} for index, name in enumerate(self.tags_by_collection[self.collection])})
        return points

    def command(self, op, **fields):
        selected = self.selected or "Tags"
        if fields.get("collection"):
            assert fields["collection"] == self.collection
        common = {"active_collection": COLLECTION_NAMES[self.collection], "collection": self.collection,
                  "selected": selected, "search": "", "active_type": self.active_type if self.collection == "textures" else None}
        if op == "layout":
            points = self.current_points()
            result = {**common, "header": {"x": 100, "y": 10},
                      "width": 300, "height": 400, "main_origin": {"x": 0, "y": 0},
                      "tags": self.tags_by_collection[self.collection] + ["Personal", "Recently Used"],
                      "type_buttons": {key: value for key, value in points.items() if key in {"All", "Statics", "Flipbooks"}},
                      "collection_buttons": {key[1:]: value for key, value in points.items() if key.startswith("@")}}
            if self.collection == "textures": result["all_type"] = points["All"]
            if fields.get("tag"): result["button"] = points[fields["tag"]]
            if fields.get("texture_type"): result["type_button"] = points[fields["texture_type"]]
            if fields.get("target_collection"): result["collection_button"] = points["@" + fields["target_collection"]]
            return result
        if op == "capture":
            label = fields["label"]
            type_capture = self.collection == "textures" and label in {"Statics", "Flipbooks"}
            assert selected == ("Tags" if label == "All" or type_capture else label)
            if self.collection == "textures": assert self.active_type == (label if type_capture else "All")
            if label == "All": self.manifests[self.collection] = fields["expected_tags"]
            self.captures.append(label)
            self.capture_ids.append((self.collection, label))
            return {"started": label, "collection": self.collection}
        if op == "status":
            return {**common, "capture": {"status": "done", "collection": self.collection, "label": self.captures[-1], "count": 10, "missing": 0}}
        if op == "restore":
            self.restores += 1
            return {"restored": True}
        raise AssertionError(op)

if __name__ == "__main__":
    unittest.main()
