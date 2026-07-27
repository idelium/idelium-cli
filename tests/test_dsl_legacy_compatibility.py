"""Compatibility corpus for legacy Idelium DSL and payload intent."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By

from idelium._internal.dsl import DslSyntaxError, DslRuntimeOptions, execute_ast, parse_source
from idelium._internal.dsl.linter import lint_source
from tests.test_dsl_runtime import FakeDriver, FakeElement


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "dsl_legacy"


class DslLegacyCompatibilityTest(unittest.TestCase):
    def test_legacy_script_fixture_parses_lints_and_executes_without_network(self):
        source = (FIXTURE_ROOT / "login_legacy.idelium").read_text(encoding="utf-8")
        ast = parse_source(source, source_name="login_legacy.idelium")
        driver = FakeDriver()
        email = driver.add(By.CSS_SELECTOR, "#email", FakeElement())
        password = driver.add(By.CSS_SELECTOR, "#password", FakeElement())
        submit = driver.add(By.XPATH, "//button[@type='submit']", FakeElement())
        driver.add(By.CSS_SELECTOR, "#dashboard", FakeElement(displayed=True))
        driver.add(By.CSS_SELECTOR, "h1", FakeElement(text="Dashboard"))

        with tempfile.TemporaryDirectory() as directory:
            result = execute_ast(
                ast,
                driver,
                options=DslRuntimeOptions(
                    screenshot_directory=directory,
                    sleep=lambda _seconds: None,
                ),
            )

        lint_result = lint_source(source, source_name="login_legacy.idelium")

        self.assertEqual("passed", result["status"])
        self.assertEqual("passed", lint_result["status"])
        self.assertEqual(["user@example.invalid"], email.sent_keys)
        self.assertEqual(["legacy-secret"], password.sent_keys)
        self.assertTrue(submit.clicked)

    def test_legacy_payload_fixture_maps_to_representative_dsl_kinds(self):
        payload = json.loads(
            (FIXTURE_ROOT / "login_payload.json").read_text(encoding="utf-8")
        )
        mapping = {
            "open_browser": "open",
            "wait_for_next_step": "wait",
            "send_keys": "write",
            "click": "click",
            "find_element": "assertVisibility",
            "assert_text": "assertText",
            "back": "back",
            "forward": "forward",
            "screen_shot": "screenshot",
        }

        mapped_kinds = [mapping[step["stepType"]] for step in payload["steps"]]

        self.assertEqual(
            [
                "open",
                "wait",
                "write",
                "write",
                "click",
                "assertVisibility",
                "assertText",
                "back",
                "forward",
                "screenshot",
            ],
            mapped_kinds,
        )

    def test_intentional_incompatibilities_have_migration_diagnostics(self):
        incompatible_sources = {
            "url credentials": (
                'idelium 1.0\n\ntest "T" {\n'
                '    open "https://user:secret@example.invalid"\n}\n'
            ),
            "path screenshot": (
                'idelium 1.0\n\ntest "T" {\n'
                '    screenshot "../secret"\n}\n'
            ),
            "uppercase keyword": (
                'idelium 1.0\n\ntest "T" {\n'
                '    Open "https://example.invalid"\n}\n'
            ),
        }

        for name, source in incompatible_sources.items():
            with self.subTest(name=name):
                with self.assertRaises(DslSyntaxError):
                    parse_source(source)
                lint_result = lint_source(source)
                self.assertEqual("failed", lint_result["status"])
                self.assertEqual("IDL-LINT-SYNTAX", lint_result["diagnostics"][0]["ruleId"])


if __name__ == "__main__":
    unittest.main()
