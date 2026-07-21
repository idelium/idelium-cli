"""Keep supported Python metadata and CI configuration synchronized."""

import ast
import importlib.util
import pathlib
import re
import runpy
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SUPPORTED_VERSIONS = ["3.10", "3.11", "3.12", "3.13"]


class MetadataConsistencyTest(unittest.TestCase):
    def test_python_support_metadata_matches_ci_and_documentation(self):
        setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn('python_requires=">=3.10,<3.14"', setup_source)
        for version in SUPPORTED_VERSIONS:
            self.assertIn(
                '"Programming Language :: Python :: {}"'.format(version),
                setup_source,
            )
            self.assertIn(version, readme)
            self.assertIn("'{}'".format(version), workflow)

        classified_versions = re.findall(
            r'"Programming Language :: Python :: (3\.\d+)"',
            setup_source,
        )
        self.assertEqual(SUPPORTED_VERSIONS, classified_versions)

    def test_setup_file_remains_valid_python(self):
        setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
        ast.parse(setup_source)

    def test_public_package_version_matches_internal_version(self):
        internal = runpy.run_path(str(ROOT / "src/idelium/_internal/main.py"))
        spec = importlib.util.spec_from_file_location(
            "idelium",
            ROOT / "src/idelium/__init__.py",
            submodule_search_locations=[str(ROOT / "src/idelium")],
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(internal["IDELIUM_VERSION"], module.__version__)

    def test_local_test_script_is_documented_and_packaged(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        script = ROOT / "scripts/test-package.sh"

        self.assertTrue(script.exists())
        self.assertIn("scripts/test-package.sh", readme)
        self.assertIn("recursive-include scripts *.sh", manifest)

    def test_project_license_metadata_is_apache_2(self):
        setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn("license='Apache-2.0'", setup_source)
        self.assertIn("Apache License 2.0", readme)
        self.assertIn("include LICENSE", manifest)
        self.assertIn("Apache License", license_text)
