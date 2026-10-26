"""Updater integration tests use fake GitHub responses and real temporary files."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

import fx_update as updater


def package(version="1.1.0", files=None, zip_info=None):
    files = files or {
        "version.json": json.dumps({"version": version}).encode(),
        "Dataky FX Studio.exe": b"new-desktop",
        "tool/fx_update.py": b"# new-updater\n",
        "editor/app.js": b"// new-app\n",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(zip_info(name) if zip_info else name, content)
    body = output.getvalue()
    manifest = {"format": 1, "application": "Dataky FX Studio", "version": version,
                "archive": updater.ARCHIVE, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    return body, manifest


class Github:
    def __init__(self, version="1.1.0", files=None, zip_info=None):
        self.body, self.manifest = package(version, files, zip_info)
        self.urls = {name: "https://github.com/" + updater.REPOSITORY + "/releases/download/v" + version + "/" + name
                     for name in (updater.ARCHIVE, updater.MANIFEST)}
        self.release = {"tag_name": "v" + version, "draft": False, "prerelease": False, "assets": [
            {"name": updater.MANIFEST, "state": "uploaded", "browser_download_url": self.urls[updater.MANIFEST]},
            {"name": updater.ARCHIVE, "state": "uploaded", "browser_download_url": self.urls[updater.ARCHIVE],
             "size": len(self.body), "digest": "sha256:" + self.manifest["sha256"]}]}
        self.calls = []

    def __call__(self, url, limit, timeout):
        self.calls.append((url, limit, timeout))
        if url == updater.LATEST_API:
            return json.dumps(self.release).encode()
        if url == self.urls[updater.MANIFEST]:
            return json.dumps(self.manifest).encode()
        if url == self.urls[updater.ARCHIVE]:
            return self.body
        raise AssertionError("Unexpected update URL")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.original = {
            "version.json": b'{"version":"1.0.0"}',
            "Dataky FX Studio.exe": b"old-desktop",
            "tool/fx_update.py": b"# old-updater\n",
            "editor/app.js": b"// old-app\n",
            "catalogue.html": b"old-catalogue",
            "editor/projects/custom.json": b"personal-project",
            "editor/snapshots/photo.json": b"personal-snapshot",
            "editor/artistry/review.json": b"personal-artistry",
            "editor/local_ai/meshes/model.json": b"personal-mesh",
            "images/custom.png": b"custom-image",
            "textures.json": b"personal-texture-data",
            "tool/grid_overrides.json": b"personal-overrides",
            "tool/texture_frames.json": b"personal-cache",
            "exports/mine.lua": b"personal-export",
        }
        for name, content in self.original.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.enterContext(mock.patch.object(updater, "server_running", return_value=False))

    def assert_original(self):
        for name, content in self.original.items():
            self.assertEqual((self.root / name).read_bytes(), content, name)

    def test_check_downloads_only_metadata_and_preserves_all_files(self):
        github = Github()
        result = updater.run(self.root, fetch=github)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["current_version"], "1.0.0")
        self.assertEqual(result["latest_version"], "1.1.0")
        self.assertEqual(len(github.calls), 2)
        self.assert_original()
        state = json.loads((self.root / "editor/desktoplogs/update-status.json").read_bytes())
        self.assertEqual(state["status"], "available")
        self.assertIn("checked_at", state)

    def test_apply_commits_verified_code_and_rebuilds_from_local_data(self):
        github = Github()

        def rebuild(root):
            self.assertEqual(updater.current_version(root), "1.0.0", "version commits last")
            self.assertEqual((root / "editor/app.js").read_bytes(), b"// new-app\n")
            self.assertEqual((root / "textures.json").read_bytes(), b"personal-texture-data")
            (root / "catalogue.html").write_bytes(b"rebuilt-catalogue")

        result = updater.run(self.root, apply=True, fetch=github, rebuild=rebuild)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(updater.current_version(self.root), "1.1.0")
        self.assertEqual((self.root / "catalogue.html").read_bytes(), b"rebuilt-catalogue")
        for name, content in self.original.items():
            if name not in github.manifest["files"] and name != "catalogue.html":
                self.assertEqual((self.root / name).read_bytes(), content, name)
        backups = list((self.root / "editor/desktoplogs/updates").glob("backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "editor/app.js").read_bytes(), b"// old-app\n")

    def test_rebuild_failure_restores_all_code_version_and_catalogue(self):
        def rebuild(root):
            (root / "catalogue.html").write_bytes(b"half-built")
            raise OSError("injected disk failure")

        result = updater.run(self.root, apply=True, fetch=Github(), rebuild=rebuild)
        self.assertEqual(result["status"], "error")
        self.assertIn("restaurée", result["message"])
        self.assert_original()

    def test_failed_file_replacement_rolls_back_preceding_changes(self):
        original_replace = updater.os.replace

        def replace(source, destination):
            if str(source).endswith("app.js") and "stage-" in str(source):
                raise PermissionError("locked file")
            return original_replace(source, destination)

        with mock.patch.object(updater.os, "replace", side_effect=replace):
            result = updater.run(self.root, apply=True, fetch=Github())
        self.assertEqual(result["status"], "error")
        self.assert_original()

    def test_network_failure_is_nonfatal_and_does_not_touch_application_files(self):
        def offline(*args):
            raise updater.NetworkUnavailable("offline")

        result = updater.run(self.root, apply=True, fetch=offline)
        self.assertEqual(result["status"], "unavailable")
        self.assert_original()

    def test_equal_or_older_release_never_downloads_or_downgrades(self):
        for version in ("1.0.0", "0.9.0"):
            github = Github(version)
            result = updater.run(self.root, apply=True, fetch=github)
            self.assertEqual(result["status"], "up_to_date")
            self.assertEqual(len(github.calls), 1)
            self.assert_original()

    def test_running_server_prevents_apply_without_network_or_writes(self):
        github = Github()
        with mock.patch.object(updater, "server_running", return_value=True):
            result = updater.run(self.root, apply=True, fetch=github)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(github.calls, [])
        self.assert_original()

    def test_corrupt_download_is_rejected_before_any_application_write(self):
        github = Github()
        github.body += b"tampered"
        result = updater.run(self.root, apply=True, fetch=github)
        self.assertEqual(result["status"], "error")
        self.assert_original()

    def test_manifest_cannot_target_personal_data_or_escape_installation(self):
        bad_names = ["../outside.py", "/outside.py", "tool/../../outside.py", "editor\\app.js", "editor/projects/mine.json",
                     "tool/grid_overrides.json", "tool/texture_frames.json", "editor/artistry/notes.js", "images/custom.png",
                     "source/code.py", "_runtime/python/python.exe", "tool/CON.py", "editor/app.js ", "editor/APP.JS"]
        for name in bad_names:
            with self.subTest(name=name):
                github = Github()
                github.manifest["files"][name] = "0" * 64
                result = updater.run(self.root, apply=True, fetch=github)
                self.assertEqual(result["status"], "error")
                self.assert_original()

    def test_zip_symlink_is_rejected_even_when_hashes_match(self):
        def link_info(name):
            item = zipfile.ZipInfo(name)
            if name == "editor/app.js":
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
            return item

        result = updater.run(self.root, apply=True, fetch=Github(zip_info=link_info))
        self.assertEqual(result["status"], "error")
        self.assert_original()

    def test_file_digest_and_version_must_agree_with_manifest(self):
        github = Github()
        github.manifest["files"]["editor/app.js"] = "0" * 64
        result = updater.run(self.root, apply=True, fetch=github)
        self.assertEqual(result["status"], "error")
        self.assert_original()

        body, manifest = package()
        manifest["version"] = "9.9.9"
        with self.assertRaises(updater.UpdateError):
            updater.verify_archive(body, manifest)

    def test_unexpected_zip_entries_and_uncompressed_limits_are_rejected(self):
        github = Github()
        output = io.BytesIO(github.body)
        with zipfile.ZipFile(output, "a") as archive:
            archive.writestr("editor/extra.js", b"unexpected")
        body = output.getvalue()
        github.manifest.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        with self.assertRaises(updater.UpdateError):
            updater.verify_archive(body, github.manifest)
        with mock.patch.object(updater, "MAX_FILE", 3):
            with self.assertRaises(updater.UpdateError):
                updater.verify_archive(github.body, package()[1])

    def test_asset_urls_must_belong_to_official_repository_and_use_https(self):
        for url in ["http://github.com/unsafe", "https://github.com.evil.test/file", "file:///tmp/code", "https://user:pass@github.com/file", "https://github.com:bad/file"]:
            with self.subTest(url=url), self.assertRaises(updater.UpdateError):
                updater._https_url(url)
        github = Github()
        github.release["assets"][0]["browser_download_url"] = "https://github.com/other/repo/releases/download/v1.1.0/" + updater.MANIFEST
        self.assertEqual(updater.run(self.root, fetch=github)["status"], "error")

    def test_duplicate_json_keys_and_unstable_versions_are_rejected(self):
        with self.assertRaises(updater.UpdateError):
            updater._json(b'{"version":"1.0.0","version":"2.0.0"}')
        for version in ["v1.0.0", "1.0", "1.0.0-beta", "01.0.0", True]:
            with self.subTest(version=version), self.assertRaises(updater.UpdateError):
                updater.parse_version(version)
        github = Github()
        github.release["prerelease"] = True
        self.assertEqual(updater.run(self.root, fetch=github)["status"], "error")

    def test_production_builder_archive_applies_and_rebuilds_real_local_catalogue(self):
        source_root = Path(__file__).resolve().parent.parent
        module_spec = importlib.util.spec_from_file_location("dataky_build_update", source_root / "desktop/build_update.py")
        builder = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source", Path(directory) / "release"
            names = set(builder.REQUIRED) | {"tool/catalog.py", "editor/app.js"}
            for name in names:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if name == "version.json":
                    target.write_text('{"version":"1.1.0"}', encoding="utf-8")
                elif name == "Dataky FX Studio.exe":
                    target.write_bytes(b"unlocked-rebuilt-desktop-executable")
                else:
                    shutil.copy2(source_root / name, target)
            with mock.patch.object(builder.subprocess, "check_output", return_value="\0".join(sorted(names)).encode()):
                manifest = builder.build_update(source, output, "1.1.0")
            body = (output / updater.ARCHIVE).read_bytes()
            self.assertEqual(updater.validate_manifest(manifest, "1.1.0"), manifest)
            self.assertEqual(set(updater.verify_archive(body, manifest)), names)
            textures = json.dumps([{"asset_id": "101", "name": "My retained texture", "tags": ["Custom"],
                                    "kind": "flipbook", "grid": 2, "image_path": "images/custom.png"}]).encode()
            (self.root / "textures.json").write_bytes(textures)
            github = Github()
            github.body, github.manifest = body, manifest
            github.release["assets"][1].update(size=len(body), digest="sha256:" + manifest["sha256"])
            result = updater.run(self.root, apply=True, fetch=github)
            self.assertEqual(result["status"], "updated", result)
            self.assertEqual((self.root / "Dataky FX Studio.exe").read_bytes(), b"unlocked-rebuilt-desktop-executable")
            self.assertEqual((self.root / "textures.json").read_bytes(), textures)
            html = (self.root / "catalogue.html").read_text(encoding="utf-8")
            self.assertIn("My retained texture", html)
            self.assertIn('id="animate-flipbooks"', html)
            self.assertEqual((self.root / "editor/projects/custom.json").read_bytes(), b"personal-project")
            self.assertEqual((self.root / "tool/grid_overrides.json").read_bytes(), b"personal-overrides")


if __name__ == "__main__":
    unittest.main()
