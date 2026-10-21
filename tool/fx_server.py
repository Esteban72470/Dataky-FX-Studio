"""Dataky FX Studio: local editor, validated recipes and native Studio bridge.

Uses Python's standard library only. Binds exclusively to IPv4 loopback. The
browser edits JSON; the bridge executes the fixed native runtime, never code
supplied by a project. Run: python tool/fx_server.py [--no-browser] [--port 48754].
"""
from argparse import ArgumentParser
import base64
import binascii
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import mimetypes
import os
from pathlib import Path
import re
import struct
import tempfile
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import webbrowser
import zlib

if __package__:
    from .fx_schema import SCHEMA, ValidationError, identifier, number, text, validate_project
else:
    from fx_schema import SCHEMA, ValidationError, identifier, number, text, validate_project

APP = "Dataky FX Studio"
CURRENT_BRIDGE_VERSION = 2
LIBRARY = Path(__file__).resolve().parent.parent
CLIENT_TIMEOUT = 20
FRAME_TIMEOUT = 5
MAX_BODY = 12_000_000


class APIError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".dataky-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, data):
    atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def decode_png_data_url(image, max_bytes=8_000_000):
    if not isinstance(image, str) or not image.startswith("data:image/png;base64,"):
        raise ValidationError("Capture data:image/png;base64 requise")
    encoded = image.split(",", 1)[1]
    if len(encoded) > ((max_bytes + 2) // 3) * 4:
        raise APIError(413, "Image PNG trop volumineuse")
    try:
        png = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("Capture base64 invalide") from exc
    if len(png) > max_bytes:
        raise APIError(413, "Image PNG trop volumineuse")
    width, height = png_dimensions(png)
    return png, width, height


def sibling(name):
    return importlib.import_module((__package__ + "." if __package__ else "") + name)


def confined(base, relative):
    base = base.resolve()
    candidate = (base / relative).resolve()
    if candidate == base or not candidate.is_relative_to(base):
        raise APIError(403, "Chemin interdit")
    return candidate


def png_dimensions(data):
    """Validate browser canvas PNG including CRC and bounded decoded scanlines."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8_000_000:
        raise ValidationError("Image PNG valide de 8 Mo maximum requise")
    pos, header, compressed, ended, palette = 8, None, bytearray(), False, False
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValidationError("PNG tronqué")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        end = pos + 12 + length
        if end > len(data):
            raise ValidationError("Bloc PNG tronqué")
        kind, payload = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length:end])[0]
        if (binascii.crc32(kind + payload) & 0xffffffff) != crc:
            raise ValidationError("Somme de contrôle PNG invalide")
        if header is None and kind != b"IHDR":
            raise ValidationError("En-tête PNG absent")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValidationError("En-tête PNG invalide")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 8_000_000):
                raise ValidationError("PNG limité à 8192 pixels par côté et 8 mégapixels")
            if color not in depths or depth not in depths[color] or compression != 0 or filtering != 0 or interlace != 0:
                raise ValidationError("Format PNG non pris en charge ; utiliser une capture PNG non entrelacée")
            header = (width, height, depth, color)
        elif kind == b"PLTE":
            palette = 0 < length <= 768 and length % 3 == 0
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            if length != 0 or end != len(data):
                raise ValidationError("Fin PNG invalide")
            ended = True
            break
        elif kind[:1].isupper() and kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"}:
            raise ValidationError("Bloc PNG critique inconnu")
        pos = end
    if not ended or not header or not compressed:
        raise ValidationError("PNG incomplet")
    width, height, depth, color = header
    if color == 3 and not palette:
        raise ValidationError("Palette PNG absente")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    row = (width * channels * depth + 7) // 8 + 1
    expected = row * height
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ValidationError("Données PNG invalides") from exc
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValidationError("Taille décodée PNG invalide")
    if any(decoded[offset] > 4 for offset in range(0, expected, row)):
        raise ValidationError("Filtre PNG invalide")
    return width, height


class FXServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address=("127.0.0.1", 48754), library=LIBRARY):
        if address[0] != "127.0.0.1":
            raise ValueError("Dataky FX Studio accepte uniquement 127.0.0.1")
        self.library = Path(library).resolve()
        self.editor = self.library / "editor"
        self.projects = self.editor / "projects"
        self.snapshots = self.editor / "snapshots"
        self.lock = threading.RLock()
        self.client = None
        self.commands = deque()
        self.pending = {}
        self.last_ack = None
        self.last_error = None
        self.preview = {"enabled": False, "available": False, "permission": False, "error": None, "fps": 0}
        self.latest_frame = None
        self.frame_sequence = 0
        self.capture_generation = 0
        self.preview_project_id = None
        self.preview_project_name = None
        super().__init__(address, Handler)

    def connected(self):
        with self.lock:
            if self.client and time.monotonic() - self.client["seen_monotonic"] >= CLIENT_TIMEOUT:
                self.client = None
                self.commands.clear()
                self.pending.clear()
                self.invalidate_preview(disable=True)
            return self.client is not None

    def invalidate_preview(self, disable=False):
        self.latest_frame = None
        self.capture_generation += 1
        if disable:
            self.preview["enabled"] = False

    def active_frame(self):
        if not self.connected() or not self.preview["enabled"]:
            self.latest_frame = None
            return None
        if self.latest_frame and time.monotonic() - self.latest_frame["received"] > FRAME_TIMEOUT:
            self.latest_frame = None
        return self.latest_frame

    def preview_status(self):
        with self.lock:
            frame = self.active_frame()
            metadata = {**frame["metadata"], "age": round(time.monotonic() - frame["received"], 3)} if frame else None
            return {**self.preview, "frame": metadata, "generation": self.capture_generation}

    def require_active_client(self, client_id):
        identifier(client_id, "client_id")
        if not self.connected() or self.client["client_id"] != client_id:
            raise APIError(409, "Cette capture ne provient pas du pont Studio actif")

    def status(self):
        with self.lock:
            connected = self.connected()
            client = self.client or {}
            return {"app": APP, "version": 1, "connected": connected,
                    "last_seen": client.get("last_seen"), "studio": client.get("studio"),
                    "client_id": client.get("client_id"), "bridge_version": client.get("version"),
                    "bridge_capabilities": client.get("capabilities", {}),
                    "bridge_update_required": bool(client and not client.get("capabilities", {}).get("native_preview")),
                    "runtime": client.get("details"),
                    "last_error": self.last_error, "last_ack": self.last_ack,
                    "queued": len(self.commands), "pending": len(self.pending),
                    "preview": self.preview_status(),
                    "port": self.server_port, "origin": f"http://127.0.0.1:{self.server_port}"}

    def touch_client(self, client_id, hello=None):
        identifier(client_id, "client_id")
        capabilities = {}
        if hello is not None:
            capabilities = hello.get("capabilities", {})
            if not isinstance(capabilities, dict):
                raise ValidationError("capabilities doit être un objet")
            allowed = {"native_preview", "capture_permission", "capture_permission_request", "capture_context", "commands"}
            if set(capabilities) - allowed:
                raise ValidationError("Capacité de pont inconnue")
            for flag in ("native_preview", "capture_permission", "capture_permission_request"):
                if flag in capabilities and not isinstance(capabilities[flag], bool):
                    raise ValidationError("capabilities." + flag + " doit être un booléen")
            if "capture_context" in capabilities and capabilities["capture_context"] not in {"plugin", "command_bar"}:
                raise ValidationError("capabilities.capture_context doit être plugin ou command_bar")
            if "commands" in capabilities:
                commands = capabilities["commands"]
                if not isinstance(commands, list) or len(commands) > 32:
                    raise ValidationError("capabilities.commands doit être une liste de 32 actions maximum")
                for command in commands:
                    text(command, "capabilities.commands", 80, False)
        with self.lock:
            if self.connected() and self.client["client_id"] != client_id:
                raise APIError(409, "Une autre fenêtre Studio est déjà connectée. Déconnecter son pont ou attendre 20 secondes.")
            if hello is not None:
                if not self.client or self.client["client_id"] != client_id:
                    # Never deliver old commands to another Studio document.
                    self.commands.clear()
                    self.pending.clear()
                    self.invalidate_preview(disable=True)
                    self.preview_project_id = None
                    self.preview_project_name = None
                    self.last_error = None
                    self.last_ack = None
                self.client = {"client_id": client_id, "studio": text(hello.get("studio", "Roblox Studio"), "studio", 512),
                               "version": text(str(hello.get("version", "1")), "version", 80),
                               "capabilities": capabilities,
                               "details": hello.get("details"),
                               "last_seen": now_iso(), "seen_monotonic": time.monotonic()}
            else:
                if not self.client or self.client["client_id"] != client_id:
                    raise APIError(409, "Enregistrer le pont avec /bridge/hello avant de recevoir une commande")
                self.client["last_seen"] = now_iso()
                self.client["seen_monotonic"] = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    server_version = "DatakyFX/1"

    def log_message(self, fmt, *args):
        # Polling does not flood the terminal. Failures still appear.
        if len(args) > 1 and str(args[1]) not in {"200", "201", "204", "304"}:
            super().log_message(fmt, *args)

    def guard(self):
        host = self.headers.get("Host", "")
        parsed_host = urlsplit("http://" + host)
        try:
            valid_host = parsed_host.hostname in {"127.0.0.1", "localhost"} and parsed_host.port == self.server.server_port
        except ValueError:
            valid_host = False
        if not valid_host or parsed_host.path or parsed_host.username or parsed_host.password:
            raise APIError(403, "Hôte local invalide")
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            try:
                valid_origin = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == self.server.server_port and not parsed.path and not parsed.query and not parsed.fragment and not parsed.username
            except ValueError:
                valid_origin = False
            if not valid_origin:
                raise APIError(403, "Origine externe refusée")
        navigation = (self.command == "GET" and urlsplit(self.path).path in {"/", "/index.html", "/library/catalogue.html"}
                      and self.headers.get("Sec-Fetch-Mode") == "navigate"
                      and self.headers.get("Sec-Fetch-Dest") == "document")
        if self.headers.get("Sec-Fetch-Site") == "cross-site" and not navigation:
            raise APIError(403, "Requête intersite refusée")

    def send_json(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_bytes(self, data, content_type, status=200, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        if content_type.startswith("text/html"):
            scripts = "'self' 'unsafe-inline'" if self.path.split("?", 1)[0] == "/library/catalogue.html" else "'self'"
            self.send_header("Content-Security-Policy", f"default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src {scripts}; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self, limit=4_000_000):
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "Transfert par blocs non pris en charge")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "Content-Length invalide")
        if not 0 < length <= min(limit, MAX_BODY):
            raise APIError(413, "Corps JSON absent ou trop volumineux")
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "Content-Type application/json requis")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise APIError(400, "Corps tronqué")
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Champ JSON dupliqué : " + key)
                result[key] = value
            return result
        try:
            result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                                parse_constant=lambda constant: (_ for _ in ()).throw(ValueError("Nombre non fini interdit")))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise APIError(400, "JSON invalide : " + str(exc)) from exc
        if not isinstance(result, dict):
            raise APIError(400, "Objet JSON requis")
        return result

    def file(self, path):
        if not path.is_file():
            raise APIError(404, "Fichier introuvable")
        self.send_bytes(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

    def project_path(self, ident):
        identifier(ident, "id")
        return confined(self.server.projects, ident + ".json")

    def load_project(self, ident):
        path = self.project_path(ident)
        if not path.is_file():
            raise APIError(404, "Projet introuvable")
        return validate_project(json.loads(path.read_text(encoding="utf-8")))

    def dispatch(self):
        self.guard()
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if "\x00" in path or "\\" in path:
            raise APIError(403, "Chemin interdit")
        if self.command == "GET":
            self.get(path, parse_qs(parsed.query))
        elif self.command == "POST":
            self.post(path)
        elif self.command == "DELETE":
            self.delete(path)
        else:
            raise APIError(405, "Méthode non prise en charge")

    def handle_api(self):
        try:
            self.dispatch()
        except APIError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except ValidationError as exc:
            self.send_json({"error": str(exc)}, 400)
        except (ValueError, KeyError, TypeError, RecursionError) as exc:
            self.send_json({"error": "Données invalides : " + str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.server.last_error = str(exc)
            self.send_json({"error": "Erreur locale : " + str(exc)}, 500)

    do_GET = do_POST = do_DELETE = do_OPTIONS = handle_api

    def get(self, path, query):
        server = self.server
        if path in {"/", "/index.html", "/app.js", "/curves.js", "/emulator.js", "/render.html", "/render.js", "/styles.css"}:
            self.file(confined(server.editor, "index.html" if path in {"/", "/index.html"} else path[1:]))
        elif path == "/api/schema":
            self.send_json(SCHEMA)
        elif path == "/api/catalog":
            result = {}
            for key, rel in (("textures", "textures.json"), ("beams", "beams/assets.json"), ("meshes", "meshes/assets.json")):
                source = confined(server.library, rel)
                result[key] = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else []
            self.send_json(result)
        elif path == "/api/projects":
            projects = []
            if server.projects.is_dir():
                for file in server.projects.glob("*.json"):
                    try:
                        project = self.load_project(file.stem)
                        projects.append({"id": file.stem, "name": project["name"], "updated_at": datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")})
                    except (ValueError, OSError):
                        continue
            self.send_json({"projects": sorted(projects, key=lambda item: item["updated_at"], reverse=True)})
        elif path.startswith("/api/project/"):
            self.send_json(self.load_project(path.removeprefix("/api/project/")))
        elif path == "/api/status":
            self.send_json(server.status())
        elif path == "/api/preview/frame":
            self.send_json(server.preview_status())
        elif path == "/api/preview/frame.png":
            with server.lock:
                frame = server.active_frame()
                if frame is None:
                    raise APIError(404, "Aucune image native récente disponible")
                png = frame["png"]
            self.send_bytes(png, "image/png")
        elif path == "/api/runtime":
            origin = f"http://127.0.0.1:{server.server_port}"
            url = origin + "/bridge/bootstrap.lua"
            self.send_json({"bootstrap_url": url, "bootstrap_command": f'loadstring(game:GetService("HttpService"):GetAsync("{url}"))()',
                            "runtime_url": origin + "/bridge/runtime.lua", "origin": origin, "current_bridge_version": CURRENT_BRIDGE_VERSION})
        elif path.startswith("/api/export/"):
            export = path.removeprefix("/api/export/")
            ident, separator, kind = export.rpartition(".")
            if not separator or kind not in {"json", "lua", "rbxmx"}:
                raise APIError(404, "Format d’export inconnu")
            project = self.load_project(ident)
            if kind == "rbxmx":
                source = sibling("fx_rbxmx").export_rbxmx(project)
                self.send_bytes(source.encode("utf-8"), "application/xml; charset=utf-8", filename=ident + ".rbxmx")
            elif kind == "json":
                self.send_bytes((json.dumps(project, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), "application/json; charset=utf-8", filename=ident + ".json")
            else:
                try:
                    exporter = importlib.import_module((__package__ + "." if __package__ else "") + "fx_export")
                except ImportError as exc:
                    raise APIError(503, "Exportateur Lua absent") from exc
                source = exporter.export_project(project)
                self.send_bytes(source.encode("utf-8"), "text/plain; charset=utf-8", filename=ident + ".lua")
        elif path == "/api/blocks":
            self.send_json({"blocks": sibling("fx_modules").list_blocks()})
        elif path == "/api/snapshots":
            items = []
            if server.snapshots.is_dir():
                for file in server.snapshots.glob("*.json"):
                    try:
                        item = json.loads(file.read_text(encoding="utf-8"))
                        if confined(server.snapshots, item["id"] + ".png").is_file():
                            items.append(item)
                    except (ValueError, OSError, KeyError):
                        continue
            self.send_json({"snapshots": sorted(items, key=lambda item: item["created_at"], reverse=True)})
        elif path.startswith("/api/snapshot/") and path.endswith(".png"):
            ident = path.removeprefix("/api/snapshot/").removesuffix(".png")
            identifier(ident, "snapshot id")
            self.file(confined(server.snapshots, ident + ".png"))
        elif path == "/bridge/poll":
            client_id = query.get("client_id", [None])[0]
            server.touch_client(client_id)
            with server.lock:
                retry = next((pending for pending in server.pending.values()
                              if pending["client_id"] == client_id and time.monotonic() - pending["delivered"] >= 2), None)
                command = retry["command"] if retry else server.commands.popleft() if server.commands else None
                if command:
                    server.pending[command["id"]] = {"client_id": client_id, "command": command, "delivered": time.monotonic()}
            self.send_json({"command": command})
        elif path in {"/bridge/runtime.lua", "/bridge/bootstrap.lua"}:
            filename = "fx_runtime.lua" if path.endswith("runtime.lua") else "fx_plugin.lua"
            target = confined(server.library / "tool", filename)
            if not target.is_file():
                raise APIError(503, "Runtime Studio absent")
            source = target.read_text(encoding="utf-8")
            if filename == "fx_plugin.lua":
                source = source.replace('local BASE = "http://127.0.0.1:48754"', f'local BASE = "http://127.0.0.1:{server.server_port}"', 1)
            self.send_bytes(source.encode("utf-8"), "text/plain; charset=utf-8")
        elif path.startswith("/library/"):
            relative = path.removeprefix("/library/")
            if not self.library_allowed(relative):
                raise APIError(403, "Fichier hors du catalogue public local")
            self.file(confined(server.library, relative))
        else:
            raise APIError(404, "Route introuvable")

    @staticmethod
    def library_allowed(relative):
        parts = relative.split("/")
        if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
            return False
        suffix = Path(relative).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".html", ".json", ".csv", ".sqlite"}:
            return False
        root_files = {"catalogue.html", "textures.json", "textures.csv", "textures.sqlite", "summary.json", "failures.json", "apercu_catalogue.jpg"}
        if len(parts) == 1:
            return relative in root_files
        if parts[0] in {"images", "previews", "tags"}:
            return suffix != ".html"
        if parts[0] in {"beams", "meshes"}:
            return (len(parts) == 2 and parts[1] in {"assets.json", "assets.csv", "assets.sqlite", "summary.json", "failures.json", "apercu.jpg"}) or (len(parts) >= 3 and parts[1] in {"images", "previews", "tags"} and suffix != ".html")
        return False

    def post(self, path):
        server = self.server
        data = self.read_json(12_000_000 if path in {"/api/snapshot", "/bridge/frame"} else 4_000_000)
        if path == "/api/project":
            project = validate_project(data.get("project", data))
            project.setdefault("id", uuid.uuid4().hex)
            with server.lock:
                atomic_json(self.project_path(project["id"]), project)
            self.send_json(project, 201)
        elif path == "/api/compose":
            # Ajoute des briques à la recette fournie (ou en crée une) ; rien n’est enregistré.
            plan = data.get("plan") or {"blocks": data.get("blocks")}
            self.send_json(sibling("fx_modules").compose(plan, data.get("project")))
        elif path == "/api/preview":
            action = data.get("action", "apply")
            if action not in {"apply", "play", "stop", "clear", "pause", "resume", "status", "preview_start", "preview_stop", "capture_status"}:
                raise ValidationError("Action inconnue")
            project = validate_project(data["project"]) if data.get("project") is not None else None
            if action in {"apply", "play"} and project is None:
                raise ValidationError("Projet requis pour appliquer ou lire")
            command = {"id": uuid.uuid4().hex, "action": action}
            if project is not None:
                command["project"] = project
            if "time" in data:
                command["time"] = number(data["time"], "time", 0, project["duration"] if project else 600)
                if command["time"] != 0:
                    raise APIError(422, "Le rendu natif ne permet pas de reconstruire fidèlement particules et traînées à un instant arbitraire. Relancer la lecture depuis le début.")
            if "fps" in data:
                command["fps"] = number(data["fps"], "fps", 1, 15)
            with server.lock:
                if not server.connected():
                    raise APIError(409, "Roblox Studio n’est pas connecté. Installer ou lancer le pont depuis l’éditeur.")
                if action in {"preview_start", "preview_stop", "capture_status"} and not server.client.get("capabilities", {}).get("native_preview"):
                    raise APIError(409, "Le pont chargé dans Studio est ancien et ne prend pas en charge l’aperçu intégré. Relancez Roblox Studio, puis cliquez sur Plugins > Dataky FX > Connexion pour charger la nouvelle version.")
                if len(server.commands) + len(server.pending) >= 50:
                    raise APIError(429, "Le pont a trop de commandes en attente")
                if action in {"apply", "play", "stop", "clear", "preview_start", "preview_stop"}:
                    server.invalidate_preview(disable=action in {"stop", "clear", "preview_stop"})
                    if action in {"apply", "play"}:
                        server.preview_project_id = project.get("id")
                        server.preview_project_name = project.get("name")
                    if action == "clear":
                        server.preview_project_id = None
                        server.preview_project_name = None
                command["capture_generation"] = server.capture_generation
                server.commands.append(command)
            self.send_json({"queued": True, "command": command, "id": command["id"]}, 202)
        elif path == "/bridge/hello":
            server.touch_client(data.get("client_id"), data)
            self.send_json({"ok": True, "app": APP, "version": CURRENT_BRIDGE_VERSION})
        elif path == "/bridge/goodbye":
            client_id = identifier(data.get("client_id"), "client_id")
            with server.lock:
                if not server.client or server.client["client_id"] != client_id:
                    raise APIError(409, "Seul le pont connecté peut fermer sa session")
                server.client = None
                server.commands.clear()
                server.pending.clear()
                server.last_error = None
                server.invalidate_preview(disable=True)
                server.preview_project_id = None
                server.preview_project_name = None
            self.send_json({"ok": True})
        elif path == "/bridge/preview_status":
            client_id = data.get("client_id")
            for field in ("enabled", "available", "permission"):
                if not isinstance(data.get(field), bool):
                    raise ValidationError(field + " doit être un booléen")
            error = data.get("error")
            if error is not None:
                error = text(error, "error", 2000)
            fps = number(data.get("fps", 0), "fps", 0, 15)
            generation = number(data.get("generation"), "generation", 0, integer=True)
            with server.lock:
                server.require_active_client(client_id)
                if generation != server.capture_generation:
                    raise APIError(409, "État de capture périmé")
                server.preview = {field: data[field] for field in ("enabled", "available", "permission")}
                server.preview.update({"error": error, "fps": fps})
                if not data["enabled"] or not data["available"] or not data["permission"]:
                    server.latest_frame = None
            self.send_json({"ok": True})
        elif path == "/bridge/frame":
            client_id = data.get("client_id")
            generation = number(data.get("generation"), "generation", 0, integer=True)
            project_id = data.get("project_id")
            if project_id is not None:
                identifier(project_id, "project_id")
            timestamp = number(data.get("time", 0), "time", 0, 600)
            # Check lease/generation before decoding attacker-provided image data,
            # then check again before publishing if commands arrived meanwhile.
            with server.lock:
                server.require_active_client(client_id)
                if generation != server.capture_generation or project_id != server.preview_project_id:
                    raise APIError(409, "Image provenant d’une ancienne composition")
                if not (server.preview["enabled"] and server.preview["available"] and server.preview["permission"]):
                    raise APIError(409, "Le flux natif n’est pas activé et autorisé")
            png, width, height = decode_png_data_url(data.get("image"), 4_000_000)
            with server.lock:
                server.require_active_client(client_id)
                if generation != server.capture_generation or project_id != server.preview_project_id or not server.preview["enabled"]:
                    raise APIError(409, "Image périmée pendant le décodage")
                server.frame_sequence += 1
                metadata = {"sequence": server.frame_sequence, "at": now_iso(), "width": width, "height": height,
                            "time": timestamp, "project_id": project_id, "project_name": server.preview_project_name, "generation": generation}
                server.latest_frame = {"png": png, "metadata": metadata, "received": time.monotonic(), "client_id": client_id}
            self.send_json({"ok": True, "frame": metadata})
        elif path == "/bridge/ack":
            client_id = data.get("client_id")
            server.touch_client(client_id)
            ident = identifier(data.get("id"), "command id")
            if not isinstance(data.get("ok"), bool):
                raise ValidationError("ok doit être un booléen")
            error = text(data.get("error", ""), "error", 4000)
            with server.lock:
                pending = server.pending.get(ident)
                if not pending or pending["client_id"] != client_id:
                    raise APIError(409, "Commande inconnue ou appartenant à un autre pont")
                server.pending.pop(ident)
                server.last_ack = {"id": ident, "ok": data["ok"], "error": error, "details": data.get("details"), "at": now_iso(), "action": pending["command"]["action"]}
                server.last_error = error if not data["ok"] else None
            self.send_json({"ok": True})
        elif path == "/api/snapshot":
            native = data.get("native", False)
            if not isinstance(native, bool):
                raise ValidationError("native doit être un booléen")
            native_meta = None
            if native:
                with server.lock:
                    frame = server.active_frame()
                    if frame is None:
                        raise APIError(409, "Aucune image native récente à enregistrer")
                    native_meta = dict(frame["metadata"])
                    png = frame["png"]
                width, height = native_meta["width"], native_meta["height"]
                if "project_id" in data and data["project_id"] != native_meta["project_id"]:
                    raise APIError(409, "L’image native appartient à une autre composition")
                if "time" in data and data["time"] != native_meta["time"]:
                    raise APIError(409, "Le temps demandé ne correspond pas à l’image native capturée")
            else:
                png, width, height = decode_png_data_url(data.get("image"))
            item = {"id": uuid.uuid4().hex, "created_at": now_iso(), "width": width, "height": height}
            item["url"] = "/api/snapshot/" + item["id"] + ".png"
            if native_meta:
                item.update({"project_id": native_meta["project_id"], "time": native_meta["time"], "captured_at": native_meta["at"],
                             "project_name": native_meta["project_name"], "frame_sequence": native_meta["sequence"], "capture_source": "studio-native"})
            elif data.get("project_id") is not None:
                item["project_id"] = identifier(data["project_id"], "project_id")
            if not native_meta and "time" in data:
                item["time"] = number(data["time"], "time", 0, 600)
            if not native_meta:
                source = data.get("source", "screen-share")
                if source not in {"screen-share", "emulator"}:
                    raise ValidationError("source doit valoir screen-share ou emulator")
                item.update({"captured_at": item["created_at"], "capture_source": "browser-emulator" if source == "emulator" else "screen-share"})
            with server.lock:
                atomic_bytes(confined(server.snapshots, item["id"] + ".png"), png)
                atomic_json(confined(server.snapshots, item["id"] + ".json"), item)
            self.send_json(item, 201)
        else:
            raise APIError(404, "Route introuvable")

    def delete(self, path):
        if not path.startswith("/api/project/"):
            raise APIError(404, "Route introuvable")
        target = self.project_path(path.removeprefix("/api/project/"))
        with self.server.lock:
            if not target.is_file():
                raise APIError(404, "Projet introuvable")
            target.unlink()
        self.send_json({"ok": True})


def create_server(library=LIBRARY, port=48754):
    return FXServer(("127.0.0.1", port), library)


def main(argv=None):
    parser = ArgumentParser(description=APP + " — éditeur local et pont Roblox Studio")
    parser.add_argument("--port", type=int, default=48754)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    server = create_server(port=args.port)
    origin = f"http://127.0.0.1:{server.server_port}"
    print(f"{APP} : {origin}\nFermer cette fenêtre arrête le serveur. Aucun appel à une IA.", flush=True)
    if not args.no_browser:
        webbrowser.open(origin)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
