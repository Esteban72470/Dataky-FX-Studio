"""Freshness, exhaustive retrieval, provenance and reusable local OBJ registry."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

try:
    from . import fx_ai_catalog as catalog
    from .fx_mesh import import_obj
except ImportError:
    import fx_ai_catalog as catalog
    from fx_mesh import import_obj

OBJ = "v -1 0 0\nv 1 0 0\nv 0 2 0\nvt 0 0\nvt 1 0\nvt .5 1\nf 1/1 2/2 3/3\n"


def row(ident, name, **values):
    return {"asset_id": str(ident), "name": name, "uri": f"rbxassetid://{ident}", "id_status": "valid", "tags": [], **values}


class LiveCatalogue(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for source in catalog.SOURCES.values():
            self.write(source, [])

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_add_edit_remove_and_same_stat_changes_are_immediately_visible(self):
        path = self.write("textures.json", [row(101, "Alpha")])
        first = catalog.snapshot(self.root)
        stamp = path.stat()
        self.write("textures.json", [row(101, "Bravo")])  # same serialized byte count
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        second = catalog.snapshot(self.root)
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(catalog.search("Bravo", root=self.root)["items"][0]["id"], "101")
        self.assertEqual(catalog.search("Bravo", snapshot=first)["total"], 0, "explicit snapshots remain coherent")
        self.write("textures.json", [row(101, "Bravo"), row(102, "New")])
        self.assertEqual(catalog.search(root=self.root)["total"], 2)
        path.unlink()
        self.assertEqual(catalog.search(root=self.root)["total"], 0)

    def test_invalid_changed_json_fails_instead_of_serving_old_catalogue(self):
        path = self.write("textures.json", [row(101, "Alpha")])
        self.assertEqual(catalog.snapshot(self.root)["counts"]["total"], 1)
        path.write_text("[{broken", encoding="utf-8")
        with self.assertRaisesRegex(catalog.CatalogError, "JSON invalide"):
            catalog.snapshot(self.root)
        path.write_text('[{"asset_id":"101","name":NaN}]', encoding="utf-8")
        with self.assertRaises(catalog.CatalogError):
            catalog.snapshot(self.root)
        self.write("textures.json", [row(102, "Fixed")])
        self.assertEqual(catalog.snapshot(self.root)["assets"][0]["id"], "102")

    def test_snapshot_retries_when_a_file_changes_during_read(self):
        self.write("textures.json", [row(101, "Alpha")])
        original = catalog._read
        changed = []
        def concurrent_read(path):
            body = original(path)
            if path.name == "textures.json" and not changed:
                changed.append(True)
                self.write("textures.json", [row(101, "Alpha"), row(102, "Added")])
            return body
        with patch.object(catalog, "_read", side_effect=concurrent_read):
            result = catalog.snapshot(self.root)
        self.assertEqual(result["counts"]["textures"], 2)

    def test_editor_rows_and_revision_use_the_same_content_snapshot(self):
        self.write("textures.json", [row(101,"Before")])
        original = catalog._read
        changed = []
        def concurrent_read(path):
            body = original(path)
            if path.name == "textures.json" and not changed:
                changed.append(True)
                self.write("textures.json",[row(101,"Before"),row(102,"After")])
            return body
        with patch.object(catalog,"_read",side_effect=concurrent_read):
            editor = catalog.editor_catalog(self.root)
        self.assertEqual(len(editor["textures"]),2)
        self.assertEqual(editor["revision"],catalog.snapshot(self.root)["revision"])
        catalog.register_mesh(import_obj(OBJ),root=self.root)
        editor = catalog.editor_catalog(self.root)
        self.assertTrue(editor["meshes"][0]["local_key"].startswith("local-"))
        self.assertEqual(editor["revision"],catalog.snapshot(self.root)["revision"])

    def test_three_collections_deduplicate_ids_but_keep_searchable_aliases(self):
        self.write("textures.json", [row(101, "Alpha"), row(101, "Other", tags=["Smoke"]), row(0, "Invalid"), {"asset_id": "not-id"}])
        self.write("beams/assets.json", [row(101, "Beam", kind="beam")])
        self.write("meshes/assets.json", [row(103, "Mesh", kind="mesh", references=[{"label":"MeshId","uri":"rbxassetid://303"}]),
                                         row(303, "Spiral", references=[{"label":"TextureId","uri":"rbxassetid://404"}])])
        snap = catalog.snapshot(self.root)
        self.assertEqual(snap["counts"]["total"], 4)
        self.assertEqual(snap["counts"]["skipped"], 2)
        self.assertEqual(snap["raw_counts"], {"textures":4,"beams":1,"meshes":2})
        self.assertEqual(catalog.search("Other", snapshot=snap)["items"][0]["id"], "101")
        mesh = catalog.get_asset("meshes:303", snapshot=snap)
        self.assertEqual(mesh["mesh_texture_id"], "")
        self.assertEqual(catalog.get_asset("meshes:303@404",snapshot=snap)["mesh_texture_id"],"rbxassetid://404")
        with self.assertRaisesRegex(catalog.CatalogError,"ambigu"):
            catalog.get_asset("101", snapshot=snap)

    def test_mesh_variants_keep_untextured_and_each_distinct_texture(self):
        untextured=row(1051557,"Simple Thick Spring",kind="mesh",references=[{"label":"MeshId","uri":"rbxassetid://1051557"}])
        textured=row(1051557,"Spiral",kind="mesh",references=[{"label":"MeshId","uri":"rbxassetid://1051557"},
                                                                  {"label":"TextureId","uri":"rbxassetid://98468789881853"}])
        alternate=row(1051557,"Spiral alternative",kind="mesh",references=[{"label":"TextureId","uri":"rbxassetid://456"}])
        duplicate={**textured,"name":"Spiral alias","tags":["Wind"]}
        self.write("meshes/assets.json",[textured,untextured,alternate,duplicate])
        snap=catalog.snapshot(self.root)
        self.assertEqual(snap["counts"]["meshes"],3)
        self.assertEqual(catalog.get_asset("meshes:1051557",snapshot=snap)["mesh_texture_id"],"")
        key="meshes:1051557@98468789881853"
        self.assertEqual(catalog.get_asset(key,snapshot=snap)["mesh_texture_id"],"rbxassetid://98468789881853")
        self.assertIn("Spiral alias",catalog.get_asset(key,snapshot=snap)["aliases"])
        self.assertEqual(catalog.search(key,snapshot=snap)["items"][0]["key"],key)
        self.assertEqual(catalog.search("1051557",collection="meshes",snapshot=snap)["total"],3)
        with self.assertRaisesRegex(catalog.CatalogError,"ambigu"):
            catalog.get_asset("1051557",snapshot=snap)
        self.write("meshes/assets.json",[duplicate,alternate,untextured,textured])
        reordered=catalog.snapshot(self.root)
        self.assertEqual({a["key"]:a["mesh_texture_id"] for a in reordered["assets"]},
                         {a["key"]:a["mesh_texture_id"] for a in snap["assets"]})

    def test_new_textured_variant_is_live_without_replacing_the_base(self):
        original=row(321,"Untextured",kind="mesh")
        self.write("meshes/assets.json",[original])
        before=catalog.snapshot(self.root)
        added=row(321,"Added texture",kind="mesh",references=[{"label":"TextureId","uri":"rbxassetid://654"}])
        self.write("meshes/assets.json",[original,added])
        after=catalog.snapshot(self.root)
        self.assertNotEqual(before["revision"],after["revision"])
        self.assertEqual(catalog.get_asset("meshes:321",snapshot=after)["mesh_texture_id"],"")
        self.assertEqual(catalog.get_asset("meshes:321@654",snapshot=after)["mesh_texture_id"],"rbxassetid://654")

    def test_all_textured_variants_choose_a_stable_base_independent_of_row_order(self):
        high=row(321,"High",kind="mesh",references=[{"label":"TextureId","uri":"rbxassetid://999"}])
        low=row(321,"Low",kind="mesh",references=[{"label":"TextureId","uri":"rbxassetid://555"}])
        self.write("meshes/assets.json",[high,low])
        first=catalog.snapshot(self.root)
        self.assertEqual(catalog.get_asset("meshes:321",snapshot=first)["mesh_texture_id"],"rbxassetid://555")
        self.assertEqual(catalog.get_asset("meshes:321@999",snapshot=first)["mesh_texture_id"],"rbxassetid://999")
        self.write("meshes/assets.json",[low,high])
        second=catalog.snapshot(self.root)
        self.assertEqual(catalog.get_asset("meshes:321",snapshot=second)["mesh_texture_id"],"rbxassetid://555")

    def test_french_english_names_tags_aliases_and_exact_id_priority(self):
        self.write("textures.json", [row(101, "Arcane Ring", tags=["Ground"]), row(102, "Custom", aliases=["Éclat furtif"]), row(103,"Bright Glare")])
        self.write("meshes/assets.json", [row(201,"Shockwave")])
        self.write("beams/assets.json", [row(301,"Zigzag",tags=["Lightning"])])
        self.assertEqual(catalog.search("anneau", collection="meshes",root=self.root)["items"][0]["id"], "201")
        self.assertEqual(catalog.search("éclair",collection="beams",root=self.root)["items"][0]["id"], "301")
        self.assertEqual(catalog.search("eclat furtif",root=self.root)["items"][0]["id"], "102")
        self.assertEqual(catalog.search("ring 103",root=self.root)["items"][0]["id"], "103")
        self.assertEqual(catalog.search("meshes:201",root=self.root)["items"][0]["key"], "meshes:201")
        self.assertTrue(all(a["visual_status"] == "unknown" for a in catalog.snapshot(self.root)["assets"]))

    def test_explicit_query_match_beats_older_generic_role_match(self):
        self.write("textures.json",[row(101,"Flash",tags=["Light"]),row(102,"New entry",tags=["AzuraCustom"])])
        self.assertEqual(catalog.search("AzuraCustom",role="flash",root=self.root)["items"][0]["id"],"102")
        self.assertEqual(catalog.search("not-found",role="flash",root=self.root)["items"][0]["id"],"101")

    def test_grid_overrides_and_actual_annotations_are_reloaded(self):
        self.write("textures.json", [row(101,"Loop",kind="flipbook",grid=8,grid_source="inferred_from_name")])
        first = catalog.snapshot(self.root)
        self.assertTrue(first["assets"][0]["flipbook"]["estimated"])
        self.write("tool/grid_overrides.json", {"version":1,"grids":{"101":4}})
        self.write("editor/artistry/assets.json", {"version":1,"assets":{"textures:101":{"metadata":{"shape":["ring"],"notes":"Observed a narrow ring"},
            "provenance":{"shape":{"observer":"human","evidence":{"sha256":"proof"}}}}}})
        second = catalog.snapshot(self.root)
        asset = second["assets"][0]
        self.assertNotEqual(first["revision"],second["revision"])
        self.assertEqual(asset["flipbook"],{"grid":4,"FlipbookLayout":"Grid4x4","estimated":False})
        self.assertEqual(asset["metadata"],{"shape":["ring"]},"unproven metadata never becomes observed")
        self.assertEqual(asset["visual_status"],"observed")

    def test_missing_thumbnail_is_still_searchable_and_licenses_stay_unknown(self):
        self.write("textures.json", [row(101,"Unknown",image_path="images/101.png")])
        asset=catalog.search(root=self.root)["items"][0]
        self.assertEqual(asset["image"],"images/101.png")
        self.assertIsNone(asset["provenance"]["license"])
        self.assertIsNone(asset["provenance"]["creator"])

    def test_pagination_can_reach_every_asset_and_search_never_mutates_snapshot(self):
        self.write("textures.json", [row(100+i,f"Asset {i}") for i in range(8)])
        snap = catalog.snapshot(self.root)
        seen = [catalog.search(snapshot=snap,limit=1,offset=i)["items"][0]["id"] for i in range(8)]
        self.assertEqual(len(set(seen)),8)
        found = catalog.search(snapshot=snap)["items"]
        found[0]["tags"].append("Changed")
        self.assertEqual(snap["assets"][0]["tags"],[])
        for kwargs in ({"limit":True},{"limit":121},{"offset":-1},{"collection":"private"}):
            with self.assertRaises(catalog.CatalogError):
                catalog.search(snapshot=snap,**kwargs)

    def test_register_obj_reuse_mapping_and_content_addressed_geometry(self):
        imported=import_obj(OBJ,"triangle",name="Arcane triangle.obj")
        original=deepcopy(imported)
        first=catalog.register_mesh(imported,root=self.root,tags=["Slash","Custom"])
        self.assertEqual(imported,original)
        self.assertEqual(first["uri"],"")
        self.assertEqual(catalog.load_geometry(first,root=self.root),imported["mesh"])
        snap=catalog.snapshot(self.root)
        self.assertEqual(snap["counts"]["local_meshes"],1)
        self.assertEqual(catalog.search("triangle",collection="meshes",root=self.root)["items"][0]["id"],first["id"])
        imported["node"]["properties"]["MeshId"]="rbxassetid://987"
        second=catalog.register_mesh(imported,root=self.root)
        self.assertEqual(second["id"],first["id"])
        self.assertEqual(second["mesh_id"],"rbxassetid://987")
        self.assertEqual(catalog.snapshot(self.root)["counts"]["meshes"],1)
        entry=catalog.local_entries(self.root)[0]
        self.assertEqual(entry["local_key"],first["id"])
        self.assertEqual(entry["references"][0]["label"],"MeshId")
        self.assertEqual(catalog.get_asset(first["id"],root=self.root)["key"],first["key"])

    def test_register_unchanged_mesh_is_idempotent_and_keeps_source_provenance(self):
        imported=import_obj(OBJ,"triangle",name="Library source.obj")
        first=catalog.register_mesh(imported,root=self.root,tags=["Slash"])
        path=self.root/catalog.REGISTRY
        registry=json.loads(path.read_text(encoding="utf-8"))
        registry["assets"][0]["provenance"]["license"]="Permission recorded by owner"
        registry["assets"][0]["provenance"]["creator"]={"name":"Local author"}
        registry["assets"][0]["metadata"]={"usage":["Verified author note"]}
        self.write(catalog.REGISTRY,registry)
        before=path.read_bytes(),path.stat().st_mtime_ns,catalog.snapshot(self.root)["revision"]
        second=catalog.register_mesh(imported,root=self.root)
        self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns,catalog.snapshot(self.root)["revision"]),before)
        self.assertEqual(second["provenance"],registry["assets"][0]["provenance"])
        self.assertEqual(second["metadata"],registry["assets"][0]["metadata"])
        self.assertEqual(first["id"],second["id"])

    def test_saved_effect_name_becomes_alias_and_mapping_updates_only_once(self):
        imported=import_obj(OBJ,"triangle",name="Library source.obj")
        first=catalog.register_mesh(imported,root=self.root,tags=["Slash"])
        imported["node"]["name"]="Generated attack layer"
        imported["node"]["properties"].update(MeshId="rbxassetid://123",TextureID="rbxassetid://456")
        second=catalog.register_mesh(imported,root=self.root,tags=["Ground"])
        self.assertEqual(second["name"],"Library source.obj")
        self.assertIn("Generated attack layer",second["aliases"])
        self.assertEqual(second["tags"],["Slash","Ground"])
        self.assertEqual(second["mesh_id"],"rbxassetid://123")
        self.assertEqual(second["mesh_texture_id"],"rbxassetid://456")
        self.assertEqual(second["provenance"],first["provenance"])
        path=self.root/catalog.REGISTRY
        before=path.read_bytes(),path.stat().st_mtime_ns,catalog.snapshot(self.root)["revision"]
        self.assertEqual(catalog.register_mesh(imported,root=self.root),second)
        self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns,catalog.snapshot(self.root)["revision"]),before)
        imported["node"]["properties"].update(MeshId="",TextureID="")
        self.assertEqual(catalog.register_mesh(imported,root=self.root),second)
        imported["node"]["properties"].update(MeshId="rbxassetid://789",TextureID="rbxassetid://987")
        updated=catalog.register_mesh(imported,root=self.root)
        self.assertEqual(updated["id"],first["id"])
        self.assertEqual(updated["mesh_id"],"rbxassetid://789")
        self.assertEqual(updated["mesh_texture_id"],"rbxassetid://987")
        self.assertEqual(updated["provenance"],first["provenance"])
        self.assertNotEqual(catalog.snapshot(self.root)["revision"],before[2])

    def test_parallel_registrations_do_not_lose_assets(self):
        imports=[import_obj(OBJ+f"# different {i}\n",f"mesh{i}") for i in range(6)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda imported:catalog.register_mesh(imported,root=self.root),imports))
        self.assertEqual(catalog.snapshot(self.root)["counts"]["local_meshes"],6)
        self.assertFalse((self.root/"editor/local_ai/.catalog.lock").exists())

    def test_independent_processes_share_the_same_atomic_registry(self):
        program = '''
import sys
sys.path.insert(0, sys.argv[1])
from fx_ai_catalog import register_mesh
from fx_mesh import import_obj
text = "v -1 0 0\\nv 1 0 0\\nv 0 2 0\\nf 1 2 3\\n# process " + sys.argv[3]
register_mesh(import_obj(text),root=sys.argv[2])
'''
        processes=[subprocess.Popen([sys.executable,"-c",program,str(Path(catalog.__file__).parent),str(self.root),str(i)],
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(3)]
        for process in processes:
            stdout,stderr=process.communicate(timeout=20)
            self.assertEqual(process.returncode,0,stdout+stderr)
        self.assertEqual(catalog.snapshot(self.root)["counts"]["local_meshes"],3)

    def test_registry_rejects_external_paths_and_tampered_geometry(self):
        registered=catalog.register_mesh(import_obj(OBJ),root=self.root)
        bad={**registered,"geometry_path":"../../private.json"}
        with self.assertRaises(catalog.CatalogError):
            catalog.load_geometry(bad,root=self.root)
        self.write(catalog.REGISTRY,{"version":1,"assets":[bad]})
        with self.assertRaises(catalog.CatalogError):
            catalog.snapshot(self.root)
        self.write(catalog.REGISTRY,{"version":1,"assets":[registered]})
        path=self.root/registered["geometry_path"]
        path.write_text("{}",encoding="utf-8")
        with self.assertRaisesRegex(catalog.CatalogError,"empreinte"):
            catalog.load_geometry(registered,root=self.root)


if __name__=="__main__":
    unittest.main()
