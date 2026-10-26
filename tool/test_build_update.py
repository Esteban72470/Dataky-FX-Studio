"""Public release assets exclude private state and match their SHA-256 manifest."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


def load_builder(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "desktop" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update = load_builder("build_update")
portable = load_builder("build_portable")


class ReleaseAssets(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "app"
        self.runtime = self.base / "runtime"
        self.tracked = set(update.REQUIRED) | {"editor/app.js", "editor/styles.css", "tool/fx_render.cjs",
            "editor/projects/dataky-impact.json", "editor/projects/enuma-elish-rupture.json",
            "editor/snapshots/private.png", "editor/local_ai/catalog.json", "editor/artistry/private.json",
            "docs/livraison/private.md", "reports-private.txt", "catalogue.html", "tool/test_fx_server.py",
            "tool/grid_overrides.json", "tool/texture_frames.json", "textures.json", "meshes/assets.json"}
        for name in self.tracked:
            self.write(self.root / name, '{"version":"1.2.3"}' if name == "version.json" else name)
        self.write(self.runtime / "python/pythonw.exe", "runtime")
        self.write(self.root / "editor/local_ai/untracked.json", "personal")
        self.write(self.root / "editor/untracked.js", "not staged")
        self.enterContext(mock.patch.object(update.subprocess, "check_output", side_effect=self.git))

    @staticmethod
    def write(path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def git(self, command, **kwargs):
        self.assertIn("ls-files", command)
        return ("\0".join(sorted(self.tracked)) + "\0").encode()

    def test_small_update_contains_only_application_files_and_verified_bytes(self):
        output = self.base / "release"
        manifest = update.build_update(self.root, output)
        body = (output / update.ARCHIVE_NAME).read_bytes()
        self.assertEqual(manifest["version"], "1.2.3")
        self.assertEqual(manifest["bytes"], len(body))
        self.assertEqual(manifest["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(manifest, json.loads((output / update.MANIFEST_NAME).read_text(encoding="utf-8")))
        with zipfile.ZipFile(output / update.ARCHIVE_NAME) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, set(manifest["files"]))
            self.assertTrue(update.REQUIRED.issubset(names))
            self.assertIn("tool/fx_render.cjs", names)
            for name in names:
                self.assertTrue(update.allowed_path(name), name)
                self.assertEqual(archive.read(name), (self.root / name).read_bytes())
                self.assertEqual(manifest["files"][name], hashlib.sha256(archive.read(name)).hexdigest())
            self.assertTrue(all("private" not in name and "local_ai" not in name and "projects" not in name for name in names))
            self.assertNotIn("editor/untracked.js", names)
            self.assertNotIn("tool/test_fx_server.py", names)
            self.assertNotIn("tool/grid_overrides.json", names)
            self.assertNotIn("catalogue.html", names)

    def test_reproducible_archive_and_existing_assets_not_overwritten(self):
        first, second = self.base / "first", self.base / "second"
        a = update.build_update(self.root, first)
        b = update.build_update(self.root, second)
        self.assertEqual(a, b)
        self.assertEqual((first / update.ARCHIVE_NAME).read_bytes(), (second / update.ARCHIVE_NAME).read_bytes())
        with self.assertRaises(FileExistsError):
            update.build_update(self.root, first)

    def test_missing_tracked_component_and_invalid_versions_are_rejected(self):
        self.tracked.remove("tool/fx_update.py")
        with self.assertRaisesRegex(ValueError, "missing or untracked"):
            update.build_update(self.root, self.base / "out")
        self.tracked.add("tool/fx_update.py")
        for version in ["v1.2.3", "1.2.3-beta", "01.2.3", "1.2", None, 123]:
            with self.subTest(version=version):
                self.write(self.root / "version.json", json.dumps({"version":version}))
                with self.assertRaisesRegex(ValueError, "stable X.Y.Z"):
                    update.build_update(self.root, self.base / "out")
        self.write(self.root / "version.json", '{"version":"1.2.3"}')
        with self.assertRaisesRegex(ValueError, "differs"):
            update.build_update(self.root, self.base / "out", "1.2.4")

    def test_large_update_leaves_no_publishable_partial_assets(self):
        output = self.base / "out"
        with mock.patch.object(update, "MAX_ARCHIVE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "download limit"):
                update.build_update(self.root, output)
        self.assertEqual(list(output.iterdir()), [])
        with mock.patch.object(update, "MAX_FILE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "extraction limits"):
                update.build_update(self.root, output)
        self.assertEqual(list(output.iterdir()), [])

    def test_public_full_package_excludes_tracked_and_untracked_personal_data(self):
        files = portable.selected_files(self.root, self.runtime, False)
        self.assertIn("editor/projects/enuma-elish-rupture.json", files)
        self.assertIn("_runtime/python/pythonw.exe", files)
        for name in ["editor/projects/dataky-impact.json", "editor/snapshots/private.png",
                     "editor/local_ai/catalog.json", "editor/local_ai/untracked.json", "editor/artistry/private.json",
                     "docs/livraison/private.md", "reports-private.txt", "tool/grid_overrides.json", "tool/texture_frames.json"]:
            self.assertNotIn(name, files)

    def test_explicit_private_full_package_keeps_user_files(self):
        files = portable.selected_files(self.root, self.runtime, True)
        for name in ["editor/projects/dataky-impact.json", "editor/snapshots/private.png",
                     "editor/local_ai/catalog.json", "editor/local_ai/untracked.json", "editor/artistry/private.json"]:
            self.assertIn(name, files)
        self.assertNotIn("docs/livraison/private.md", files)

    def test_update_path_allowlist_cannot_select_private_paths_or_traversal(self):
        for name in ["editor/projects/test.js", "editor/../app.js", "editor\\app.js", "/editor/app.js",
                     "tool/test_fx_server.py", "tool/grid_overrides.json", "_runtime/python/pythonw.exe", "../version.json",
                     "editor/CON.js", "editor/app.js.", "editor/élan.js", "editor//app.js"]:
            self.assertFalse(update.allowed_path(name), name)


if __name__ == "__main__":
    unittest.main()
