"""Regression tests for the Idelium DSL AST runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from idelium._internal.dsl import DslRuntimeOptions, execute_ast, parse_source


class FakeElement:
    def __init__(self, *, text="", displayed=True, enabled=True):
        self.text = text
        self.displayed = displayed
        self.enabled = enabled
        self.clicked = False
        self.sent_keys = []

    def click(self):
        self.clicked = True

    def send_keys(self, value):
        self.sent_keys.append(value)

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled


class FakeDriver:
    def __init__(self):
        self.elements = {}
        self.calls = []

    def add(self, strategy, selector, element):
        self.elements[(strategy, selector)] = element
        return element

    def get(self, url):
        self.calls.append(("get", url))

    def back(self):
        self.calls.append(("back",))

    def forward(self):
        self.calls.append(("forward",))

    def find_element(self, strategy, selector):
        self.calls.append(("find_element", strategy, selector))
        try:
            return self.elements[(strategy, selector)]
        except KeyError as error:
            raise NoSuchElementException(selector) from error

    def get_screenshot_as_file(self, path):
        self.calls.append(("screenshot", path))
        Path(path).write_text("fake image", encoding="utf-8")
        return True


class DslRuntimeTest(unittest.TestCase):
    def test_executes_minimal_browser_command_set_end_to_end(self):
        source = """idelium 1.0

test "Runtime smoke" {
    open "https://example.invalid/login?token=secret"
    wait css "#email" visible timeout 250ms
    write css "#email" value "user@example.invalid"
    click xpath "//button[@type='submit']"
    assert visible css "#dashboard"
    assert text css "h1" equals "Dashboard"
    back
    forward
    screenshot "runtime-smoke"
}
"""
        ast = parse_source(source, source_name="runtime.idelium")
        driver = FakeDriver()
        email = driver.add(By.CSS_SELECTOR, "#email", FakeElement())
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

            self.assertEqual("passed", result["status"])
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
                [statement["kind"] for statement in result["tests"][0]["statements"]],
            )
            self.assertTrue(submit.clicked)
            self.assertEqual(["user@example.invalid"], email.sent_keys)
            self.assertTrue((Path(directory) / "runtime-smoke.png").exists())
            self.assertIn(
                "token=%5BREDACTED%5D",
                result["tests"][0]["statements"][0]["output"]["url"],
            )

    def test_unsupported_node_fails_safely_and_skips_following_nodes(self):
        ast = {
            "kind": "document",
            "schemaVersion": "1.0",
            "languageVersion": "1.0",
            "tests": [
                {
                    "kind": "test",
                    "name": "Unsafe",
                    "statements": [
                        {"kind": "executePython", "code": "print('no')"},
                        {"kind": "open", "url": "https://example.invalid"},
                    ],
                }
            ],
        }

        result = execute_ast(ast, FakeDriver())

        statements = result["tests"][0]["statements"]
        self.assertEqual("failed", result["status"])
        self.assertEqual("failed", statements[0]["status"])
        self.assertEqual(
            "IDELIUM_DSL_RUNTIME_UNSUPPORTED_NODE",
            statements[0]["diagnostics"][0]["code"],
        )
        self.assertEqual("skipped", statements[1]["status"])

    def test_unknown_fields_are_rejected_before_dispatch(self):
        ast = {
            "kind": "document",
            "schemaVersion": "1.0",
            "languageVersion": "1.0",
            "tests": [
                {
                    "kind": "test",
                    "name": "Unknown field",
                    "statements": [
                        {
                            "kind": "click",
                            "locator": {"strategy": "css", "value": "#x"},
                            "plugin": "unsafe",
                        }
                    ],
                }
            ],
        }

        result = execute_ast(ast, FakeDriver())

        diagnostic = result["tests"][0]["statements"][0]["diagnostics"][0]
        self.assertEqual("IDELIUM_DSL_RUNTIME_UNKNOWN_FIELD", diagnostic["code"])
        self.assertIn("plugin", diagnostic["message"])

    def test_sensitive_text_is_redacted_from_results_and_diagnostics(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Sensitive" {\n'
            '    write css "#password" value "super-secret"\n'
            '    assert text css "#password" equals "super-secret"\n'
            "}\n"
        )
        driver = FakeDriver()
        driver.add(By.CSS_SELECTOR, "#password", FakeElement(text="different"))

        result = execute_ast(ast, driver)
        serialized = repr(result)

        self.assertNotIn("super-secret", serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
