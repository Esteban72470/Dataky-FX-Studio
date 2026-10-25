import copy
import math
import unittest

from fx_mesh import import_obj, validate_mesh, MeshError, MAX_OBJ_BYTES
from fx_schema import validate_project, ValidationError


TRIANGLE = "v -2 -1 0\nv 2 -1 0\nv 0 3 0\nvt 0 0\nvt 1 0\nvt .5 1\nf 1/1 2/2 3/3\n"


class ObjImportTests(unittest.TestCase):
    def test_obj_normalizes_geometry_preserves_uvs_dimensions_and_provenance(self):
        imported = import_obj(TRIANGLE, "slash", name="slash.obj")
        self.assertEqual(imported["node"]["properties"]["Size"], [4, 4, .001])
        self.assertEqual(imported["mesh"]["positions"], [-.5,-.5,0,.5,-.5,0,0,.5,0])
        self.assertEqual(imported["mesh"]["uvs"], [0,1,1,1,.5,0])
        self.assertEqual(imported["mesh"]["normals"], [0,0,1]*3)
        self.assertEqual(imported["mesh"]["indices"], [0,1,2])
        self.assertEqual(len(imported["mesh"]["source"]["sha256"]), 64)
        self.assertIn("Aperçu local", " ".join(imported["warnings"]))

    def test_obj_negative_indices_convex_quads_and_explicit_normals(self):
        obj = "v 0 0 0\nv 4 0 0\nv 4 2 0\nv 0 2 0\nvn 0 0 2\nf -4//1 -3//1 -2//1 -1//1"
        imported = import_obj(obj, mesh_id="rbxassetid://123")
        self.assertEqual(imported["mesh"]["indices"], [0,1,2,0,2,3])
        self.assertEqual(imported["mesh"]["normals"], [0,0,1]*4)
        self.assertEqual(imported["warnings"], [])

    def test_material_references_are_not_opened_or_executed(self):
        obj = 'mtllib ../../secret.mtl\nusemtl https://invalid/evil\n' + TRIANGLE
        imported = import_obj(obj)
        self.assertTrue(any("aucune ressource externe" in w for w in imported["warnings"]))
        self.assertEqual(len(imported["mesh"]["indices"]), 3)

    def test_invalid_or_unsupported_obj_fails_explicitly(self):
        cases = ["", "v NaN 0 0", "v inf 0 0", "v 0 0 0 0", TRIANGLE.replace("3/3", "99/3"),
                 TRIANGLE.replace("1/1", "0/1"), TRIANGLE.replace("1/1", "1/a"),
                 TRIANGLE + "\ncurv 0 1 2 3", "#" * (MAX_OBJ_BYTES + 1),
                 "v 0 0 0\nv 1 0 0\nv 2 0 0\nf 1 2 3",
                 "v 0 0 0\nv 3 0 0\nv 1 1 0\nv 3 3 0\nv 0 3 0\nf 1 2 3 4 5",
                 "v 0 0 0\nv 1 0 0\nv 1 1 1\nv 0 1 0\nf 1 2 3 4"]
        for obj in cases:
            with self.subTest(obj=obj[:80]), self.assertRaises(MeshError):
                import_obj(obj)
        with self.assertRaises(MeshError):
            import_obj(TRIANGLE, mesh_id="https://external.invalid/mesh")

    def test_schema_roundtrip_and_rejects_orphan_or_unbounded_geometry(self):
        imported = import_obj(TRIANGLE, "slash")
        project = {"version": 1, "name": "OBJ", "duration": 1, "nodes": [imported["node"]],
                   "editor": {"version": 1, "meshes": {"slash": imported["mesh"]}}}
        clean = validate_project(project)
        self.assertEqual(clean["editor"]["meshes"], project["editor"]["meshes"])
        cases = []
        orphan = copy.deepcopy(project); orphan["nodes"][0]["id"] = "other"; cases.append(orphan)
        for field, bad in [("positions", [math.nan]*9), ("positions", [9]*9), ("normals", [0]*9),
                           ("uvs", [0]*2), ("indices", [0,1,10]), ("indices", [True,1,2])]:
            invalid = copy.deepcopy(project); invalid["editor"]["meshes"]["slash"][field] = bad; cases.append(invalid)
        invalid = copy.deepcopy(project); invalid["editor"]["meshes"]["slash"]["script"] = "execute()"; cases.append(invalid)
        for invalid in cases:
            with self.subTest(invalid=repr(invalid)[:80]), self.assertRaises(ValidationError):
                validate_project(invalid)


if __name__ == "__main__":
    unittest.main()
