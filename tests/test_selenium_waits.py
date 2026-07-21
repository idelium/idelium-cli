"""Network-free representative tests for Selenium explicit waits."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SeleniumWaitTest(unittest.TestCase):
    @patch("idelium._internal.wrappers.ideliumselenium.EC")
    @patch("idelium._internal.wrappers.ideliumselenium.WebDriverWait")
    def test_wait_for_next_step_supports_clickable_condition(self, wait, expected):
        expected.element_to_be_clickable.return_value = "clickable-condition"
        wrapper = IdeliumSelenium()

        result = wrapper.wait_for_next_step(
            Mock(),
            {},
            {
                "findBy": "id",
                "target": "submit",
                "note": "wait",
                "waitCondition": "clickable",
                "waitSeconds": 7,
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        wait.assert_called_once()
        self.assertEqual(7, wait.call_args.args[1])
        wait.return_value.until.assert_called_once_with("clickable-condition")
        expected.element_to_be_clickable.assert_called_once()

    @patch("idelium._internal.wrappers.ideliumselenium.EC")
    @patch("idelium._internal.wrappers.ideliumselenium.WebDriverWait")
    def test_wait_for_next_step_supports_title_condition(self, wait, expected):
        expected.title_contains.return_value = "title-condition"
        wrapper = IdeliumSelenium()

        result = wrapper.wait_for_next_step_real(
            Mock(),
            "ignored",
            "Dashboard",
            "wait",
            3,
            "title_contains",
        )

        self.assertEqual(Result.OK, result)
        wait.return_value.until.assert_called_once_with("title-condition")
        expected.title_contains.assert_called_once_with("Dashboard")

    @patch("idelium._internal.wrappers.ideliumselenium.EC")
    def test_wait_for_next_step_supports_staleness_condition(self, expected):
        driver = Mock()
        element = Mock()
        driver.find_element.return_value = element
        expected.staleness_of.return_value = "staleness-condition"

        condition = IdeliumSelenium._expected_condition(
            driver,
            "id",
            "old-panel",
            "staleness",
        )

        self.assertEqual("staleness-condition", condition)
        driver.find_element.assert_called_once_with("id", "old-panel")
        expected.staleness_of.assert_called_once_with(element)

    def test_unsupported_wait_condition_fails_safely(self):
        wrapper = IdeliumSelenium()

        result = wrapper.wait_for_next_step_real(
            Mock(),
            "id",
            "target",
            "wait",
            1,
            "unknown",
        )

        self.assertEqual(Result.KO, result)


if __name__ == "__main__":
    unittest.main()
