"""Regression tests for the Idelium DSL AST runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from idelium._internal.dsl import DslRuntimeOptions, execute_ast, parse_source


class FakeElement:
    def __init__(self, *, text="", displayed=True, enabled=True, attributes=None):
        self.text = text
        self.displayed = displayed
        self.enabled = enabled
        self.attributes = attributes or {}
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

    def get_attribute(self, name):
        return self.attributes.get(name)


class FakeDriver:
    def __init__(self):
        self.elements = {}
        self.calls = []
        self.current_url = "https://example.invalid/dashboard"
        self.title = "Dashboard"

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

    def find_elements(self, strategy, selector):
        self.calls.append(("find_elements", strategy, selector))
        return [
            element
            for (element_strategy, element_selector), element in self.elements.items()
            if element_strategy == strategy and element_selector == selector
        ]

    def get_screenshot_as_file(self, path):
        self.calls.append(("screenshot", path))
        Path(path).write_text("fake image", encoding="utf-8")
        return True


class DslRuntimeTest(unittest.TestCase):
    def test_executes_minimal_browser_command_set_end_to_end(self):
        source = """idelium 1.0

test "Runtime smoke" {
    let baseUrl = "https://example.invalid"
    secret password = "super-secret"
    open "${baseUrl}/login?token=${password}"
    wait css "#email" visible timeout 250ms
    write css "#email" value "${password}"
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
                    "variable",
                    "variable",
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
            self.assertEqual(["super-secret"], email.sent_keys)
            self.assertTrue((Path(directory) / "runtime-smoke.png").exists())
            self.assertIn(
                "token=%5BREDACTED%5D",
                result["tests"][0]["statements"][2]["output"]["url"],
            )
            self.assertEqual(
                "[REDACTED]",
                result["tests"][0]["statements"][4]["output"]["value"],
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

    def test_external_variables_are_interpolated_and_local_variables_take_precedence(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Variables" {\n'
            '    open "${baseUrl}/from-external"\n'
            '    let baseUrl = "https://local.example.invalid"\n'
            '    open "${baseUrl}/from-local"\n'
            "}\n"
        )
        driver = FakeDriver()

        result = execute_ast(
            ast,
            driver,
            options=DslRuntimeOptions(
                variables={"baseUrl": "https://external.example.invalid"}
            ),
        )

        self.assertEqual("passed", result["status"])
        self.assertEqual(
            [
                ("get", "https://external.example.invalid/from-external"),
                ("get", "https://local.example.invalid/from-local"),
            ],
            driver.calls,
        )

    def test_missing_interpolation_variable_fails_without_echoing_placeholder_value(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Missing" {\n'
            '    open "https://example.invalid/${missingSecret}"\n'
            "}\n"
        )

        result = execute_ast(ast, FakeDriver())

        diagnostic = result["tests"][0]["statements"][0]["diagnostics"][0]
        self.assertEqual("failed", result["status"])
        self.assertEqual("IDELIUM_DSL_RUNTIME_MISSING_VARIABLE", diagnostic["code"])
        self.assertNotIn("missingSecret", diagnostic["message"])

    def test_secret_interpolation_is_redacted_from_driver_errors(self):
        class EchoingDriver(FakeDriver):
            def get(self, url):
                raise RuntimeError("navigation failed for " + url)

        ast = parse_source(
            'idelium 1.0\n\ntest "Secret diagnostic" {\n'
            '    secret token = "top-secret-token"\n'
            '    open "https://example.invalid/?token=${token}"\n'
            "}\n"
        )

        result = execute_ast(ast, EchoingDriver())
        serialized = repr(result)

        self.assertEqual("failed", result["status"])
        self.assertNotIn("top-secret-token", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_if_and_repeat_execute_nested_blocks_with_bounds(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Control" {\n'
            '    if visible css "#ready" {\n'
            '        repeat 2 times {\n'
            '            click css ".retry"\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        driver = FakeDriver()
        ready = driver.add(By.CSS_SELECTOR, "#ready", FakeElement(displayed=True))
        retry = driver.add(By.CSS_SELECTOR, ".retry", FakeElement())

        result = execute_ast(ast, driver, options=DslRuntimeOptions())

        self.assertEqual("passed", result["status"])
        self.assertTrue(ready.is_displayed())
        self.assertTrue(retry.clicked)
        control_output = result["tests"][0]["statements"][0]["output"]
        self.assertTrue(control_output["conditionMatched"])
        repeat_output = control_output["statements"][0]["output"]
        self.assertEqual(2, repeat_output["count"])
        self.assertEqual(2, len(repeat_output["iterations"]))

    def test_if_false_skips_nested_block_without_failing_test(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Control" {\n'
            '    if visible css "#missing" {\n'
            '        click css ".never"\n'
            "    }\n"
            "}\n"
        )

        result = execute_ast(ast, FakeDriver())

        self.assertEqual("passed", result["status"])
        if_result = result["tests"][0]["statements"][0]
        self.assertEqual("passed", if_result["status"])
        self.assertFalse(if_result["output"]["conditionMatched"])
        self.assertEqual("skipped", if_result["output"]["statements"][0]["status"])

    def test_repeat_bound_is_enforced_before_dispatch(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Bounded" {\n'
            '    repeat 3 times { open "https://example.invalid" }\n'
            "}\n"
        )
        driver = FakeDriver()

        result = execute_ast(
            ast,
            driver,
            options=DslRuntimeOptions(max_loop_iterations=2),
        )

        diagnostic = result["tests"][0]["statements"][0]["diagnostics"][0]
        self.assertEqual("failed", result["status"])
        self.assertEqual("IDELIUM_DSL_RUNTIME_LOOP_BOUND_EXCEEDED", diagnostic["code"])
        self.assertEqual([], driver.calls)

    def test_nested_failure_fails_outer_control_statement_and_skips_following_nodes(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Nested failure" {\n'
            '    repeat 2 times {\n'
            '        click css ".missing"\n'
            "    }\n"
            '    open "https://example.invalid/after"\n'
            "}\n"
        )

        result = execute_ast(ast, FakeDriver())

        statements = result["tests"][0]["statements"]
        self.assertEqual("failed", result["status"])
        self.assertEqual("failed", statements[0]["status"])
        self.assertEqual("skipped", statements[1]["status"])
        first_iteration = statements[0]["output"]["iterations"][0]
        second_iteration = statements[0]["output"]["iterations"][1]
        self.assertEqual("failed", first_iteration["statements"][0]["status"])
        self.assertEqual("skipped", second_iteration["statements"][0]["status"])

    def test_reusable_step_executes_with_parameters_and_isolated_scope(self):
        ast = parse_source(
            'idelium 1.0\n\n'
            "step fillField(selector, value) {\n"
            '    write css "${selector}" value "${value}"\n'
            '    let selector = "#internal"\n'
            "}\n\n"
            'test "Reuse" {\n'
            '    let selector = "#email"\n'
            '    use fillField("${selector}", "user@example.invalid")\n'
            '    click css "${selector}"\n'
            "}\n"
        )
        driver = FakeDriver()
        email = driver.add(By.CSS_SELECTOR, "#email", FakeElement())

        result = execute_ast(ast, driver)

        self.assertEqual("passed", result["status"])
        self.assertEqual(["user@example.invalid"], email.sent_keys)
        self.assertTrue(email.clicked)
        call_output = result["tests"][0]["statements"][1]["output"]
        self.assertEqual("fillField", call_output["name"])
        self.assertEqual(["#email", "user@example.invalid"], call_output["arguments"])
        self.assertEqual("write", call_output["statements"][0]["kind"])

    def test_reusable_step_secret_arguments_are_redacted(self):
        ast = parse_source(
            'idelium 1.0\n\n'
            "step fillPassword(value) {\n"
            '    write css "#password" value "${value}"\n'
            "}\n\n"
            'test "Secret reuse" {\n'
            '    secret password = "top-secret-password"\n'
            '    use fillPassword("${password}")\n'
            "}\n"
        )
        driver = FakeDriver()
        password = driver.add(By.CSS_SELECTOR, "#password", FakeElement())

        result = execute_ast(ast, driver)
        serialized = repr(result)

        self.assertEqual("passed", result["status"])
        self.assertEqual(["top-secret-password"], password.sent_keys)
        self.assertNotIn("top-secret-password", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_reusable_step_arity_mismatch_fails_before_dispatch(self):
        ast = parse_source(
            'idelium 1.0\n\nstep openPage(url) { open "${url}" }\n\n'
            'test "Bad call" { use openPage() }\n'
        )
        driver = FakeDriver()

        result = execute_ast(ast, driver)

        diagnostic = result["tests"][0]["statements"][0]["diagnostics"][0]
        self.assertEqual("failed", result["status"])
        self.assertEqual("IDELIUM_DSL_RUNTIME_CALL_ARITY_MISMATCH", diagnostic["code"])
        self.assertEqual([], driver.calls)

    def test_reusable_step_expansion_limit_blocks_recursion(self):
        ast = parse_source(
            'idelium 1.0\n\nstep again() { use again() }\n\n'
            'test "Recursive" { use again() }\n'
        )

        result = execute_ast(
            ast,
            FakeDriver(),
            options=DslRuntimeOptions(max_macro_expansions=2),
        )

        self.assertEqual("failed", result["status"])
        outer_call = result["tests"][0]["statements"][0]
        nested_call = outer_call["output"]["statements"][0]
        deepest_call = nested_call["output"]["statements"][0]
        diagnostic = deepest_call["diagnostics"][0]
        self.assertEqual("failed", outer_call["status"])
        self.assertEqual("IDELIUM_DSL_RUNTIME_MACRO_EXPANSION_LIMIT", diagnostic["code"])

    def test_advanced_assertions_return_versioned_contract_payloads(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Assertions" {\n'
            '    assert value css "#email" equals "user@example.invalid"\n'
            '    assert count css ".row" at_least 2\n'
            '    assert url contains "/dashboard"\n'
            '    assert title equals "Dashboard"\n'
            "}\n"
        )
        driver = FakeDriver()
        driver.add(
            By.CSS_SELECTOR,
            "#email",
            FakeElement(attributes={"value": "user@example.invalid"}),
        )
        driver.add(By.CSS_SELECTOR, ".row", FakeElement())
        driver.elements[(By.CSS_SELECTOR, ".row-2")] = FakeElement()
        driver.elements[(By.CSS_SELECTOR, ".row")] = [
            FakeElement(),
            FakeElement(),
            FakeElement(),
        ]

        def find_elements(strategy, selector):
            if selector == ".row":
                return [FakeElement(), FakeElement(), FakeElement()]
            return []

        driver.find_elements = find_elements

        result = execute_ast(ast, driver)

        self.assertEqual("passed", result["status"])
        for statement in result["tests"][0]["statements"]:
            assertion = statement["output"]["assertion"]
            self.assertEqual("dsl-assertion.v1", assertion["contractVersion"])
            self.assertIn("expected", assertion)
            self.assertIn("actual", assertion)

    def test_assertion_failures_include_redacted_expected_actual_contract(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Sensitive assertion" {\n'
            '    secret expected = "top-secret-value"\n'
            '    assert value css "#password" equals "${expected}"\n'
            "}\n"
        )
        driver = FakeDriver()
        driver.add(
            By.CSS_SELECTOR,
            "#password",
            FakeElement(attributes={"value": "different-secret"}),
        )

        result = execute_ast(ast, driver)
        serialized = repr(result)
        diagnostic = result["tests"][0]["statements"][1]["diagnostics"][0]

        self.assertEqual("failed", result["status"])
        self.assertEqual("IDELIUM_DSL_RUNTIME_ASSERTION_FAILED", diagnostic["code"])
        self.assertEqual(
            "dsl-assertion.v1",
            diagnostic["data"]["assertion"]["contractVersion"],
        )
        self.assertNotIn("top-secret-value", serialized)
        self.assertNotIn("different-secret", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_runtime_results_include_versioned_step_traces(self):
        ast = parse_source(
            'idelium 1.0\n\ntest "Trace" {\n'
            '    secret token = "trace-secret"\n'
            '    open "https://example.invalid/dashboard?token=${token}"\n'
            '    click css "#missing-${token}"\n'
            '    click css "#after"\n'
            "}\n"
        )
        driver = FakeDriver()
        driver.current_url = "https://example.invalid/page?session=trace-secret"
        driver.title = "Secret trace-secret page"

        result = execute_ast(ast, driver)
        statements = result["tests"][0]["statements"]
        open_trace = statements[1]["trace"]
        failed_trace = statements[2]["trace"]
        skipped_trace = statements[3]["trace"]
        serialized = repr(result)

        self.assertEqual("performed-step-trace.v1", open_trace["schemaVersion"])
        self.assertEqual("open", open_trace["identity"]["kind"])
        self.assertEqual("failed", failed_trace["status"])
        self.assertEqual("locator", failed_trace["diagnostics"][0]["category"])
        self.assertEqual("skipped", skipped_trace["status"])
        self.assertTrue(skipped_trace["interrupted"])
        self.assertEqual(
            "interruption",
            skipped_trace["diagnostics"][0]["category"],
        )
        self.assertNotIn("trace-secret", serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
