"""Build one Windows EXE containing the app, catalogue and a staged runtime.

The bootstrap footer is struct <16sQQ32s: DATAKYFXBUNDLE01, ZIP offset,
ZIP length, SHA-256 of ZIP bytes. No paths, credentials or installers are fetched.
Use --include-user-data only for a private package belonging to its local user.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
import zipfile

MAGIC = b"DATAKYFXBUNDLE01"
FOOTER = struct.Struct("<16sQQ32s")
PRIVATE_DIRS = ("editor/projects", "editor/artistry", "editor/snapshots", "editor/local_ai/meshes", "editor/local_ai/video", "exports")
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".local-ai", ".venv", "backups", "desktoplogs"}
MODEL_SUFFIXES = {".gguf", ".safetensors", ".ckpt", ".pt", ".pth"}


def file_sha(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def selected_files(root: Path, runtime: Path, include_user_data: bool):
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode("utf-8").split("\0")
    result = {}
    for name in filter(None, names):
        path = root / name
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        if name.startswith(("smokecheck/", "tool/fixtures/")) or Path(name).name.startswith("test_"):
            continue
        if name.startswith("desktop/") and name.endswith((".cs", ".ps1", ".py")):
            continue
        result[name] = path
    if include_user_data:
        for name in PRIVATE_DIRS:
            base = root / name
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = path
        registry = root / "editor/local_ai/catalog.json"
        if registry.is_file():
            result[registry.relative_to(root).as_posix()] = registry
    for path in runtime.rglob("*"):
        if path.is_file():
            result["_runtime/" + path.relative_to(runtime).as_posix()] = path
    clean = {}
    for name, path in result.items():
        if any(part in SKIP_PARTS for part in Path(name).parts) or path.suffix.lower() in {".pyc", ".pyo", ".log", ".lock", ".tmp", ".bak"}:
            continue
        if path.suffix.lower() in MODEL_SUFFIXES:
            raise ValueError(f"Unexpected model weights excluded from app package: {name}")
        if path.is_symlink():
            raise ValueError(f"Symlink not supported in private package: {name}")
        clean[name] = path
    for required in ("Dataky FX Studio.exe", "tool/fx_server.py", "editor/index.html", "textures.json", "meshes/assets.json", "_runtime/python/pythonw.exe"):
        if required not in clean:
            raise ValueError(f"Required component is missing: {required}")
    return dict(sorted(clean.items()))


def build_payload(root: Path, runtime: Path, destination: Path, include_user_data: bool, reuse: bool = False):
    if destination.exists():
        if not reuse:
            raise ValueError("Payload archive exists. Choose a new path or use --reuse-payload to validate and reuse it.")
        with zipfile.ZipFile(destination) as archive:
            data = json.loads(archive.read("portable-manifest.json"))
            if archive.testzip() is not None:
                raise ValueError("Existing payload archive is corrupt")
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if data.get("commit") != commit or data.get("private_user_data_included") != include_user_data:
            raise ValueError("Existing payload belongs to another app revision or privacy selection")
        current = selected_files(root, runtime, include_user_data)
        captured = {row["path"]: row for row in data["files"]}
        if set(current) != set(captured):
            raise ValueError("App/runtime file list changed after the payload was built")
        for name, path in current.items():
            if path.stat().st_size != captured[name]["bytes"] or file_sha(path) != captured[name]["sha256"]:
                raise ValueError(f"App/runtime file changed after the payload was built: {name}")
        return data
    files = selected_files(root, runtime, include_user_data)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    manifest = {"format": 1, "application": "Dataky FX Studio", "commit": commit,
                "created_at": datetime.now(timezone.utc).isoformat(), "private_user_data_included": include_user_data, "files": []}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".building")
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        for index, (name, path) in enumerate(files.items(), 1):
            digest = file_sha(path)
            archive.write(path, name)
            manifest["files"].append({"path": name, "bytes": path.stat().st_size, "sha256": digest})
            if index % 1000 == 0 or index == len(files):
                print(json.dumps({"phase": "packaging", "files": index, "total": len(files)}), flush=True)
        archive.writestr("portable-manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    temporary.replace(destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--payload-zip", type=Path)
    parser.add_argument("--include-user-data", action="store_true")
    parser.add_argument("--reuse-payload", action="store_true", help="Validate existing payload against every app/runtime file before reusing")
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    root, runtime, output = args.root.resolve(), args.runtime.resolve(), args.out.resolve()
    if output.exists():
        raise ValueError("Output exists; choose a new package path")
    if not runtime.is_dir() or runtime.is_relative_to(root):
        raise ValueError("Staged runtime must be a separate directory outside the app checkout")
    payload = args.payload_zip.resolve() if args.payload_zip else output.with_suffix(".payload.zip")
    compiler = args.compiler or Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_payload(root, runtime, payload, args.include_user_data, args.reuse_payload)
    payload_hash = bytes.fromhex(file_sha(payload))
    with tempfile.TemporaryDirectory(prefix="dataky-bootstrap-build-") as temporary:
        stub = Path(temporary) / "bootstrap.exe"
        command = [str(compiler), "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
                   "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Web.Extensions.dll",
                   "/reference:System.IO.Compression.dll", "/reference:System.IO.Compression.FileSystem.dll",
                   "/win32icon:" + str(root / "desktop/DatakyFXStudio.ico"), "/out:" + str(stub), str(root / "desktop/PortableBootstrap.cs")]
        subprocess.run(command, check=True)
        with output.open("xb") as target, stub.open("rb") as binary, payload.open("rb") as archive:
            shutil.copyfileobj(binary, target)
            offset = target.tell()
            shutil.copyfileobj(archive, target, 4 * 1024 * 1024)
            target.write(FOOTER.pack(MAGIC, offset, payload.stat().st_size, payload_hash))
    report = {"package": str(output), "bytes": output.stat().st_size, "sha256": file_sha(output),
              "payload_sha256": payload_hash.hex(), "bundle_id": payload_hash.hex()[:24], "files": len(manifest["files"]),
              "expanded_bytes": sum(row["bytes"] for row in manifest["files"]), "private_user_data_included": manifest["private_user_data_included"], "commit": manifest["commit"]}
    output.with_suffix(".manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
