"""Build the small application-only assets consumed by tool/fx_update.py.

The public update never contains catalogue data, runtime binaries or user files.
Run after staging new application files: python desktop/build_update.py --root .
--out-dir PATH. Existing release assets are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile

ARCHIVE_NAME = "DatakyFX-Studio-Update.zip"
MANIFEST_NAME = "DatakyFX-Studio-Update.json"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_FILES = 1024
REQUIRED = {"Dataky FX Studio.exe", "version.json", "tool/fx_update.py",
            "tool/fx_server.py", "tool/gallery.py", "tool/asset_catalog.py", "editor/index.html"}
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def allowed_path(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(part in {".", ".."} for part in path.parts):
        return False
    if any(not re.fullmatch(r"[A-Za-z0-9_. -]+", part) or part.endswith((".", " ")) for part in path.parts):
        return False
    if any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I) for part in path.parts):
        return False
    if name in {"Dataky FX Studio.exe", "version.json"}:
        return True
    parts = path.parts
    if len(parts) != 2:
        return False
    directory, filename = parts
    suffix = PurePosixPath(filename).suffix
    if filename.startswith("test_"):
        return False
    return ((directory == "editor" and suffix in {".html", ".js", ".css"}) or
            (directory == "tool" and suffix in {".py", ".lua", ".cjs"}))


def selected_files(root: Path) -> dict[str, Path]:
    root = root.resolve()
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode("utf-8").split("\0")
    result = {}
    for name in filter(allowed_path, names):
        file = root / name
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError(f"Application path must stay inside the checkout: {name}")
        if not file.is_file():
            raise ValueError(f"Tracked application file is missing: {name}")
        result[name] = file
    missing = REQUIRED.difference(result)
    if missing:
        raise ValueError("Required application files are missing or untracked: " + ", ".join(sorted(missing)))
    if len(result) > MAX_FILES or len({name.casefold() for name in result}) != len(result):
        raise ValueError("Application file list exceeds update limits or contains case collisions")
    return dict(sorted(result.items()))


def build_update(root: Path, output: Path, expected_version: str | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    files = selected_files(root)
    data = json.loads(files["version.json"].read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("version.json must contain a stable X.Y.Z version without leading zeroes")
    if expected_version is not None and expected_version != version:
        raise ValueError("The requested release version differs from version.json")
    total = sum(file.stat().st_size for file in files.values())
    if total > MAX_EXPANDED_BYTES:
        raise ValueError("Application-only update exceeds the 64 MiB expanded limit")
    output.mkdir(parents=True, exist_ok=True)
    archive_path, manifest_path = output / ARCHIVE_NAME, output / MANIFEST_NAME
    if archive_path.exists() or manifest_path.exists():
        raise FileExistsError("Release assets already exist; choose a fresh output directory")
    with tempfile.TemporaryDirectory(prefix=".dataky-update-", dir=output) as temporary:
        staged_archive = Path(temporary) / ARCHIVE_NAME
        digests = {}
        expanded = 0
        with zipfile.ZipFile(staged_archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, file in files.items():
                body = file.read_bytes()
                expanded += len(body)
                if len(body) > MAX_FILE_BYTES or expanded > MAX_EXPANDED_BYTES:
                    raise ValueError("An application file exceeds update extraction limits")
                digests[name] = hashlib.sha256(body).hexdigest()
                # Stable metadata makes builds reproducible and carries no local paths.
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, body, compresslevel=6)
        size = staged_archive.stat().st_size
        if size > MAX_ARCHIVE_BYTES:
            raise ValueError("Application-only update exceeds the 32 MiB download limit")
        manifest = {"format": 1, "application": "Dataky FX Studio", "version": version,
                    "archive": ARCHIVE_NAME, "sha256": hashlib.sha256(staged_archive.read_bytes()).hexdigest(),
                    "bytes": size, "files": digests}
        staged_manifest = Path(temporary) / MANIFEST_NAME
        staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged_archive.replace(archive_path)
        staged_manifest.replace(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--version", help="Require this exact X.Y.Z release version")
    args = parser.parse_args()
    manifest = build_update(args.root, args.out_dir, args.version)
    print(json.dumps({"version": manifest["version"], "archive": str(args.out_dir / ARCHIVE_NAME),
                      "manifest": str(args.out_dir / MANIFEST_NAME), "bytes": manifest["bytes"],
                      "sha256": manifest["sha256"], "files": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
