"""Regression tests for the network-free DSL linter."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from idelium._internal import main as cli_main
from idelium._internal.dsl import lint_source
from idelium._internal.exitcodes import EXIT_SUCCESS, EXIT_VALIDATION_ERROR


class DslLinterTest(unittest.TestCase):
    def test_linter_reports_stable_rules_with_source_locations(self):
        source = """idelium 1.0

test "Lint" {
    open "http://example.invalid"
    wait css "#ready" visible
    use missing()
}
"""

        result = lint_source(source, source_name="lint.idelium")

        self.assertEqual("dsl-lint-result.v1", result["schemaVersion"])
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, result["summary"]["errors"])
        self.assertEqual(2, result["summary"]["warnings"])
        rules = [diagnostic["ruleId"] for diagnostic in result["diagnostics"]]
        self.assertEqual(
            [
                "IDL-LINT-INSECURE-URL",
                "IDL-LINT-IMPLICIT-WAIT-TIMEOUT",
                "IDL-LINT-UNKNOWN-STEP",
            ],
            rules,
        )
        self.assertEqual(
            {"line": 4, "column": 5},
            result["diagnostics"][0]["span"]["start"],
        )

    def test_syntax_errors_are_lint_errors(self):
        result = lint_source('idelium 1.0\n\ntest "Broken" { Open "x" }\n')

        self.assertEqual("failed", result["status"])
        self.assertEqual("IDL-LINT-SYNTAX", result["diagnostics"][0]["ruleId"])
        self.assertEqual("error", result["diagnostics"][0]["severity"])

    def test_cli_lint_mode_writes_report_and_returns_validation_error_on_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "lint.idelium"
            report_path = Path(directory) / "lint.json"
            source_path.write_text(
                'idelium 1.0\n\ntest "Lint" {\n  use missing()\n}\n',
                encoding="utf-8",
            )

            with patch.object(cli_main.printer, "print_important_text"):
                exit_code = cli_main.main(
                    [
                        "idelium",
                        "--dslLint",
                        str(source_path),
                        "--dslLintReport",
                        str(report_path),
                    ]
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(EXIT_VALIDATION_ERROR, exit_code)
        self.assertEqual("failed", report["status"])

    def test_cli_lint_mode_returns_success_for_warnings_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "lint.idelium"
            source_path.write_text(
                'idelium 1.0\n\ntest "Lint" {\n  open "http://example.invalid"\n}\n',
                encoding="utf-8",
            )

            with patch.object(cli_main.printer, "print_important_text"):
                exit_code = cli_main.main(["idelium", "--dslLint", str(source_path)])

        self.assertEqual(EXIT_SUCCESS, exit_code)


if __name__ == "__main__":
    unittest.main()
