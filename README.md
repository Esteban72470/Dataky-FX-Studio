# Dataky FX Studio

Dataky FX Studio is a local editor for composing, animating, and exporting Roblox visual effects. It includes an offline catalogue of Roblox textures, beams, and meshes.

## Get started

1. Download and run **DatakyFX-Studio-Complet.exe**. The standalone package includes the editor, catalogue, Python, Node, and Chromium. [Download the latest release](https://github.com/Esteban72470/Dataky-FX-Studio/releases/latest).
2. Build an effect in the editor. Its tools include a live asset library, local OBJ mesh previews, animation curves and tracks, local video references, and manual art direction. Transparent Parts remain selectable and show an outline when selected.
3. Connect to Roblox Studio to check the effect in-engine and export it. [Read the editor guide](DATAKY_FX_STUDIO.md).

From a checkout on Windows, double-click **Dataky FX Studio.exe** to open the editor in a dedicated window without a terminal. This launcher uses your installed Python 3 and Edge, Chrome, or Brave. You can also run **DATAKY_FX_STUDIO.bat** to open the editor in your browser with the server visible. [Windows launcher and automatic updates](desktop/README.md).

The editor runs without a local AI model or an API key. The built-in model, its runtime and launchers, and the generation panel have been removed. MCP tools remain available for external assistants, with no bundled model required. [Assistant setup and workflow](CLAUDE.md).

## Browse the asset catalogue

Double-click **catalogue.html** and choose **Textures**, **Beams**, or **Meshes**. Search by name, tag, or Roblox ID. Each tab remembers its own filters. The Textures tab can also filter static images and flipbooks. Use **Copier l’ID** (Copy ID) or **rbxassetid** to copy a reference for Roblox Studio.

**Beams** lists textures for Roblox ribbons and beams. **Meshes** lists 3D shapes and provides copy buttons for their **MeshId** and, where available, **TextureId**. Mesh thumbnails do not contain geometry. [Local mesh previews](docs/MESH_PREVIEW.md) · [Roblox export compatibility](docs/EXPORT_COMPATIBILITY.md).

The catalogue combines captures from **ZonitoVisuals** and **VFX Studio**. Valid assets are grouped by Roblox ID. Earlier names and keys remain searchable aliases, and texture variants of the same mesh are preserved. More descriptive names come from plugin metadata. New entries appear in the editor catalogue without a server restart. [Catalogue merge and provenance](docs/IMPORT_VFX_STUDIO.md).

The catalogue and its Roblox-provided thumbnails work offline. The original texture and mesh files are hosted by Roblox, and assets may require permission to use in your experience. The catalogue keeps IDs even when thumbnails are unavailable.

Texture types come from the plugin’s **Statics** and **Flipbooks** views when that data is available. The details panel identifies the source of each classification and flags ambiguous or inferred cases. A flipbook grid marked **estimée** (estimated) is inferred and used for the preview animation. Check the grid in the plugin before using it in an effect.

| Path | Contents |
| --- | --- |
| `catalogue.html` | Visual catalogue with search, filters, and copy buttons for IDs. |
| `textures.json` | Full texture dataset for scripts. |
| `textures.csv` | Texture table suitable for Excel. |
| `textures.sqlite` | SQLite database for queries and tools. |
| `beams/` | Beam catalogue with `assets.json`, `assets.csv`, `assets.sqlite`, `tags/`, `images/`, `source/`, `summary.json`, and `failures.json`. |
| `meshes/` | Mesh catalogue with the same layout and both MeshId and TextureId in the exports. |
| `tags/` | Texture index by plugin tag. A texture can appear under several tags. |
| `images/` | Locally cached Roblox thumbnails named by asset ID. |
| `previews/` | Representative flipbook previews when the grid could be inferred. |
| `source/` | Raw plugin list captures used to rebuild the catalogue. |
| `summary.json` | Extraction and download summary. |
| `failures.json` | Missing previews and recorded errors. |
| `apercu_catalogue.jpg` | Contact sheet of 24 thumbnails with names and IDs. |
| `tool/` | Scripts for capture, download, and catalogue generation. |

## Refresh the catalogue

Run **METTRE_A_JOUR.bat** to rebuild all three collections and download missing thumbnails. The rebuild uses saved captures from `source/`, `beams/source/`, and `meshes/source/`, along with supplementary metadata in `source/vfx-studio/`. Downloads run in parallel and keep valid images in the cache. Rerun the update after an interruption to fetch the remaining previews. New downloads need an internet connection.

To rebuild the beam and mesh exports and retry their preview downloads from the existing captures, run this from the repository root.

```powershell
python tool/asset_catalog.py --collections beams meshes --workers 12
```

To capture changes in the plugin lists, run **`tool/macro.bat`** or `python tool/macro.py`. Clear the search and tags in the plugin, paste the provided line into the Studio Command Bar, then put the pointer in the centre of the **Tags** header and press **F8** to calibrate. **Esc** stops the capture. Keep the `vfx.rbxl` window visible and its panels in place. By default, the macro captures **Textures**, **Beams**, and **Meshes**, their tags and full lists, plus the **Statics** and **Flipbooks** views for Textures. It then rebuilds the catalogues. [Capture instructions](tool/MACRO_LIRE_MOI.md).

Automated checks cover the capture logic. The native Windows click sequence still needs an interactive run. Watch the first run, especially the first tag change. Completed captures remain on disk if the macro stops. The macro discovers tags automatically. Pass `--include-personal` to include the personal and recent views.

Keep the catalogue and its image folders together when moving them.

## Verify the exports

- `python tool/verify_outputs.py` compares the captures with the JSON, CSV, and SQLite databases, tag indexes, and HTML catalogue data. Add `--verify-png` to check image files with Pillow.
- `python tool/verify_extra_outputs.py --verify-png` checks the Beam and Mesh captures and exports, asset references, images, and integration with the main catalogue.

## Documentation

- [Editor, Studio bridge, and local API](DATAKY_FX_STUDIO.md)
- [Claude and MCP workflows](CLAUDE.md)
- [Windows launcher and automatic updates](desktop/README.md)
- [Live catalogue and reusable OBJ meshes](docs/CATALOGUE_IA_DYNAMIQUE.md)
- [Catalogue names and verified flipbook grids](docs/CATALOGUE_NOMS_ET_GRILLES.md)
- [Motion tracks in Roblox exports](docs/RUNTIME_ANIMATIONS.md)
- [Textures and local video references](docs/TEXTURES_REELLES_ET_VIDEO.md)
- [Development history, batches 1–2](RAPPORT_DEMANDES_CLAUDE.md) and [batch 3](RAPPORT_DEMANDES_CLAUDE_3.md)
