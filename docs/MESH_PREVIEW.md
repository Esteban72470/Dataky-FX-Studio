# MeshPart preview with local OBJ geometry

Import an OBJ with `tool.fx_mesh.import_obj` or the local `/api/mesh/import` route to add mesh geometry to the editor. WebGL renders positions, normals, and UVs with depth, colour, transparency, TextureID, orientation, Size, and DoubleSided. Existing tracks animate the MeshPart on the same timeline as particles, Beams, Trails, and lights. Attachments follow the MeshPart's position and rotation. Like Roblox, Parts use world transforms. Parenting Parts alone does not establish local group transforms.

## Files and format

The importer accepts UTF-8 OBJ files containing surface data through `v`, `vt`, `vn`, and `f`. Positive and negative indices are supported. It triangulates triangles and planar convex polygons. Triangulate concave or nonplanar faces in the source application first. OBJ groups are combined into one MeshPart. Explicit normals are kept. If none are provided, the importer calculates face normals. Smoothing groups cannot replace explicit normals.

The importer never opens MTL files or other external resources. References to them generate a warning. For textures, set a Roblox TextureID whose thumbnail is in the local catalogue. These thumbnails have a lower resolution than the original assets.

Import limits are 4 MiB of text, 100,000 lines, 16,384 characters per line, 64 vertices per face, 60,000 vertices per channel, and 20,000 triangles per mesh. Each project supports up to 32 meshes, 100,000 triangles, and 16 MiB of JSON geometry. Source dimensions must fit within 2,048 units. Scale larger geometry down in the source application.

The importer centres the geometry on its bounding box and normalises each axis to `[-0.5, 0.5]`. The original dimensions become `MeshPart.Size`. A flat axis uses a minimum size of 0.001. OBJ coordinates are interpreted in studs with Y up. The browser flips the V coordinate for textures.

```python
from tool.fx_mesh import import_obj
result = import_obj(obj_text, "slash", name="slash.obj", mesh_id="")
project["nodes"].append(result["node"])
editor = project.setdefault("editor", {"version": 1, "curves": {}})
editor.setdefault("meshes", {})["slash"] = result["mesh"]
```

`result` contains `node`, `mesh`, and `warnings`. The schema validates the geometry before saving. `editor.meshes[node_id]` has the following structure.

```text
version: 1
positions: [x, y, z, ...]       # Flat normalised array
normals: [nx, ny, nz, ...]      # Unit normals, one per vertex
uvs: [u, v, ...]               # One pair per vertex
indices: [i0, i1, i2, ...]     # Triangles with zero-based integer indices
source: {name, format: "obj", sha256, dimensions: [x, y, z]}
```

The geometry is editor metadata, separate from `properties.MeshId`. Duplicate and copy/paste remap its IDs. Delete removes the associated metadata and Undo restores it. JSON import, export, and saves preserve the meshes. Keep the source OBJ for manual import into Studio.

## Export to Roblox

Local OBJ preview creates no Roblox asset. The native Studio preview and exports to `.rbxmx`, Luau, and Lua libraries require an explicit Roblox `MeshId`. JSON export is available without one. Use **Exporter → Manifeste des assets Roblox** (Export → Roblox asset manifest) to find missing references.

Import the source file with the official Roblox Studio workflow, verify geometry, scale, and permissions, and enter the resulting MeshId on the same node in the editor. Publishing is manual. An ID alone cannot confirm permissions or a matching mesh. Compare the results in Studio.

## Verification and limits

`test_fx_mesh.py` checks imports and invalid data. `test_fx_mesh.cjs` renders in Chromium and checks silhouette, depth, transparency, culling, and UV texture pixels. `test_fx_preview_ui.cjs` covers the metadata lifecycle. `test_fx_mesh_export.py` verifies that export requires a MeshId, and `test_fx_mesh_merge.py` covers merging local meshes.

The importer does not support FBX, glTF, GLB, skinning, Bones, AnimationController, EditableMesh, SurfaceAppearance/PBR, or procedural mesh generators. Preview materials approximate SmoothPlastic and Neon with simplified lighting. The preview does not reproduce Roblox's native bloom or shadows. It sorts translucent surfaces per object and particles in batches, so complex intersections may render differently in Roblox. Opaque texture areas write depth and alpha pixels are drawn in a second pass. The tests above cover the emulator. Use Studio for native visual comparisons.
