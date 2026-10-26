"""Check and apply code-only updates from Dataky FX Studio's stable GitHub releases.

The portable bootstrap calls --apply before starting the desktop/server. The
desktop may call --check while running. Personal data, assets and runtimes are
never update targets. Everything is verified before application files change.
"""
from __future__ import annotations

from argparse import ArgumentParser
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "Esteban72470/Dataky-FX-Studio"
LATEST_API = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
RELEASES_URL = "https://github.com/" + REPOSITORY + "/releases/latest"
ARCHIVE = "DatakyFX-Studio-Update.zip"
MANIFEST = "DatakyFX-Studio-Update.json"
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_FILES = 1024
REQUIRED_FILES = {"version.json", "tool/fx_update.py", "Dataky FX Studio.exe"}
ALLOWED_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


class UpdateError(ValueError):
    """A release/package cannot safely be used."""


class NetworkUnavailable(OSError):
    """Checking/downloading failed; the existing application remains usable."""


def parse_version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise UpdateError("Numéro de version invalide.")
    return tuple(map(int, value.split(".")))


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise UpdateError("Champ JSON dupliqué dans la mise à jour.")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeError, TypeError) as error:
        if isinstance(error, UpdateError):
            raise
        raise UpdateError("Métadonnées de mise à jour invalides.") from error


def allowed_path(name):
    """Only application code, the desktop shell and version marker are writable."""
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(part in {".", ".."} for part in path.parts):
        return False
    if any(not re.fullmatch(r"[A-Za-z0-9_. -]+", part) or part.endswith((".", " ")) for part in path.parts):
        return False
    if any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I) for part in path.parts):
        return False
    if name in {"version.json", "Dataky FX Studio.exe"}:
        return True
    if len(path.parts) != 2 or path.name.startswith("test_"):
        return False
    return (path.parts[0] == "editor" and path.suffix in {".html", ".css", ".js"}) or (
        path.parts[0] == "tool" and path.suffix in {".py", ".lua", ".cjs"})


def _target(root, name):
    target = root.joinpath(*PurePosixPath(name).parts)
    if not target.resolve().is_relative_to(root):
        raise UpdateError("Un fichier de mise à jour sort du dossier de l’application.")
    current = target
    while current != root:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise UpdateError("Un lien de fichiers empêche la mise à jour.")
        current = current.parent
    return target


def _https_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise UpdateError("Adresse de téléchargement non autorisée.")
    return url


class _GithubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url, max_bytes, timeout):
    """Download bounded public GitHub data. No account token is read or stored."""
    _https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Dataky-FX-Studio-Updater", "Accept": "application/vnd.github+json" if url == LATEST_API else "application/octet-stream"})
    deadline = time.monotonic() + timeout
    try:
        opener = urllib.request.build_opener(_GithubRedirects())
        with opener.open(request, timeout=min(5, timeout)) as response:
            _https_url(response.url)
            size = response.headers.get("Content-Length")
            if size:
                try:
                    if not 0 <= int(size) <= max_bytes:
                        raise UpdateError("Téléchargement de mise à jour trop volumineux.")
                except ValueError as error:
                    if isinstance(error, UpdateError):
                        raise
                    raise UpdateError("Taille de téléchargement invalide.") from error
            data = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise NetworkUnavailable("Le téléchargement de la mise à jour a dépassé son délai.")
                # read1 performs at most one socket read, so a slow trickle
                # cannot keep an otherwise bounded read alive indefinitely.
                chunk = response.read1(min(128 * 1024, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise UpdateError("Téléchargement de mise à jour trop volumineux.")
            return bytes(data)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            message = "Aucune mise à jour publique n’est disponible."
        elif error.code in (401, 403, 429):
            message = "GitHub est temporairement indisponible pour la vérification."
        else:
            message = "Le service de mise à jour est temporairement indisponible."
        raise NetworkUnavailable(message) from error
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as error:
        raise NetworkUnavailable("Connexion indisponible ; la version installée reste utilisable.") from error


def current_version(root):
    path = _target(root, "version.json")
    if not path.is_file():
        return "0.0.0"
    data = _json(path.read_bytes())
    value = data.get("version") if isinstance(data, dict) else None
    parse_version(value)
    return value


def validate_manifest(data, version):
    if not isinstance(data, dict) or type(data.get("format")) is not int or data["format"] != 1 or data.get("application") != "Dataky FX Studio":
        raise UpdateError("Format de mise à jour non reconnu.")
    if data.get("version") != version or data.get("archive") != ARCHIVE:
        raise UpdateError("La mise à jour ne correspond pas à la version publiée.")
    if not isinstance(data.get("sha256"), str) or not SHA256.fullmatch(data["sha256"]):
        raise UpdateError("Empreinte de mise à jour invalide.")
    if type(data.get("bytes")) is not int or not 0 < data["bytes"] <= MAX_ARCHIVE:
        raise UpdateError("Taille de mise à jour invalide.")
    files = data.get("files")
    if not isinstance(files, dict) or not REQUIRED_FILES.issubset(files) or not len(files) <= MAX_FILES:
        raise UpdateError("Liste des fichiers de mise à jour incomplète.")
    names = set()
    for name, digest in files.items():
        if not allowed_path(name) or name.casefold() in names:
            raise UpdateError("La mise à jour contient un chemin non autorisé.")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise UpdateError("Empreinte de fichier invalide.")
        names.add(name.casefold())
    return data


def _release_asset(release, name, version):
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Liste des téléchargements invalide.")
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
    if len(matches) != 1 or matches[0].get("state") != "uploaded":
        raise UpdateError("La publication ne contient pas sa mise à jour complète.")
    asset = matches[0]
    url = _https_url(asset.get("browser_download_url", ""))
    parsed = urllib.parse.urlsplit(url)
    expected = "/" + REPOSITORY + "/releases/download/" + release["tag_name"] + "/" + name
    if parsed.hostname != "github.com" or urllib.parse.unquote(parsed.path).casefold() != expected.casefold() or parsed.query or parsed.fragment:
        raise UpdateError("La mise à jour ne provient pas du dépôt officiel.")
    return asset


def check_release(root, fetch=fetch_bytes):
    installed = current_version(root)
    deadline = time.monotonic() + 8
    release = _json(fetch(LATEST_API, 2 * 1024 * 1024, 5))
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise UpdateError("La version publiée n’est pas une version stable.")
    tag = release.get("tag_name", "")
    version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
    parse_version(version)
    result = {"status": "up_to_date", "current_version": installed, "latest_version": version,
              "release_url": "https://github.com/" + REPOSITORY + "/releases/tag/" + tag,
              "message": "Dataky FX Studio est à jour."}
    if parse_version(version) <= parse_version(installed):
        return result, None
    manifest_asset = _release_asset(release, MANIFEST, version)
    archive_asset = _release_asset(release, ARCHIVE, version)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NetworkUnavailable("La vérification de mise à jour a dépassé son délai.")
    manifest = validate_manifest(_json(fetch(manifest_asset["browser_download_url"], 512 * 1024, min(5, remaining))), version)
    if archive_asset.get("size") != manifest["bytes"]:
        raise UpdateError("La taille publiée ne correspond pas à la mise à jour.")
    digest = archive_asset.get("digest")
    if digest and digest.lower() != "sha256:" + manifest["sha256"].lower():
        raise UpdateError("L’empreinte publiée ne correspond pas à la mise à jour.")
    result.update(status="available", message="Une mise à jour de Dataky FX Studio est disponible.")
    return result, {"manifest": manifest, "url": archive_asset["browser_download_url"]}


def verify_archive(body, manifest):
    if len(body) != manifest["bytes"] or hashlib.sha256(body).hexdigest() != manifest["sha256"].lower():
        raise UpdateError("Le téléchargement est incomplet ou son empreinte est incorrecte.")
    extracted = {}
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            infos = archive.infolist()
            if len(infos) != len(manifest["files"]) or len(infos) > MAX_FILES:
                raise UpdateError("Le contenu de la mise à jour ne correspond pas au manifeste.")
            total = 0
            names = set()
            for info in infos:
                name = info.filename
                file_type = stat.S_IFMT(info.external_attr >> 16)
                if info.is_dir() or not allowed_path(name) or name.casefold() in names or name not in manifest["files"] or file_type not in (0, stat.S_IFREG) or info.flag_bits & 1:
                    raise UpdateError("La mise à jour contient un fichier non autorisé.")
                names.add(name.casefold())
                total += info.file_size
                if not 0 <= info.file_size <= MAX_FILE or total > MAX_EXPANDED:
                    raise UpdateError("Le contenu décompressé de la mise à jour est trop volumineux.")
                content = archive.read(info)
                if len(content) != info.file_size or hashlib.sha256(content).hexdigest() != manifest["files"][name].lower():
                    raise UpdateError("Un fichier de mise à jour est corrompu.")
                extracted[name] = content
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise UpdateError("L’archive de mise à jour est invalide.") from error
    marker = _json(extracted["version.json"])
    if not isinstance(marker, dict) or marker.get("version") != manifest["version"]:
        raise UpdateError("Le numéro de version du paquet est incohérent.")
    return extracted


def rebuild_catalogue(root):
    command = "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from asset_catalog import rebuild_root_gallery; rebuild_root_gallery(Path(sys.argv[2]))"
    try:
        subprocess.run([sys.executable, "-c", command, str(root / "tool"), str(root)], check=True, capture_output=True, timeout=45)
    except (subprocess.SubprocessError, OSError) as error:
        raise UpdateError("Le catalogue n’a pas pu être actualisé ; la version précédente a été restaurée.") from error


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".update-", suffix=".json", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_verified(root, files, version, rebuild=rebuild_catalogue):
    """Back up every target first; restore all old code/catalogue if commit fails."""
    targets = {name: _target(root, name) for name in files}
    catalogue = _target(root, "catalogue.html")
    updates = _target(root, "editor/desktoplogs/updates")
    updates.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="backup-" + version + "-", dir=updates))
    all_targets = {**targets, "catalogue.html": catalogue}
    originals = {}
    for name, target in all_targets.items():
        if target.exists() and not target.is_file():
            raise UpdateError("Une destination de mise à jour n’est pas un fichier.")
        saved = backup.joinpath(*PurePosixPath(name).parts)
        if target.is_file():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            originals[name] = saved
        else:
            originals[name] = None
    committed = []
    with tempfile.TemporaryDirectory(prefix="stage-", dir=updates) as directory:
        stage = Path(directory)
        for name, content in files.items():
            path = stage.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        try:
            for name in sorted(set(files).difference({"version.json"})):
                target = targets[name]
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage.joinpath(*PurePosixPath(name).parts), target)
                committed.append(name)
            committed.append("catalogue.html")
            rebuild(root)
            os.replace(stage / "version.json", targets["version.json"])
            committed.append("version.json")
            _atomic_json(backup / "rollback.json", {"version": version, "files": list(originals), "complete": True})
        except Exception as error:
            rollback_failed = False
            for name in reversed(committed):
                try:
                    target = all_targets[name]
                    if originals[name] is None:
                        target.unlink(missing_ok=True)
                    else:
                        shutil.copy2(originals[name], target)
                except OSError:
                    rollback_failed = True
            if rollback_failed:
                raise UpdateError("La restauration est incomplète. Les sauvegardes sont conservées dans editor/desktoplogs/updates.") from error
            raise UpdateError("La mise à jour a échoué ; la version précédente a été restaurée.") from error
    return backup


def server_running(root):
    """Never replace code underneath an existing server for this installation."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in range(48754, 48775):
        try:
            with opener.open("http://127.0.0.1:" + str(port) + "/api/status", timeout=0.15) as response:
                data = _json(response.read(64 * 1024))
            if isinstance(data, dict) and data.get("app") == "Dataky FX Studio" and isinstance(data.get("library"), str):
                if Path(data["library"]).resolve() == root:
                    return True
        except (OSError, ValueError, http.client.HTTPException):
            pass
    return False


@contextmanager
def update_lock(root):
    path = _target(root, "editor/desktoplogs/update.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            if not path.stat().st_size:
                stream.write(b"0")
                stream.flush()
                stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise NetworkUnavailable("Une vérification de mise à jour est déjà en cours.") from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise NetworkUnavailable("Une vérification de mise à jour est déjà en cours.") from error
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def run(root, apply=False, fetch=fetch_bytes, rebuild=rebuild_catalogue):
    root = Path(root).resolve()
    result = {"status": "unavailable", "current_version": "0.0.0", "release_url": RELEASES_URL}
    try:
        result["current_version"] = current_version(root)
        with update_lock(root):
            if apply and server_running(root):
                raise NetworkUnavailable("Dataky FX Studio est ouvert ; la mise à jour sera installée au prochain démarrage après fermeture complète.")
            checked, plan = check_release(root, fetch)
            result.update(checked)
            if apply and plan:
                body = fetch(plan["url"], MAX_ARCHIVE, 60)
                files = verify_archive(body, plan["manifest"])
                apply_verified(root, files, plan["manifest"]["version"], rebuild)
                result.update(status="updated", version=plan["manifest"]["version"], message="Dataky FX Studio a été mis à jour.")
    except NetworkUnavailable as error:
        result.update(status="unavailable", message=str(error))
    except UpdateError as error:
        result.update(status="error", message=str(error))
    except OSError:
        result.update(status="error", message="Les fichiers de mise à jour sont indisponibles. La version installée est conservée.")
    result["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        _atomic_json(_target(root, "editor/desktoplogs/update-status.json"), result)
    except (OSError, UpdateError):
        pass
    return result


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.root, apply=args.apply)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
