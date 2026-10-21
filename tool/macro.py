"""User-run Windows macro for the ZonitoVisuals tag catalogue.

Native clicks are deliberately confined to the foreground vfx.rbxl Studio window.
F8 calibrates the plugin coordinate origin; Escape stops the macro.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import argparse
import json
import hashlib
import re
import queue
import secrets
import subprocess
import sys
import threading
import time

SPECIAL_TAGS = {"personal", "recently used"}
TYPE_CAPTURES = ("Statics", "Flipbooks")
COLLECTIONS = ("textures", "beams", "meshes")
COLLECTION_NAMES = {"textures": "Textures", "beams": "Beams", "meshes": "Meshes"}
# Preserve established source filenames; this set does not limit tag discovery.
BASELINE_LABELS = {"Statics", "Flipbooks", "All", "Personal", "Recently Used", "Circle", "Crescent", "Effect", "Fire", "Flare", "GUI", "Grid", "Ground", "Impact", "Lightning", "Smoke", "Spec", "Star", "Swirl", "Text", "Water", "Wind", "Slash", "Other"}

def discovered_tags(values, include_personal=False, collection="textures"):
    if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
        raise StopMacro("The plugin returned invalid tag names")
    reserved = {"all", "statics", "flipbooks"} if collection == "textures" else {"all"}
    if any(value.casefold() in reserved for value in values):
        raise StopMacro("A custom tag conflicts with a reserved All/Statics/Flipbooks capture label; rename that custom tag first")
    tags = sorted(set(values), key=str.casefold)
    return [value for value in tags if include_personal or value.casefold() not in SPECIAL_TAGS]

def capture_name(label):
    if not isinstance(label, str) or not label.strip() or len(label) > 120 or any(ord(c) < 32 for c in label):
        raise ValueError("Invalid capture label")
    name = re.sub(r'[<>:"/\\|?*]', "_", label).replace(" ", "_").rstrip(". ")
    if not name or name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}:
        name = "tag_" + name
    if label not in BASELINE_LABELS:
        name += "-" + hashlib.sha256(label.encode()).hexdigest()[:8]
    return name
TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parent

class StopMacro(RuntimeError):
    pass

@dataclass(frozen=True)
class Calibration:
    x: float
    y: float

    @classmethod
    def from_header(cls, header, cursor):
        return cls(cursor[0] - float(header["x"]), cursor[1] - float(header["y"]))

    def screen(self, point):
        return round(self.x + float(point["x"])), round(self.y + float(point["y"]))

class CommandBus:
    def __init__(self):
        self.commands = queue.Queue()
        self.pending = {}
        self.lock = threading.Lock()
        self.serial = 0
        self.connected = threading.Event()

    def submit(self, op, **fields):
        with self.lock:
            self.serial += 1
            event = threading.Event()
            holder = {}
            self.pending[self.serial] = event, holder
            command = dict(id=self.serial, op=op, **fields)
            self.commands.put(command)
            return self.serial, event, holder

    def reply(self, result):
        with self.lock:
            pending = self.pending.pop(result.get("id"), None)
            if pending is None:
                return False
            event, holder = pending
            holder.update(result)
            event.set()
            return True

    def next(self):
        self.connected.set()
        try:
            return self.commands.get_nowait()
        except queue.Empty:
            return {"op": "idle"}

class CaptureStore:
    """Publish complete capture generations into separate collection directories."""
    def __init__(self, source, collection_sources=None):
        self.source = Path(source)
        self.sources = {"textures": self.source}
        self.sources.update({key: Path(value) for key, value in (collection_sources or {}).items()})
        self.source.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def save(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError("Invalid capture records")
        collection = data.get("collection", "textures")
        if collection not in self.sources or collection not in COLLECTIONS:
            raise ValueError("Unknown capture collection")
        source = self.sources[collection]
        source.mkdir(parents=True, exist_ok=True)
        label = data.get("label")
        name = capture_name(label)
        type_capture = collection == "textures" and label in TYPE_CAPTURES
        expected_filter = "tags" if label == "All" or type_capture else label.casefold()
        if "active_filter" in data and str(data["active_filter"]).casefold() != expected_filter:
            raise ValueError("Capture active filter does not match its label")
        if collection == "textures":
            expected_type = label if type_capture else "All"
            if "active_type" in data and data["active_type"] != expected_type:
                raise ValueError("Capture active type does not match its label")
        elif data.get("active_collection") != COLLECTION_NAMES[collection] or data.get("first_index") != 3:
            raise ValueError("Asset capture collection or first index is invalid")
        part, total = int(data.get("part", 1)), int(data.get("total_parts", 1))
        if not 1 <= part <= total <= 200:
            raise ValueError("Invalid capture part")
        with self.lock:
            if total > 1:
                stamp = str(data.get("captured_at", ""))
                if not stamp or len(stamp) > 100:
                    raise ValueError("Missing capture timestamp")
                generation = hashlib.sha256(stamp.encode()).hexdigest()[:16]
                directory = source / ".capture_parts" / f"{name}-{generation}"
                directory.mkdir(parents=True, exist_ok=True)
                self._atomic(directory / f"{part:03}.json", data)
                pieces = []
                for index in range(1, total + 1):
                    path = directory / f"{index:03}.json"
                    if not path.exists():
                        return str(len(data["records"]))
                    piece = json.loads(path.read_text(encoding="utf-8"))
                    if piece.get("label") != label or piece.get("collection", "textures") != collection or piece.get("captured_at") != stamp or int(piece.get("total_parts", 0)) != total:
                        raise ValueError("Mismatched capture parts")
                    pieces.append(piece)
                combined = dict(pieces[0])
                combined["records"] = [record for piece in pieces for record in piece["records"]]
            else:
                combined = dict(data)
            combined.pop("part", None)
            combined.pop("total_parts", None)
            if type_capture:
                self._validate_type_capture(combined)
            elif collection != "textures":
                if str(combined.get("active_filter", "")).casefold() != expected_filter or combined.get("search") != "":
                    raise ValueError("Asset capture requires exact tags and no search")
                self._validate_complete_indexes(combined)
            self._atomic(source / f"{name}.json", combined)
            return str(len(combined["records"]))

    @staticmethod
    def _validate_complete_indexes(data):
        if data.get("missing_indexes") != []:
            raise ValueError("Incomplete capture")
        maximum = data.get("max_index")
        first = data.get("first_index", 3)
        indexes = [record.get("index") for record in data["records"] if isinstance(record, dict)]
        if first != 3 or not isinstance(maximum, int) or not 2 <= maximum <= 1_000_000 or len(indexes) != len(data["records"]) or any(type(index) is not int for index in indexes):
            raise ValueError("Invalid capture indexes")
        if sorted(indexes) != list(range(first, maximum + 1)):
            raise ValueError("Missing or duplicated capture indexes")

    @staticmethod
    def _validate_type_capture(data):
        label = data["label"]
        if data.get("active_type") != label or str(data.get("active_filter", "")).casefold() != "tags" or data.get("search") != "":
            raise ValueError("Type capture requires its exact active type, no tag, and no search")
        CaptureStore._validate_complete_indexes(data)

    @staticmethod
    def _atomic(path, data):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def make_handler(bus, store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def route(self):
            parsed = urlsplit(self.path)
            if parse_qs(parsed.query).get("token") != [token]:
                self.send_error(403)
                return None
            return parsed.path

        def respond(self, value, content_type="application/json"):
            content = value.encode("utf-8") if isinstance(value, str) else json.dumps(value).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            path = self.route()
            if path == "/bootstrap":
                harvest = (TOOL / "harvest_ui.lua").read_text(encoding="utf-8-sig")
                assets = (TOOL / "harvest_assets.lua").read_text(encoding="utf-8-sig")
                bridge = (TOOL / "bridge.lua").read_text(encoding="utf-8-sig").replace("__TOKEN__", token)
                self.respond("(function()\n" + harvest + "\nend)();\n(function()\n" + assets + "\nend)();\n" + bridge, "text/plain; charset=utf-8")
            elif path == "/next":
                self.respond(bus.next())
            elif path is not None:
                self.send_error(404)

        def do_POST(self):
            path = self.route()
            if path is None:
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2_000_000:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if path == "/reply":
                    self.respond({"accepted": bus.reply(data)})
                elif path == "/capture":
                    self.respond(store.save(data), "text/plain")
                else:
                    self.send_error(404)
            except (ValueError, TypeError, KeyError) as exc:
                self.send_error(400, str(exc))
    return Handler

class WindowsInput:
    def __init__(self, title_fragment="vfx.rbxl"):
        if sys.platform != "win32":
            raise StopMacro("This macro requires Windows")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        self.user.SetProcessDPIAware()
        self.title_fragment = title_fragment.casefold()
        self.hwnd = None
        self.original_window_rect = None

    def cancelled(self):
        return bool(self.user.GetAsyncKeyState(0x1B) & 0x8000)

    def check_cancel(self):
        if self.cancelled():
            raise StopMacro("Stopped with Escape")

    def foreground(self, remember=False):
        hwnd = self.user.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(1024)
        self.user.GetWindowTextW(hwnd, title, len(title))
        value = title.value.casefold()
        if self.title_fragment not in value or "roblox studio" not in value:
            raise StopMacro("Keep the intended vfx.rbxl Roblox Studio window in the foreground")
        if self.hwnd is not None and hwnd != self.hwnd:
            raise StopMacro("The foreground Studio window changed")
        if remember:
            self.hwnd = hwnd
        return hwnd

    def cursor(self):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise StopMacro("Cannot read mouse position")
        return point.x, point.y

    def f8(self):
        return bool(self.user.GetAsyncKeyState(0x77) & 0x8000)

    def validate_panel(self, calibration, width, height):
        hwnd = self.foreground()
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise StopMacro("Cannot locate Studio window")
        bounds = (rect.left, rect.top, rect.right, rect.bottom)
        self.original_window_rect = bounds
        x1, y1 = calibration.screen({"x": 0, "y": 0})
        x2, y2 = calibration.screen({"x": width, "y": height})
        left, top = self.user.GetSystemMetrics(76), self.user.GetSystemMetrics(77)
        right, bottom = left + self.user.GetSystemMetrics(78), top + self.user.GetSystemMetrics(79)
        if not (max(left, rect.left) <= x1 < x2 <= min(right, rect.right) and max(top, rect.top) <= y1 < y2 <= min(bottom, rect.bottom)):
            raise StopMacro("Calibrated plugin rectangle is outside the Studio window or desktop")

    def click(self, position):
        self.check_cancel()
        hwnd = self.foreground()
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise StopMacro("Cannot locate Studio window")
        if self.original_window_rect != (rect.left, rect.top, rect.right, rect.bottom):
            raise StopMacro("The Studio window moved or resized; recalibrate before continuing")
        x, y = position
        left, top = self.user.GetSystemMetrics(76), self.user.GetSystemMetrics(77)
        right, bottom = left + self.user.GetSystemMetrics(78), top + self.user.GetSystemMetrics(79)
        if not (left <= x < right and top <= y < bottom and rect.left <= x < rect.right and rect.top <= y < rect.bottom):
            raise StopMacro("Target point is outside the Studio window or desktop")
        if not self.user.SetCursorPos(x, y):
            raise StopMacro("Cannot move mouse")
        time.sleep(0.04)
        self.foreground()
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        self.user.mouse_event(0x0004, 0, 0, 0, 0)

class Macro:
    def __init__(self, bus, native, include_personal=False, collections=COLLECTIONS):
        self.bus, self.native = bus, native
        self.include_personal = include_personal
        self.collections = tuple(dict.fromkeys(collections))
        if not self.collections or any(value not in COLLECTIONS for value in self.collections):
            raise ValueError("Choose textures, beams and/or meshes")
        self.calibration = self.dimensions = self.main_origin = None

    def command(self, op, timeout=20, check_cancel=True, **fields):
        _, event, holder = self.bus.submit(op, **fields)
        deadline = time.monotonic() + timeout
        while not event.wait(0.1):
            if check_cancel:
                self.native.check_cancel()
            if time.monotonic() > deadline:
                raise StopMacro("Studio bridge did not respond; re-run the bootstrap line if needed")
        if not holder.get("ok"):
            raise StopMacro(str(holder.get("error", "Bridge error")))
        return holder.get("result", {})

    def click(self, layout, key):
        if self.calibration is None:
            raise StopMacro("Calibration is missing")
        if self.dimensions != (layout.get("width"), layout.get("height")) or self.main_origin != layout.get("main_origin"):
            raise StopMacro("The plugin panel moved or resized; recalibrate before continuing")
        point = layout[key]
        if not (0 <= float(point["x"]) < layout["width"] and 0 <= float(point["y"]) < layout["height"]):
            raise StopMacro("Target control is outside the plugin content rectangle")
        self.native.click(self.calibration.screen(point))
        time.sleep(0.25)

    @staticmethod
    def verify(result, collection, label="All"):
        if result.get("active_collection") != COLLECTION_NAMES[collection] or result.get("collection") != collection:
            raise StopMacro("The active collection changed")
        type_capture = collection == "textures" and label in TYPE_CAPTURES
        expected_filter = "Tags" if label == "All" or type_capture else label
        if str(result.get("selected", "")).casefold() != expected_filter.casefold() or result.get("search"):
            raise StopMacro("The tag or search filter does not match the requested capture")
        if collection == "textures" and result.get("active_type") != (label if type_capture else "All"):
            raise StopMacro("The texture type did not activate exclusively")

    def switch_collection(self, collection):
        layout = self.command("layout", target_collection=collection)
        if layout.get("collection") != collection:
            self.click(layout, "collection_button")
            layout = self.command("layout", collection=collection)
        if layout.get("active_collection") != COLLECTION_NAMES[collection] or layout.get("collection") != collection:
            raise StopMacro("The collection sidebar click did not select the intended panel")
        if str(layout.get("selected", "")).casefold() != "tags" or layout.get("search"):
            raise StopMacro("Clear the tag and search filters for this collection, then restart")
        return layout

    def wait_capture(self, collection, label):
        deadline, last_log = time.monotonic() + 900, 0.0
        while time.monotonic() < deadline:
            result = self.command("status", collection=collection)
            self.verify(result, collection, label)
            state = result.get("capture", {})
            if state.get("status") == "done":
                if state.get("label") != label or state.get("collection", collection) != collection:
                    raise StopMacro("Unexpected completed capture identity")
                if state.get("missing", 0):
                    raise StopMacro(f"{collection}/{label}: missing indexes; inspect the preserved capture")
                print(f"  {collection}/{label}: {state.get('count', 0)} entries saved", flush=True)
                return
            if state.get("status") == "error":
                raise StopMacro(str(state.get("error")))
            if time.monotonic() - last_log > 10:
                print(f"  {collection}/{label}: {state.get('count', 0)} entries read...", flush=True)
                last_log = time.monotonic()
            time.sleep(0.3)
        raise StopMacro(f"Timeout capturing {collection}/{label}")

    def capture(self, collection, label, tags):
        self.verify(self.command("layout", collection=collection), collection, label)
        print(f"Capturing {collection}/{label}...", flush=True)
        self.command("capture", collection=collection, label=label, expected_tags=tags)
        self.wait_capture(collection, label)

    def run_collection(self, collection):
        layout = self.switch_collection(collection)
        tags = discovered_tags(layout.get("tags"), self.include_personal, collection)
        print(f"{COLLECTION_NAMES[collection]}: {len(tags)} discovered tags: {', '.join(tags)}", flush=True)
        if collection == "textures":
            if not {"All", *TYPE_CAPTURES}.issubset(layout.get("type_buttons", {})):
                raise StopMacro("Expected All, Statics and Flipbooks type controls are missing")
            self.click(layout, "all_type")
            self.verify(self.command("layout", collection=collection), collection)
        previous = None
        for label in (*tags, "All"):
            if previous:
                revealed = self.command("layout", collection=collection, tag=previous)
                self.click(revealed, "button")
                self.verify(self.command("layout", collection=collection), collection)
            if label != "All":
                revealed = self.command("layout", collection=collection, tag=label)
                self.click(revealed, "button")
            self.capture(collection, label, tags)
            previous = label if label != "All" else None
        if collection == "textures":
            for label in TYPE_CAPTURES:
                revealed = self.command("layout", collection=collection, texture_type=label)
                self.click(revealed, "type_button")
                self.capture(collection, label, tags)
            revealed = self.command("layout", collection=collection, texture_type="All")
            self.click(revealed, "type_button")
            self.verify(self.command("layout", collection=collection), collection)

    def run(self):
        print("\nPaste the bootstrap line in Studio and keep a catalogue tab visible.", flush=True)
        while not self.bus.connected.wait(0.1):
            self.native.check_cancel()
        initial = self.command("layout")
        if initial.get("collection") not in COLLECTIONS:
            raise StopMacro("Open Textures, Beams or Meshes first")
        if str(initial.get("selected", "")).casefold() != "tags" or initial.get("search"):
            raise StopMacro("First clear the active tag and search filters, then restart")
        print("Hover precisely over the center of the Tags header in Studio and press F8. Escape cancels.", flush=True)
        while not self.native.f8():
            self.native.check_cancel()
            time.sleep(0.05)
        self.native.foreground(remember=True)
        calibration_cursor = self.native.cursor()
        fresh = self.command("layout")
        if any(fresh.get(key) != initial.get(key) for key in ("header", "width", "height", "main_origin", "collection")):
            raise StopMacro("The plugin layout changed while awaiting F8; restart calibration")
        if str(fresh.get("selected", "")).casefold() != "tags" or fresh.get("search"):
            raise StopMacro("Filters changed while awaiting calibration")
        initial = fresh
        original_collection = initial["collection"]
        self.calibration = Calibration.from_header(initial["header"], calibration_cursor)
        self.dimensions = (initial["width"], initial["height"])
        self.main_origin = initial.get("main_origin")
        self.native.validate_panel(self.calibration, *self.dimensions)
        for collection in self.collections:
            self.run_collection(collection)
        self.switch_collection(original_collection)
        self.command("restore")
        print("\nSelected collection captures are saved. Updating local catalogues...", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-title", default="vfx.rbxl", help="Studio place title fragment, defaults to vfx.rbxl")
    parser.add_argument("--include-personal", action="store_true", help="Also capture Personal and Recently Used filters")
    parser.add_argument("--collections", nargs="+", choices=COLLECTIONS, default=list(COLLECTIONS), help="Collections to recapture (default: all three)")
    options = parser.parse_args()
    bus = CommandBus()
    token = secrets.token_hex(16)
    store = CaptureStore(ROOT / "source", {key: ROOT / key / "source" for key in ("beams", "meshes")})
    try:
        native = WindowsInput(options.window_title)
        server = ThreadingHTTPServer(("127.0.0.1", 48754), make_handler(bus, store, token))
    except (OSError, StopMacro) as exc:
        print(f"Cannot start macro: {exc}", flush=True)
        return 1
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Local ZonitoVisuals macro - keep Studio visible and do not move/resize its panels.")
    print("In Studio: clear tags/search, select Textures, then paste this ONE line in the command bar:\n")
    print(f"loadstring(game:GetService('HttpService'):GetAsync('http://127.0.0.1:48754/bootstrap?token={token}'))()", flush=True)
    macro = Macro(bus, native, include_personal=options.include_personal, collections=options.collections)
    try:
        macro.run()
        commands = []
        if "textures" in macro.collections:
            commands.append([sys.executable, str(TOOL / "catalog.py"), "--workers", "12"])
        extras = [collection for collection in macro.collections if collection != "textures"]
        if extras:
            commands.append([sys.executable, str(TOOL / "asset_catalog.py"), "--collections", *extras, "--workers", "12"])
        for command in commands:
            if not Path(command[1]).is_file():
                raise StopMacro(f"Captures saved, but {Path(command[1]).name} is missing")
            code = subprocess.run(command, cwd=str(ROOT), check=False).returncode
            if code:
                return code
        return 0
    except (StopMacro, KeyboardInterrupt) as exc:
        print(f"\nMacro stopped: {exc}", flush=True)
        if bus.connected.is_set():
            try:
                macro.command("restore", timeout=3, check_cancel=False)
            except (StopMacro, KeyboardInterrupt):
                pass
        print("Completed source files are preserved. Clear the active tag manually before restarting.", flush=True)
        return 1
    finally:
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    raise SystemExit(main())
