"""Tests for selector resilience diagnostics."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.selector_diagnostics import (
    analyze_selector,
    collect_step_selector_diagnostics,
)
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SelectorDiagnosticsTest(unittest.TestCase):
    def test_css_rules_detect_positional_and_dynamic_patterns(self):
        diagnostics = analyze_selector("css", "div:nth-child(2) #user-12345")
        rule_ids = {diagnostic.rule_id for diagnostic in diagnostics}

        self.assertIn("IDELIUM_SELECTOR_CSS_POSITIONAL", rule_ids)
        self.assertIn("IDELIUM_SELECTOR_CSS_DYNAMIC_ID", rule_ids)

    def test_xpath_rules_detect_absolute_positional_and_dynamic_patterns(self):
        diagnostics = analyze_selector(
            "xpath",
            "/html/body/div[3]//button[@id='submit-98765']",
        )
        rule_ids = {diagnostic.rule_id for diagnostic in diagnostics}

        self.assertIn("IDELIUM_SELECTOR_XPATH_ABSOLUTE", rule_ids)
        self.assertIn("IDELIUM_SELECTOR_XPATH_POSITIONAL", rule_ids)
        self.assertIn("IDELIUM_SELECTOR_XPATH_DYNAMIC_ATTRIBUTE", rule_ids)

    def test_stable_selectors_do_not_emit_diagnostics(self):
        self.assertEqual([], analyze_selector("css", "[data-testid='submit']"))
        self.assertEqual([], analyze_selector("xpath", "//*[@data-testid='submit']"))

    def test_legacy_xpath_field_is_reported_without_rewriting_selector(self):
        step = {"xpath": "//button[@id='save-1234']"}

        diagnostics = collect_step_selector_diagnostics(step)

        self.assertEqual("//button[@id='save-1234']", step["xpath"])
        self.assertIn(
            "IDELIUM_SELECTOR_LEGACY_XPATH_FIELD",
            {diagnostic.rule_id for diagnostic in diagnostics},
        )

    @patch("idelium._internal.wrappers.ideliumselenium.printer")
    def test_runtime_emits_warnings_without_changing_execution(self, patched_printer):
        driver = Mock()
        wrapper = IdeliumSelenium()
        step = {
            "findBy": "css",
            "target": "div:nth-child(2)",
        }

        wrapper.command("find_element", driver, {}, step)

        driver.find_element.assert_called_once_with("css selector", "div:nth-child(2)")
        warning_messages = [call.args[0] for call in patched_printer.warning.call_args_list]
        self.assertTrue(
            any("IDELIUM_SELECTOR_CSS_POSITIONAL" in message for message in warning_messages)
        )

    @patch("idelium._internal.wrappers.ideliumselenium.printer")
    def test_runtime_diagnostics_can_be_disabled(self, patched_printer):
        driver = Mock()
        wrapper = IdeliumSelenium()

        wrapper.command(
            "find_element",
            driver,
            {"selectorDiagnostics": False},
            {"findBy": "css", "target": "div:nth-child(2)"},
        )

        patched_printer.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
