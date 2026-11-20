# Dataky FX Studio

Double-click **DATAKY_FX_STUDIO.bat** to create and edit effects. The local editor opens in a browser with an asset library, hierarchy, properties, curves, a timeline, and 3D emulation. Roblox Studio is available for the final in-engine check. To work with Claude, run **INSTALLER_CLAUDE_DESKTOP.bat** for Claude Desktop or open this folder in Claude Code. [Claude setup](CLAUDE.md) · [Editor, Roblox Studio bridge, and .rbxmx export guide](DATAKY_FX_STUDIO.md).

The catalogue retains the provenance of ZonitoVisuals assets. The original folder name keeps existing paths and scripts compatible.

Double-click **catalogue.html**, then choose **Textures**, **Beams**, or **Meshes**. Search by name, tag, or ID. Each tab remembers its own filters, and Textures can be filtered by static image or flipbook. Use **Copier l’ID** (Copy ID) or **rbxassetid** to copy references for Roblox Studio.

**Beams** lists textures for Roblox ribbons and beams. **Meshes** lists 3D shapes. Its details show the **MeshId** and, when available, **TextureId**, with a copy button for each reference.

The catalogue and its Roblox-provided thumbnails are available offline. They retain asset IDs even when previews are missing. Original texture and mesh files are hosted by Roblox and may require permission to use in your experience.

## Files

| Path | Contents |
| --- | --- |
| `catalogue.html` | Visual catalogue with search, filters, and copy buttons for IDs. |
| `textures.json` | Full texture dataset for scripts. |
| `textures.csv` | Texture table suitable for Excel. |
| `textures.sqlite` | SQLite database for queries and tools. |
| `beams/` | Beam catalogue with `assets.json`, `assets.csv`, `assets.sqlite`, `tags/`, `images/`, `source/`, `summary.json`, and `failures.json`. |
| `meshes/` | Mesh catalogue with the same layout and MeshId and TextureId preserved in the exports. |
| `tags/` | Texture index by plugin tag. A texture can appear under several tags. |
| `images/` | Locally cached Roblox thumbnails named by asset ID. |
| `previews/` | Representative flipbook previews where the grid could be inferred. |
| `source/` | Raw plugin list captures used to rebuild the catalogue. |
| `summary.json` | Extraction and download summary. |
| `failures.json` | Unavailable previews and recorded errors. |
| `apercu_catalogue.jpg` | Contact sheet of 24 thumbnails with names and IDs. |
| `tool/` | Scripts for capture, download, and catalogue generation. |

The catalogue derives texture types from the plugin’s **Statics** and **Flipbooks** views when that information is available. The details panel shows where the classification came from and flags ambiguous or inferred cases. A flipbook grid marked **estimée** (estimated) is inferred and used for preview animation. Check the grid in the plugin before using it in an effect.

## Refresh the catalogue

Double-click **METTRE_A_JOUR.bat** to rebuild all three collections and download missing thumbnails from saved captures in `source/`, `beams/source/`, and `meshes/source/`. Downloads run in parallel. Valid images stay cached, so restarting after an interruption fetches only the remaining previews. New previews require an internet connection.

To rebuild the beam and mesh exports and retry their previews using existing captures, run this from the catalogue directory.

```powershell
python tool/asset_catalog.py --collections beams meshes --workers 12
```

To capture new plugin lists, run **`tool/macro.bat`** or `python tool/macro.py`. Open the plugin with its tags and search cleared and follow the prompts. Paste the supplied line into the Studio Command Bar, then place the pointer in the centre of the **Tags** header and press **F8** to calibrate. Press **Esc** to stop. Keep `vfx.rbxl` visible and its panels in place while the macro clicks. By default, it captures all lists and tags for **Textures**, **Beams**, and **Meshes**, plus the **Statics** and **Flipbooks** views for Textures. It then rebuilds the catalogues. [Detailed capture instructions](tool/MACRO_LIRE_MOI.md).

Automated checks cover the macro logic. The native Windows click sequence still needs an interactive run. Watch the first run, especially the first tag change. Completed captures remain on disk if the macro stops. Tags are discovered automatically. Pass `--include-personal` to include the personal and recent views.

Keep the catalogue and its image folders together when moving them.

Run `python tool/verify_outputs.py` to verify the exports without opening a browser. It compares the captures with the JSON, CSV, and SQLite databases, tag indexes, and HTML catalogue data. Add `--verify-png` to check PNG files with Pillow.

Run `python tool/verify_extra_outputs.py --verify-png` to check the Beam and Mesh captures, exports, asset references, images, and integration with the main catalogue.
