"""Tests for offline DSL AST export commands."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator

from idelium._internal import main as cli_main
from idelium._internal.astexport import export_ast_report
from idelium._internal.exitcodes import EXIT_SUCCESS, EXIT_VALIDATION_ERROR


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AST_SCHEMA = REPOSITORY_ROOT / "docs" / "dsl" / "v1" / "ast.schema.json"


class AstExportTest(unittest.TestCase):
    def test_exports_canonical_ast_that_validates_against_schema(self):
        printer = Mock()
        schema = json.loads(AST_SCHEMA.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "login.idelium"
            output_path = Path(directory) / "login.ast.json"
            source_path.write_text(
                'idelium 1.0\n\ntest "Login" {\n  open "https://example.invalid"\n}\n',
                encoding="utf-8",
            )

            export_ast_report(str(source_path), str(output_path), printer)

            ast = json.loads(output_path.read_text(encoding="utf-8"))

        Draft202012Validator(schema).validate(ast)
        self.assertEqual("1.0", ast["schemaVersion"])
        self.assertEqual("1.0", ast["languageVersion"])
        self.assertEqual("login.idelium", ast["sourceName"])
        printer.success.assert_called_once()

    def test_rejects_future_dsl_versions_without_writing_output(self):
        printer = Mock()

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "future.idelium"
            output_path = Path(directory) / "future.ast.json"
            source_path.write_text(
                'idelium 2.0\n\ntest "Future" {\n  open "https://example.invalid"\n}\n',
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit):
                export_ast_report(str(source_path), str(output_path), printer)

            self.assertFalse(output_path.exists())

        self.assertIn(
            "Unsupported DSL language version", printer.danger.call_args.args[0]
        )

    def test_main_ast_export_mode_does_not_require_api_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "minimal.idelium"
            output_path = Path(directory) / "minimal.ast.json"
            source_path.write_text(
                'idelium 1.0\n\ntest "Minimal" {\n  open "https://example.invalid"\n}\n',
                encoding="utf-8",
            )

            with patch.object(cli_main.printer, "print_important_text"):
                exit_code = cli_main.main(
                    [
                        "idelium",
                        "--dslSource",
                        str(source_path),
                        "--astReport",
                        str(output_path),
                    ]
                )

            ast = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual("document", ast["kind"])

    def test_main_ast_export_mode_requires_source_and_output_together(self):
        with (
            patch("builtins.print"),
            patch.object(cli_main.printer, "print_important_text"),
            patch.object(cli_main.printer, "danger") as danger,
        ):
            exit_code = cli_main.main(["idelium", "--dslSource", "test.idelium"])

        self.assertEqual(EXIT_VALIDATION_ERROR, exit_code)
        danger.assert_called_with("dslSource and astReport are required together")


if __name__ == "__main__":
    unittest.main()
