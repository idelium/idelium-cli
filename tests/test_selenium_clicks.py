"""Network-free tests for stable Selenium click execution."""

import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import ElementClickInterceptedException

from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SeleniumClicksTest(unittest.TestCase):
    def test_clear_dispatches_input_and_change_events_for_reactive_apps(self):
        driver = Mock()
        element = Mock()
        driver.find_element.return_value = element
        wrapper = IdeliumSelenium()

        result = wrapper.clear(
            driver,
            {},
            {
                "note": "Clear the table search before validating every row",
                "findBy": "css",
                "target": "[data-testid='table-search']",
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        element.clear.assert_called_once_with()
        driver.execute_script.assert_called_once_with(
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
            element,
        )

    def test_click_scrolls_element_into_center_before_clicking(self):
        driver = Mock()
        element = Mock()
        driver.find_element.return_value = element
        wrapper = IdeliumSelenium()

        result = wrapper.click(
            driver,
            {},
            {
                "note": "Submit the demo form",
                "findBy": "css",
                "target": "[data-testid='submit-button']",
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        driver.execute_script.assert_called_once_with(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            element,
        )
        element.click.assert_called_once_with()

    @patch("idelium._internal.wrappers.ideliumselenium.ActionChains")
    def test_click_uses_actions_fallback_when_click_is_intercepted(self, action_chains):
        driver = Mock()
        element = Mock()
        element.click.side_effect = ElementClickInterceptedException(
            "element click intercepted"
        )
        driver.find_element.return_value = element
        chain = action_chains.return_value
        chain.move_to_element.return_value = chain
        chain.click.return_value = chain
        wrapper = IdeliumSelenium()

        result = wrapper.click(
            driver,
            {},
            {
                "note": "Submit the demo form",
                "findBy": "css",
                "target": "[data-testid='submit-button']",
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual(2, driver.execute_script.call_count)
        chain.move_to_element.assert_called_once_with(element)
        chain.click.assert_called_once_with(element)
        chain.perform.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
