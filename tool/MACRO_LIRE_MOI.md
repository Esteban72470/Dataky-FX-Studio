# Rebuild the texture, beam, and mesh catalogues

Double-click **`tool/macro.bat`** to run the Windows capture again. The default run covers all three collections, **Textures**, **Beams**, and **Meshes**, including each tab’s tags and **All** view. It also captures **Statics** and **Flipbooks** for Textures.

The macro preserves Roblox names and IDs. For meshes, the helper reads MeshId and TextureId from the panel. Raw captures go into `source/`, `beams/source/`, and `meshes/source/`. The macro then runs `catalog.py` for textures and `asset_catalog.py` for beams and meshes to rebuild the catalogues.

Preview downloads run in parallel and reuse valid images in the local cache. Restarting a build after an interruption fetches the missing previews. Running the macro again starts the capture sequence over and reuses the same image cache.

1. Open `vfx.rbxl` in Roblox Studio’s Edit mode and open ZonitoVisuals on Textures, Beams, or Meshes. Clear the search and deselect all tags so the header reads **Tags**.
2. Double-click **`tool/macro.bat`**. Copy the `loadstring(...)` line it prints, paste it into the Studio Command Bar, and run it. Allow local HTTP access if Studio asks.
3. Place the pointer exactly in the centre of the **Tags** header, then press **F8** to calibrate the panel coordinates.
4. Keep that Studio window in the foreground and leave its panels where they are while the macro captures each list. Press **Esc** or **Ctrl+C** to stop.

The macro checks the active tag before each capture. The **Statics** and **Flipbooks** views each require an exclusive selection with no tags. Beams and Meshes do not use those views. Incomplete asset or type captures are rejected before they can replace a complete file. After a successful run, the macro returns to the starting tab.

To choose which collections to capture, open a terminal in `tool/` and run either command.

```powershell
py -3 macro.py --collections beams meshes
py -3 macro.py --collections textures
```

The **Personal** and **Recently Used** views are excluded by default. Pass `--include-personal` to include them for each selected collection. If the Studio place has another name, add `--window-title "MyGame.rbxl"`.

To regenerate previews and exports from existing captures without repeating the click sequence, run the following commands.

```powershell
py -3 catalog.py --workers 12
py -3 asset_catalog.py --collections beams meshes --workers 12
```

The server listens only on `127.0.0.1:48754` and uses a random token on each launch. The macro stops if the expected Studio window loses focus, if the panel moves or changes size, or if the active collection, tag, or type no longer matches the expected capture. It creates no objects in the game.

Completed captures stay on disk if you stop the macro. Incomplete fragments remain in the collection’s `.capture_parts/` folder and never replace a complete capture. Clear active tags before restarting. Tags whose names are invalid filenames on Windows are saved under safe filenames, with the original tag names preserved in JSON. The macro restores the scroll position and menu visibility while the local connection remains available.

Automated tests cover coordinates, the command queue, split captures, the three collections and their tags, texture types, single-collection selection, and protection against mixed captures. The native Windows click sequence still needs an interactive run. Watch the first run, especially the first tab and tag changes.
