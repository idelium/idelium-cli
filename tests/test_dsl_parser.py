"""Regression tests for the Idelium DSL v1 parser."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from idelium._internal.dsl import DslSyntaxError, parse_source


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DSL_V1_ROOT = REPOSITORY_ROOT / "docs" / "dsl" / "v1"


class DslParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads(
            (DSL_V1_ROOT / "ast.schema.json").read_text(encoding="utf-8")
        )
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def test_valid_source_produces_canonical_ast(self):
        source = """idelium 1.0

test "Sign in" {
    open "https://example.invalid/login"
    wait css "#email" visible timeout 10s
    write css "#password" value "secret"
    click xpath "//button[@type='submit']"
    assert visible css "#dashboard"
    assert text css "h1" equals "Dashboard"
    back
    forward
    screenshot "dashboard-loaded"
}
"""

        ast = parse_source(source, source_name="sign-in.idelium")

        self.validator.validate(ast)
        self.assertEqual("document", ast["kind"])
        self.assertEqual("sign-in.idelium", ast["sourceName"])
        self.assertEqual("Sign in", ast["tests"][0]["name"])
        self.assertEqual(
            [
                "open",
                "wait",
                "write",
                "click",
                "assertVisibility",
                "assertText",
                "back",
                "forward",
                "screenshot",
            ],
            [statement["kind"] for statement in ast["tests"][0]["statements"]],
        )
        self.assertEqual(
            10000,
            ast["tests"][0]["statements"][1]["timeoutMilliseconds"],
        )
        self.assertTrue(ast["tests"][0]["statements"][2]["sensitive"])
        self.assertEqual(
            {"line": 4, "column": 5},
            ast["tests"][0]["statements"][0]["span"]["start"],
        )

    def test_examples_parse_and_validate_against_schema(self):
        for example in sorted((DSL_V1_ROOT / "examples").glob("*.idelium")):
            with self.subTest(example=example.name):
                ast = parse_source(
                    example.read_text(encoding="utf-8"),
                    source_name=example.name,
                )
                self.validator.validate(ast)
                self.assertEqual(example.name, ast["sourceName"])

    def test_semicolon_separators_and_crlf_are_supported(self):
        source = (
            "idelium 1.0\r\n"
            'test "Compact" { open "https://example.invalid"; '
            'wait css "main" present; screenshot "compact" }\r\n'
        )

        ast = parse_source(source)

        self.validator.validate(ast)
        self.assertEqual(3, len(ast["tests"][0]["statements"]))

    def test_invalid_source_reports_location_and_remediation(self):
        source = (
            'idelium 1.0\n\ntest "Broken" {\n    Open "https://example.invalid"\n}\n'
        )

        with self.assertRaises(DslSyntaxError) as raised:
            parse_source(source)

        diagnostic = raised.exception.diagnostic
        self.assertEqual("IDELIUM_DSL_INVALID_KEYWORD_CASE", diagnostic.code)
        self.assertEqual(4, diagnostic.line)
        self.assertEqual(5, diagnostic.column)
        self.assertIn("lowercase", diagnostic.remediation)

    def test_malformed_string_reports_a_syntax_diagnostic(self):
        source = (
            'idelium 1.0\n\ntest "Broken" {\n    open "https://example.invalid\n}\n'
        )

        with self.assertRaises(DslSyntaxError) as raised:
            parse_source(source)

        self.assertEqual("IDELIUM_DSL_INVALID_STRING", raised.exception.diagnostic.code)
        self.assertEqual(4, raised.exception.diagnostic.line)

    def test_rejects_unsupported_version(self):
        with self.assertRaises(DslSyntaxError) as raised:
            parse_source('idelium 2.0\n\ntest "Future" {}\n')

        self.assertEqual(
            "IDELIUM_DSL_UNSUPPORTED_VERSION",
            raised.exception.diagnostic.code,
        )

    def test_rejects_duplicate_test_names(self):
        source = (
            'idelium 1.0\n\ntest "Duplicate" {}\n\ntest "Duplicate" {\n'
            '    open "https://example.invalid"\n}\n'
        )

        with self.assertRaises(DslSyntaxError) as raised:
            parse_source(source)

        self.assertEqual(
            "IDELIUM_DSL_DUPLICATE_TEST",
            raised.exception.diagnostic.code,
        )

    def test_rejects_boundary_values_before_runtime(self):
        invalid_sources = {
            "empty selector": 'idelium 1.0\n\ntest "T" {\n    click css ""\n}\n',
            "zero timeout": (
                'idelium 1.0\n\ntest "T" {\n    wait css "main" visible timeout 0s\n}\n'
            ),
            "URL credentials": (
                'idelium 1.0\n\ntest "T" {\n'
                '    open "https://user:secret@example.invalid"\n}\n'
            ),
            "bad screenshot": (
                'idelium 1.0\n\ntest "T" {\n    screenshot "../secret"\n}\n'
            ),
        }

        for name, source in invalid_sources.items():
            with self.subTest(name=name):
                with self.assertRaises(DslSyntaxError):
                    parse_source(source)

    def test_diagnostics_do_not_echo_sensitive_literals(self):
        source = 'idelium 1.0\n\ntest "T" {\n    open "https://user:topsecret@example.invalid"\n}\n'

        with self.assertRaises(DslSyntaxError) as raised:
            parse_source(source)

        rendered = str(raised.exception)
        self.assertNotIn("topsecret", rendered)
        self.assertNotIn("user:topsecret", rendered)


if __name__ == "__main__":
    unittest.main()
