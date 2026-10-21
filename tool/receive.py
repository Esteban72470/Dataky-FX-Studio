"""Local-only sink for reading the ZonitoVisuals UI; does not modify place data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re

LIBRARY = Path(__file__).resolve().parent.parent
ROOT = LIBRARY / "source"
ROOT.mkdir(parents=True, exist_ok=True)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/capture":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 8_000_000:
            self.send_error(413)
            return
        try:
            data = json.loads(self.rfile.read(length))
            collection = data.get("collection", "textures")
            if collection not in ("textures", "beams", "meshes"):
                raise ValueError("invalid collection")
            root = ROOT if collection == "textures" else LIBRARY / collection / "source"
            root.mkdir(parents=True, exist_ok=True)
            label = data["label"]
            if not re.fullmatch(r"[A-Za-z0-9 _-]{1,70}", label):
                raise ValueError("invalid label")
            assert isinstance(data["records"], list)
            stem = label.replace(" ", "_")
            if "part" in data:
                part, total = data["part"], data["total_parts"]
                assert isinstance(part, int) and isinstance(total, int) and 1 <= part <= total <= 100
                staging = root / ".capture_parts"
                staging.mkdir(exist_ok=True)
                stage = staging / f"{stem}.{part:03d}.json"
                stage.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                pieces = [staging / f"{stem}.{n:03d}.json" for n in range(1, total + 1)]
                if not all(p.exists() for p in pieces):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(f"part {part}/{total}".encode())
                    return
                decoded = [json.loads(p.read_text(encoding="utf-8")) for p in pieces]
                if not all(p.get("captured_at") == data.get("captured_at") for p in decoded):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"waiting current capture parts")
                    return
                data = dict(data)
                data["records"] = [record for piece in decoded for record in piece["records"]]
                data.pop("part", None)
                data.pop("total_parts", None)
            destination = root / (stem + ".json")
            temp = destination.with_suffix(".json.tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(destination)
        except (ValueError, KeyError, AssertionError):
            self.send_error(400)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(str(len(data["records"])).encode())
        print(f"Saved {collection}/{label}: {len(data['records'])} records", flush=True)

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    print("Zonito local capture sink: 127.0.0.1:48753", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 48753), Handler).serve_forever()
