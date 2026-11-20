# Live editor catalogue

`tool/fx_ai_catalog.py` reads the existing **Textures**, **Beams**, and **Meshes** collections and reusable OBJ meshes imported locally. Each search rereads the current sources. Changes to names, tags, IDs, grids, and observations, as well as additions and deletions, become visible without a server restart. The module's historical name does not imply that it uses an AI model.

## Full catalogue and paginated search

Every valid ID is searchable through paginated results. The index checks names, tags, aliases, IDs, and explicit observations. French and English synonyms cover common VFX shapes. An explicitly requested ID takes priority. Ranking comes from text and does not analyse images or infer observed shapes from names.

Search returns a page of candidates from the full catalogue. Each candidate retains its collection, permanent ID, and provenance. Local geometry buffers load only after selection.

Duplicates with the same ID in the same collection are grouped. Alternative names and tags remain searchable. For meshes, each MeshId and TextureId pair represents a distinct variant. An untextured mesh stays separate from its textured variants. The key `meshes:ID` refers to the untextured version when available, or to the variant with the lowest numeric TextureId. Other variants use `meshes:ID@TEXTUREID`. The catalogue chooses these keys independently of row order. A bare ID that maps to multiple assets requires a full key. For example, `meshes:1051557` (Simple Thick Spring, untextured) and `meshes:1051557@98468789881853` (Spiral, textured) are separate entries.

Explicit MeshId and TextureId references are preserved. Invalid IDs are excluded from results and counted. Missing thumbnails do not remove assets from search. Unknown creators, licences, and rights stay unknown.

## Source files

- `textures.json`
- `beams/assets.json`
- `meshes/assets.json`
- `tool/grid_overrides.json` for confirmed grids
- `editor/artistry/assets.json` for human and vision observations
- `editor/local_ai/catalog.json` for reusable local meshes

The SHA-256 revision reflects the file contents even when size and modification time are unchanged. A concurrent modification triggers a reread. Invalid JSON raises a visible error. The module does not silently use stale cached data and never writes to the three source catalogues.

An addition must be recorded in the catalogue or go through a supported import. Placing a file in an image folder alone cannot create an asset entry with an ID, name, and provenance.

## Imported OBJ meshes

`register_mesh(imported, root=...)` registers the validated result of `import_obj`. The local ID, `local-<source file hash>`, is stable when the same OBJ is imported again. Geometry is stored under `editor/local_ai/meshes/` using its content hash. An interprocess lock protects the index and atomic writes replace it, so concurrent imports retain every entry.

Saving an effect with a known mesh preserves the mesh's library name, licence, creator, and registration provenance. A different layer name becomes a searchable alias. An unchanged save leaves the index and revision as they are. Explicit tags and nonempty MeshId and TextureID mappings are updated when they change.

Effects that use the same OBJ share those mappings. The assigned ID must represent the same geometry in Studio. An old, unmapped recipe does not clear a registered mapping. Clearing the MeshId in a project instance leaves the global mapping intact. To change or remove it globally, edit its entry in `editor/local_ai/catalog.json`. A mapping does not establish access rights or publish an asset.

You can find and reuse a local mesh without a MeshId for preview. Native export requires an explicit Roblox MeshId after an authorised import in Studio. The catalogue never publishes assets or downloads or executes third-party scripts. A Roblox thumbnail contains no mesh geometry. Without a local mesh, only Studio can render its exact native shape.

The registry supports up to 256 local meshes. The editor's geometry and composition limits still apply.

## Python API

```python
from tool import fx_ai_catalog as catalog

snapshot = catalog.snapshot(root=application_folder)
found = catalog.search("magic ring", collection="meshes", snapshot=snapshot)
asset = catalog.get_asset(found["items"][0]["key"], snapshot=snapshot)
geometry = catalog.load_geometry(asset, root=application_folder)  # None for a remote ID
```

`snapshot` returns `revision`, `counts`, `raw_counts`, `assets`, and `warnings`. `search` returns paginated results, the total, and the same revision. Reuse a snapshot to keep candidate selection and export tied to one consistent source. The next request can create a fresh snapshot.

Run `python -m unittest discover -s tool -p test_fx_ai_catalog.py` to verify freshness, concurrent reads, invalid JSON handling, pagination, synonyms, provenance, grids, mesh references, missing thumbnails, file path constraints, fingerprints, and atomic registration across processes.
