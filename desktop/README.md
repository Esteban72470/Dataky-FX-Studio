# Windows application

Double-click **Dataky FX Studio.exe** in the project root. The editor opens in a dedicated window without a terminal. Use the system tray icon to reopen the editor or stop its local server. Closing the editor window leaves the server running. Choose **Quitter Dataky FX Studio** (Quit Dataky FX Studio) to stop it.

The launcher uses your installed Python 3, .NET Framework, and Edge, Chrome, or Brave. If it cannot find a compatible browser, it opens your default browser. It does not bundle an AI model. Keep the executable with the `tool` and `editor` folders and the catalogue. The launcher reuses a server only if it belongs to this copy of the project, and stops it only if this launcher started it.

To rebuild the Windows launcher, run `powershell -File desktop/build.ps1`. This uses the .NET Framework compiler included with Windows. The catalogue and projects remain in the application folder.

## Standalone executable

**DatakyFX-Studio-Complet.exe** bundles the editor, its catalogue and assets, Python, image and video dependencies, Node, and Chromium. Double-click it to set up the application automatically on the first launch. Later launches reuse the prepared files and keep your saved projects.

Build the standalone executable locally with `desktop/build_portable.py` and a runtime staged outside the checkout.

```powershell
python desktop/build_portable.py --root . --runtime RUNTIME_PATH --out OUTPUT_PATH.exe --payload-zip TEMP_PAYLOAD_PATH.zip
```

The runtime includes the `python`, `node`, `node_modules`, and `browsers` subfolders. The launcher uses these bundled components first.

## Automatic updates

The standalone executable checks for stable versions at every startup. It verifies the SHA-256 hashes before installing an application update and opening the editor. The catalogue, projects, personal media, and runtimes stay in place. Application updates use a small archive separate from the full download. [GitHub Releases](https://github.com/Esteban72470/Dataky-FX-Studio/releases).

If the editor is already open for this copy, the update waits until you close it and start it again. The installed version remains available if the network or an update check fails. Results appear in `editor/desktoplogs/update-status.json`. The tray menu can check for updates and open the download page. The smaller launcher can also check for updates. Start the standalone executable to install them automatically.

The first launch of a new standalone executable copies missing personal files from a previous prepared installation, preferring the one currently open. Existing files and originals are preserved. The `--self-test` option skips this copy.

Pass `--include-user-data` to include the current installation’s personal projects and media in a private build. That private build stays local. The repository tracks the build sources and the small launcher.
