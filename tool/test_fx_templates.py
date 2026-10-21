"""Cross-contract tests: actual JS editor templates -> Python schema -> Lua export.

Run from the library folder: python -m unittest tool/test_fx_templates.py -v
No project, snapshot, Studio state, or user library data is written by these tests.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

if __package__:
    from .fx_schema import SCHEMA, ValidationError, validate_project
    from .fx_export import export_project
else:
    from fx_schema import SCHEMA, ValidationError, validate_project
    from fx_export import export_project


class EditorTemplateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="dataky-template-contract-")
        schema_path = Path(cls.temp.name) / "schema.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js est requis pour exécuter les vrais modèles de l’éditeur")
        runner = Path(__file__).with_name("test_fx_frontend.cjs")
        result = subprocess.run([node, str(runner), "--schema", str(schema_path), "--fixtures"], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=15)
        cls.fixtures = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_five_real_templates_validate_and_export(self):
        self.assertEqual(set(self.fixtures), {"empty", "impact", "smoke", "beam", "trail"})
        for kind, fixture in self.fixtures.items():
            with self.subTest(template=kind):
                normalized = validate_project(fixture)
                self.assertEqual(validate_project(normalized), normalized)
                source = export_project(normalized)
                self.assertIsInstance(source, str)
                self.assertGreater(len(source), 1000)
                self.assertIn("Dataky FX", source)
                self.assertEqual(normalized["environment"], fixture["environment"])
                for node in fixture["nodes"]:
                    self.assertIn(node["id"], source)

    def test_real_templates_keep_native_parents_endpoints_and_positions(self):
        for kind in ("impact", "smoke", "beam", "trail"):
            with self.subTest(template=kind):
                fixture = validate_project(self.fixtures[kind])
                nodes = {node["id"]: node for node in fixture["nodes"]}
                for node in nodes.values():
                    if node["class"] == "ParticleEmitter":
                        self.assertEqual(nodes[node["parent"]]["class"], "Attachment")
                    if node["class"] == "Attachment":
                        self.assertIn(nodes[node["parent"]]["class"], {"Part", "MeshPart", "Attachment"})
                        self.assertFalse("Orientation" in node["properties"] and ({"Axis", "SecondaryAxis"} & node["properties"].keys()))
                    if node["class"] in {"Beam", "Trail"}:
                        endpoints = [nodes[node["properties"][key]] for key in ("Attachment0", "Attachment1")]
                        self.assertTrue(all(endpoint["class"] == "Attachment" for endpoint in endpoints))
                        self.assertNotEqual(endpoints[0]["properties"]["Position"], endpoints[1]["properties"]["Position"])
                source_part = next(node for node in nodes.values() if node["class"] == "Part")
                self.assertEqual(source_part["properties"]["Position"], [0, 1, 0])

    def test_real_trail_animates_support_with_valid_native_values(self):
        fixture = validate_project(self.fixtures["trail"])
        animation = fixture["animations"][0]
        nodes = {node["id"]: node for node in fixture["nodes"]}
        self.assertEqual(nodes[animation["node"]]["class"], "Part")
        self.assertEqual(animation["property"], "Position")
        self.assertEqual([frame["time"] for frame in animation["keyframes"]], [0, 1, 2])
        self.assertNotEqual(animation["keyframes"][0]["value"], animation["keyframes"][-1]["value"])

    def test_real_template_sequenced_properties_are_canonical_objects(self):
        for kind in ("impact", "smoke", "beam", "trail"):
            for node in validate_project(self.fixtures[kind])["nodes"]:
                specs = SCHEMA["classes"][node["class"]]["properties"]
                for key, value in node["properties"].items():
                    if specs[key]["type"] in {"NumberSequence", "ColorSequence"}:
                        self.assertIsInstance(value[0], dict, f"{kind} {node['class']}.{key}")
                        self.assertEqual(value[0]["time"], 0)
                        self.assertEqual(value[-1]["time"], 1)

    def test_authoritative_validation_rejects_corrupted_real_recipes(self):
        invalid = deepcopy(self.fixtures["beam"])
        beam = next(node for node in invalid["nodes"] if node["class"] == "Beam")
        beam["properties"]["Attachment0"] = invalid["nodes"][0]["id"]
        with self.assertRaises(ValidationError):
            export_project(invalid)
        invalid = deepcopy(self.fixtures["impact"])
        attachment = next(node for node in invalid["nodes"] if node["class"] == "Attachment")
        attachment["properties"]["Axis"] = [1, 0, 0]
        with self.assertRaises(ValidationError):
            validate_project(invalid)
        invalid = deepcopy(self.fixtures["smoke"])
        invalid["nodes"][0]["properties"]["FutureUnknownProperty"] = 123
        with self.assertRaises(ValidationError):
            validate_project(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
