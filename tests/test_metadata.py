"""Keep supported Python metadata and CI configuration synchronized."""

import ast
import pathlib
import re
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
