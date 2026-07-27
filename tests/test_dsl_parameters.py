"""Regression tests for DSL parameter resolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By

from idelium._internal.dsl import (
    DslParameterError,
    DslRuntimeOptions,
    execute_ast,
    parse_source,
    resolve_dsl_parameters,
)
from tests.test_dsl_runtime import FakeDriver, FakeElement


class DslParameterResolutionTest(unittest.TestCase):
    def test_resolves_file_parameters_with_cli_precedence_and_secret_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            parameter_file = Path(directory) / "params.json"
            parameter_file.write_text(
                json.dumps(
                    {
                        "variables": {"baseUrl": "https://file.example.invalid"},
                        "secrets": {"password": "file-secret"},
                    }
                ),
                encoding="utf-8",
            )

            resolved = resolve_dsl_parameters(
                parameter_file=str(parameter_file),
                cli_parameters=["baseUrl=https://cli.example.invalid"],
                cli_secret_parameters=["token=cli-secret"],
            )

        self.assertEqual(
            {
                "baseUrl": "https://cli.example.invalid",
                "password": "file-secret",
                "token": "cli-secret",
            },
            resolved.variables,
        )
        self.assertEqual({"password", "token"}, resolved.secret_names)

    def test_rejects_malformed_parameters_with_stable_code(self):
        with self.assertRaises(DslParameterError) as raised:
            resolve_dsl_parameters(cli_parameters=["not-an-assignment"])

        self.assertEqual(
            "IDELIUM_DSL_PARAMETER_ASSIGNMENT_INVALID",
            raised.exception.code,
        )

    def test_rejects_non_string_file_values(self):
        with tempfile.TemporaryDirectory() as directory:
            parameter_file = Path(directory) / "params.json"
            parameter_file.write_text(
                json.dumps({"variables": {"count": 3}}),
                encoding="utf-8",
            )

            with self.assertRaises(DslParameterError) as raised:
                resolve_dsl_parameters(parameter_file=str(parameter_file))

        self.assertEqual("IDELIUM_DSL_PARAMETER_VALUE_INVALID", raised.exception.code)

    def test_runtime_redacts_secret_parameters_from_output(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "External secret" {\n'
            '    write css "#password" value "${password}"\n'
            "}\n"
        )
        driver = FakeDriver()
        password = driver.add(By.CSS_SELECTOR, "#password", FakeElement())

        result = execute_ast(
            ast,
            driver,
            options=DslRuntimeOptions(
                variables={"password": "external-secret"},
                secret_names={"password"},
            ),
        )

        self.assertEqual(["external-secret"], password.sent_keys)
        self.assertNotIn("external-secret", repr(result))
        self.assertIn("[REDACTED]", repr(result))


if __name__ == "__main__":
    unittest.main()
