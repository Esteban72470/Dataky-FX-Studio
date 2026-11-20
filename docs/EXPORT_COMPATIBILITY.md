# Roblox exports and local geometry

This document records the export contract and verification from 25 October 2026.

Local OBJ geometry needs an authorised import in Roblox Studio and a **permanent MeshId** before native export. Publishing and uploading are manual.

## Local mesh data

`editor.meshes[nodeId]` stores triangles, normals, UVs, indices, and source metadata including the filename, OBJ format, SHA-256, and dimensions. Positions are centred and normalised. `MeshPart.Size` retains the object dimensions. JSON export preserves these fields so you can keep editing the effect.

The `.lua`, `.rbxmx`, and library exports validate each mesh.

- Missing or invalid `MeshPart.properties.MeshId` blocks export and returns an error with a structured manifest of missing assets.
- An explicit mapping may be a positive decimal ID, `rbxassetid://ID`, or an official Roblox URL. Local `rbxasset://...` paths and ID 0 cannot identify a permanent asset for an imported mesh.
- With a mapping, exports keep the native properties and animation tracks and remove `editor.meshes` from the Luau payload. Preview buffers stay in the editor.
- Check the permissions, geometry, normals, and UVs in the target experience. The ID alone does not verify those details.

Composing through `merge_recipes` or inclusion preserves the metadata with the new node IDs. Each copy is independent of its source. Every included local mesh still needs an import in Roblox.

Use the Python API to inspect the manifest.

```python
from tool.fx_tools import export_manifest, export
manifest = export_manifest(recipe)
export(recipe, "manifest", "exports/MonEffet.assets.json")
```

`MeshExportError.manifest` returns the same data to HTTP and MCP clients. `missing_assets` and `mapped_assets` include the node IDs and provenance and omit the buffers. If validation fails, no native export is written and existing projects stay intact.

## Map a local mesh to Roblox

1. Keep the original OBJ. The JSON saves the preview data.
2. Import the OBJ with Studio's 3D importer from your authorised account.
3. Check the axes, units in studs, pivot, size, normals, double-sided rendering, and UVs.
4. Verify permissions for the mesh and its textures in the target experience.
5. Enter the returned MeshId on the MeshPart in the editor and export.
6. Compare the native scene and preview at matching times from several angles.

This workflow currently covers OBJ. FBX, glTF, GLB, PBR materials, SurfaceAppearance, rigs, Bones, skinning, and AnimationController require their own pipeline. Support for a general format does not guarantee it can use Roblox's import pipeline.

## Runtime behaviour and limits

The Roblox runtime loads meshes through `AssetService:CreateMeshPartAsync(Content.fromUri(...))`. The multi-instance kit preloads explicitly with `FX.preload(recipe)`. `FX.play` then clones the template without yielding. The runtime does not reassign MeshId on an empty MeshPart.

The kit requires `runtime:true` on Part and MeshPart `Position` and `Transparency` tracks. Compiled motion already sets this flag. `Orientation`, `Size`, and other numeric tracks are preserved. Existing projects keep their behaviour. Attachments use local coordinates relative to their parent. Parts use recipe coordinates. Folders and Models do not introduce a separate animated coordinate frame.

The legacy Lua module and `.rbxmx` player apply pivot translation to position tracks. Use `FX.play(recipe, CFrame, ...)`, `Move`, and `follow` in the kit to compose rotation and scale. Easing curves are sampled into linearly interpolated keys, which approximates their timing. A native Trail loses its history during a complete engine pause.

## Verification in the simulator and Studio

Before the changes, 50 export, kit, and motion tests passed using the Luau CLI and a mock of the Roblox API. They cover MeshPart, preloading, runtime keys, rotation, scale, following, Beam and Trail references, multiple instances, and cleanup. The new `test_fx_mesh_export.py` tests cover missing mappings, partial output prevention, the manifest, editable JSON, and preserved tracks. A library from a mapped local mesh was played in Luau with the mock to verify interpolation, origin rotation, scale, transparency, and cleanup. After the changes, **85 tests passed**, including seven new tests, across `test_fx_mesh_export`, `test_fx_rbxmx`, `test_fx_kit`, `test_fx_motion`, and `test_fx_tools`. The command was run from `tool` with every test enabled.

Integration checks verified that a 17,000-triangle OBJ, about 1.8 MB of text and 7 MB of generated JSON, could be imported, saved, reloaded, inspected through a manifest, and followed by another import. The server rejected native preview for an unmapped mesh before queuing a Studio command. The targeted composition, export, and HTTP/Chromium workflow suite passed all 27 tests.

Studio MCP returned `{"studios":[]}` from `list_roblox_studios` during that session. No place was modified, no asset was uploaded, and no Studio capture was taken. Native comparisons still need to cover Parts and MeshParts, UVs, transparency and occlusion, emitters and flipbooks, Beam curves, Trail history, lighting, camera projection, and timing with matching parameters.

## Official asset APIs reviewed in October 2026

At the time of the review, the Creator Store reference recommended `POST /toolbox-service/v2/assets:search` and listed the legacy GET at the same path as not recommended. Asset details use `GET /toolbox-service/v2/assets/{id}`. Review the contracts and scopes for those beta operations before integration. [Creator Store reference](https://create.roblox.com/docs/cloud/reference/features/creator-store).

For assets you can access, `GET /assets/v1/assets/{assetId}` accepts a `readMask` for metadata. Asset Delivery uses `GET /asset-delivery-api/v1/assetId/{assetId}` with Open Cloud authorisation. Previews are separate from asset contents. `/v1/assets` serves thumbnails and `/v1/assets-thumbnail-3d` serves 3D previews. Authentication depends on the operation and asset permissions. [Assets reference](https://create.roblox.com/docs/cloud/reference/features/assets) · [Assets guide](https://create.roblox.com/docs/cloud/guides/usage-assets).

The proposed acquisition workflow starts with candidate assets and metadata, then checks permissions before inspecting the content. Record creator, URL, dates, licence, and separate permissions for Roblox use, inspection, redistribution, and training. Mark unsupported claims as unknown or pending verification. Permission to use an asset in Roblox does not establish redistribution or training rights. Indexing should not execute third-party scripts. Use pagination and caching, handle HTTP 429 responses, and respect the relevant rules and quotas. [Creator Store restrictions](https://create.roblox.com/docs/production/creator-store) · [Assets and permissions](https://create.roblox.com/docs/projects/assets).
