"""Conformance checks for the published Idelium DSL v1 specification."""

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DSL_V1_ROOT = REPOSITORY_ROOT / "docs" / "dsl" / "v1"

STRING = r'"(?:\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4})|[^"\\\x00-\x1f])*"'
LOCATOR = rf"(?:css|xpath)\s+({STRING})"
DURATION = r"[1-9][0-9]*(?:ms|s|m)"

STATEMENT_PATTERNS = {
    "open": re.compile(rf"open\s+({STRING})"),
    "click": re.compile(rf"click\s+{LOCATOR}"),
    "write": re.compile(rf"write\s+{LOCATOR}\s+value\s+({STRING})"),
    "wait": re.compile(
        rf"wait\s+{LOCATOR}\s+(?:present|visible|hidden|clickable)"
        rf"(?:\s+timeout\s+{DURATION})?"
    ),
    "assert_visibility": re.compile(rf"assert\s+(?:visible|hidden)\s+{LOCATOR}"),
    "assert_text": re.compile(
        rf"assert\s+text\s+{LOCATOR}\s+(?:equals|contains)\s+({STRING})"
    ),
    "back": re.compile(r"back"),
    "forward": re.compile(r"forward"),
    "screenshot": re.compile(rf"screenshot\s+({STRING})"),
}


class DslSpecificationTest(unittest.TestCase):
    def test_specification_declares_the_version_and_compatibility_policy(self):
        specification = (DSL_V1_ROOT / "SPECIFICATION.md").read_text(encoding="utf-8")

        self.assertIn("Language version: **1.0**", specification)
        self.assertIn("Specification identifier: **idelium-dsl/1.0**", specification)
        self.assertIn("## 9. Versioning and compatibility", specification)
        self.assertIn("## 10. Security requirements", specification)
        self.assertIn("## 12. Implementation conformance", specification)

    def test_dsl_specification_is_included_in_source_distributions(self):
        manifest = (REPOSITORY_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "recursive-include docs/dsl *.ebnf *.idelium *.json *.md",
            manifest,
        )
        self.assertIn("recursive-include docs/bidi *.md", manifest)
        self.assertIn(
            "https://github.com/idelium/idelium-cli/blob/main/docs/dsl/README.md",
            readme,
        )

    def test_grammar_defines_every_v1_statement(self):
        grammar = (DSL_V1_ROOT / "grammar.ebnf").read_text(encoding="utf-8")

        for rule in (
            "open-statement",
            "click-statement",
            "write-statement",
            "wait-statement",
            "assert-visible-statement",
            "assert-text-statement",
            "back-statement",
            "forward-statement",
            "screenshot-statement",
        ):
            self.assertIn(rule, grammar)

    def test_all_published_examples_conform_to_the_v1_surface(self):
        examples = sorted((DSL_V1_ROOT / "examples").glob("*.idelium"))

        self.assertGreaterEqual(len(examples), 3)
        for example in examples:
            with self.subTest(example=example.name):
                self._validate_example(example)

    def test_canonical_ast_schema_and_example_are_valid(self):
        schema = json.loads(
            (DSL_V1_ROOT / "ast.schema.json").read_text(encoding="utf-8")
        )
        ast = json.loads(
            (DSL_V1_ROOT / "examples" / "complete.ast.json").read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(ast)
        self.assertEqual(ast, json.loads(json.dumps(ast)))
        self.assertEqual(
            {
                "open",
                "wait",
                "write",
                "click",
                "assertVisibility",
                "assertText",
                "back",
                "forward",
                "screenshot",
            },
            {
                statement["kind"]
                for test in ast["tests"]
                for statement in test["statements"]
            },
        )

    def test_canonical_ast_rejects_unknown_or_incompatible_input(self):
        schema = json.loads(
            (DSL_V1_ROOT / "ast.schema.json").read_text(encoding="utf-8")
        )
        valid_ast = json.loads(
            (DSL_V1_ROOT / "examples" / "complete.ast.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        incompatible = {**valid_ast, "schemaVersion": "2.0"}
        unknown_field = {**valid_ast, "credential": "must-not-be-accepted"}
        unknown_statement = json.loads(json.dumps(valid_ast))
        unknown_statement["tests"][0]["statements"][0]["kind"] = "python"

        self.assertFalse(validator.is_valid(incompatible))
        self.assertFalse(validator.is_valid(unknown_field))
        self.assertFalse(validator.is_valid(unknown_statement))

    def _validate_example(self, path):
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertEqual("idelium 1.0", lines[0])
        self.assertGreaterEqual(lines.count("}"), 1)

        inside_test = False
        test_names = set()
        statement_count = 0
        for line in lines[1:]:
            if line.endswith(";"):
                line = line[:-1].rstrip()

            test_match = re.fullmatch(rf"test\s+({STRING})\s+\{{", line)
            if test_match:
                self.assertFalse(inside_test)
                test_name = json.loads(test_match.group(1))
                self.assertTrue(test_name.strip())
                self.assertNotIn(test_name, test_names)
                test_names.add(test_name)
                inside_test = True
                continue

            if line == "}":
                self.assertTrue(inside_test)
                inside_test = False
                continue

            self.assertTrue(inside_test)
            statement_name = self._statement_name(line)
            self.assertIsNotNone(statement_name, f"Unsupported DSL statement: {line}")
            self._validate_statement_literals(statement_name, line)
            statement_count += 1

        self.assertFalse(inside_test)
        self.assertTrue(test_names)
        self.assertGreater(statement_count, 0)

    @staticmethod
    def _statement_name(line):
        for name, pattern in STATEMENT_PATTERNS.items():
            if pattern.fullmatch(line):
                return name
        return None

    def _validate_statement_literals(self, statement_name, line):
        pattern = STATEMENT_PATTERNS[statement_name]
        match = pattern.fullmatch(line)
        literals = [json.loads(value) for value in match.groups() if value]
        self.assertTrue(all(value for value in literals))

        if statement_name == "open":
            parsed = urlsplit(literals[0])
            self.assertIn(parsed.scheme, {"http", "https"})
            self.assertTrue(parsed.netloc)
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)

        if statement_name == "screenshot":
            self.assertRegex(literals[0], r"^[A-Za-z0-9._-]+$")
            self.assertNotIn("..", literals[0])


if __name__ == "__main__":
    unittest.main()
