"""Validation tests for published DSL examples."""

from __future__ import annotations

import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from idelium._internal.dsl import lint_source, parse_source


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DSL_V1_ROOT = REPOSITORY_ROOT / "docs" / "dsl" / "v1"


class DslExampleValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json

        cls.validator = Draft202012Validator(
            json.loads((DSL_V1_ROOT / "ast.schema.json").read_text(encoding="utf-8")),
            format_checker=FormatChecker(),
        )

    def test_published_examples_parse_validate_and_lint(self):
        for example in sorted((DSL_V1_ROOT / "examples").glob("*.idelium")):
            with self.subTest(example=example.name):
                source = example.read_text(encoding="utf-8")
                ast = parse_source(source, source_name=example.name)
                lint_result = lint_source(source, source_name=example.name)

                self.validator.validate(ast)
                self.assertEqual("passed", lint_result["status"])


if __name__ == "__main__":
    unittest.main()
