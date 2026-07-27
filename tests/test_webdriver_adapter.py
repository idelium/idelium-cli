"""Network-free tests for the W3C WebDriver adapter contract."""

import unittest
from unittest.mock import Mock, call, patch

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from idelium._internal.commons.resultenum import Result
from idelium._internal.webdriver_adapter import (
    W3CWebDriverAdapter,
    WebDriverContractError,
    build_locator,
    classify_webdriver_error,
    resolve_step_locator,
)
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class WebDriverAdapterTest(unittest.TestCase):
    def test_build_locator_normalizes_supported_strategies(self):
        locator = build_locator("css", "[data-testid='save']")

        self.assertEqual((By.CSS_SELECTOR, "[data-testid='save']"), locator.as_selenium())

    def test_build_locator_rejects_unsupported_strategy(self):
        with self.assertRaises(WebDriverContractError):
            build_locator("javascript", "return document.body")

    def test_build_locator_rejects_empty_target(self):
        with self.assertRaises(WebDriverContractError):
            build_locator("xpath", "")

    def test_resolve_step_locator_preserves_legacy_xpath_payloads(self):
        locator = resolve_step_locator({"xpath": "//button[@type='submit']"})

        self.assertEqual((By.XPATH, "//button[@type='submit']"), locator.as_selenium())

    def test_adapter_find_element_uses_explicit_locator_contract(self):
        driver = Mock()
        adapter = W3CWebDriverAdapter(driver)

        adapter.find_element(build_locator("id", "submit"))

        driver.find_element.assert_called_once_with(By.ID, "submit")

    def test_error_classification_marks_timeouts_as_transient(self):
        diagnostic = classify_webdriver_error(TimeoutException("timed out"))

        self.assertEqual("IDELIUM_WEBDRIVER_TIMEOUT", diagnostic.code)
        self.assertTrue(diagnostic.transient)

    def test_error_classification_redacts_locator_not_found(self):
        diagnostic = classify_webdriver_error(
            NoSuchElementException("session abc123 missing password=secret")
        )

        self.assertEqual("IDELIUM_WEBDRIVER_LOCATOR_NOT_FOUND", diagnostic.code)
        self.assertNotIn("secret", diagnostic.message)

    def test_session_health_returns_classified_failure(self):
        driver = Mock()
        type(driver).current_window_handle = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("dead"))
        )

        result = W3CWebDriverAdapter(driver).is_session_healthy()

        self.assertEqual(Result.KO, result.return_code)
        self.assertEqual(
            "IDELIUM_WEBDRIVER_SESSION_UNHEALTHY",
            result.error.code,
        )

    def test_runtime_rejects_missing_locator_without_driver_call(self):
        driver = Mock()

        result = IdeliumSelenium.find_element(driver, {}, {"findBy": "css"})

        self.assertEqual(Result.KO, result["returnCode"])
        self.assertEqual(
            "IDELIUM_WEBDRIVER_CONTRACT_ERROR",
            result["error"]["code"],
        )
        driver.find_element.assert_not_called()

    def test_drag_and_drop_accepts_explicit_css_locators(self):
        driver = Mock()
        source = Mock()
        target = Mock()
        driver.find_element.side_effect = [source, target]
        step = {
            "dragFindBy": "css",
            "dragTarget": "[data-testid='source']",
            "dropFindBy": "css",
            "dropTarget": "[data-testid='target']",
        }

        with patch(
            "idelium._internal.wrappers.ideliumselenium.ActionChains"
        ) as action_chains:
            result = IdeliumSelenium.drag_and_drop(driver, {}, step)

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual(
            [
                call(By.CSS_SELECTOR, "[data-testid='source']"),
                call(By.CSS_SELECTOR, "[data-testid='target']"),
            ],
            driver.find_element.call_args_list,
        )
        action_chains.return_value.drag_and_drop.assert_called_once_with(source, target)
        action_chains.return_value.drag_and_drop.return_value.perform.assert_called_once_with()

    def test_drag_and_drop_preserves_legacy_xpath_payloads(self):
        driver = Mock()
        driver.find_element.side_effect = [Mock(), Mock()]
        step = {"xpathDrag": "//li[@id='source']", "xpathDrop": "//li[@id='target']"}

        with patch("idelium._internal.wrappers.ideliumselenium.ActionChains"):
            result = IdeliumSelenium.drag_and_drop(driver, {}, step)

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual(
            [
                call(By.XPATH, "//li[@id='source']"),
                call(By.XPATH, "//li[@id='target']"),
            ],
            driver.find_element.call_args_list,
        )

    def test_adapter_quit_classifies_cleanup_failures(self):
        driver = Mock()
        driver.quit.side_effect = RuntimeError("driver secret exploded")

        result = W3CWebDriverAdapter(driver).quit()

        self.assertEqual(Result.KO, result.return_code)
        self.assertEqual(
            "IDELIUM_WEBDRIVER_SESSION_CLEANUP_FAILED",
            result.error.code,
        )
        self.assertNotIn("secret", result.error.message)


if __name__ == "__main__":
    unittest.main()
