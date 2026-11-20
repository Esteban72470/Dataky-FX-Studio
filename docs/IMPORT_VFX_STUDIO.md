# Merging the ZonitoVisuals and VFX Studio catalogues

The merge keeps one row per valid Roblox ID in each collection. It retains alternate names, tags, notes, and previous keys, and stores placeholders with invalid IDs separately. A descriptive name replaces a generic name only when it appears in the metadata. The original name remains searchable.

A mesh can have more than one TextureId for the same MeshId. The library keeps one row per MeshId and stores its variants in `variants` and `references`. The catalogue tools expose each variant and continue to resolve old keys to their original textures.

## Captures and results

`source/vfx-studio/textures/textures-metadata.json` and `source/vfx-studio/meshes/meshes-metadata.json` store metadata and provenance from the plugin. The texture capture matches the 9,178 unique IDs verified in its interface. The 571 geometry observations represent 476 unique MeshIds. Interface entries without a usable MeshId are excluded from the count of native geometries. All 18 texture categories and the Static and Flipbook filters were checked in the interface. Categories also reflect the plugin's name matching, beyond the keywords in the JSON.

The mesh interface check covered 289 of 547 entries. It stopped when the plugin requested permission to manage scripts. The request was declined. The complete reference list comes from the separately read metadata of the installed package. `ui-section-verification.json` and `verified/Meshes_All_PARTIAL.json` record the limit of the interface check.

The comparison tracks the installed version separately from the public metadata used by the interface. The public version adds two texture IDs and removes two. The review found no other metadata differences. The provenance files record those changes.

JSON exports and tag indexes preserve aliases and provenance. CSV exports encode those fields as JSON. The SQLite databases store sources, names, previous keys, and variants in the `plugin_provenance` table. The previews are Roblox thumbnails. Original textures and mesh geometry are separate assets.

## Repeat the merge

From the repository root, generate a report without changing the exports.

```powershell
python tool/import_vfx_studio.py --root . --captures source/vfx-studio --report rendus/fusion-vfx-studio.json
```

To apply the merge, specify a new ZIP backup path.

```powershell
python tool/import_vfx_studio.py --root . --captures source/vfx-studio --report rendus/fusion-vfx-studio.json --apply --backup backups/avant-fusion-vfx-studio.zip
```

Add `--download` to fetch missing thumbnails. Valid cached images are reused. The importer rejects captures with active search filters, incomplete captures, and inconsistent totals. Reimporting the same metadata keeps the assets and aliases consistent.

Rebuilds through `METTRE_A_JOUR.bat`, `tool/catalog.py`, and `tool/asset_catalog.py` reapply the saved VFX Studio captures. This preserves the merge when the original catalogue is refreshed. To use newer plugin metadata, capture it separately.

Backups, private videos, plugin binaries, and plugin code are excluded from the public repository.
