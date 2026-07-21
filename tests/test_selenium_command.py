"""Network-free tests for generic Selenium command dispatch."""

import unittest
from unittest.mock import Mock

from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SeleniumCommandTest(unittest.TestCase):
    def test_navigate_operation_uses_driver_get(self):
        driver = Mock()
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "navigate_to", "url": "https://example.test"},
        )

        self.assertEqual(Result.OK, result["returnCode"])
        driver.get.assert_called_once_with("https://example.test")

    def test_execute_script_returns_value(self):
        driver = Mock()
        driver.execute_script.return_value = {"ready": True}
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {
                "operation": "execute_script",
                "script": "return arguments[0]",
                "args": [{"ready": True}],
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual({"ready": True}, result["value"])
        driver.execute_script.assert_called_once_with(
            "return arguments[0]",
            {"ready": True},
        )

    def test_cookie_operations_are_allow_listed(self):
        driver = Mock()
        driver.get_cookie.return_value = {"name": "theme", "value": "dark"}
        wrapper = IdeliumSelenium()

        add_result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "add_cookie", "cookie": {"name": "theme", "value": "dark"}},
        )
        get_result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "get_cookie", "name": "theme"},
        )

        self.assertEqual(Result.OK, add_result["returnCode"])
        self.assertEqual(Result.OK, get_result["returnCode"])
        self.assertEqual({"name": "theme", "value": "dark"}, get_result["value"])
        driver.add_cookie.assert_called_once_with({"name": "theme", "value": "dark"})

    def test_alert_and_window_operations_are_allow_listed(self):
        driver = Mock()
        wrapper = IdeliumSelenium()

        alert_result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "accept_alert"},
        )
        window_result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "new_window", "windowType": "tab"},
        )

        self.assertEqual(Result.OK, alert_result["returnCode"])
        self.assertEqual(Result.OK, window_result["returnCode"])
        driver.switch_to.alert.accept.assert_called_once_with()
        driver.switch_to.new_window.assert_called_once_with("tab")

    def test_element_state_returns_driver_state(self):
        driver = Mock()
        element = Mock()
        element.is_enabled.return_value = True
        driver.find_element.return_value = element
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {
                "operation": "element_state",
                "findBy": "id",
                "target": "save",
                "state": "enabled",
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertTrue(result["value"])
        element.is_enabled.assert_called_once_with()

    def test_file_upload_sends_path_to_element(self):
        driver = Mock()
        element = Mock()
        driver.find_element.return_value = element
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {
                "operation": "file_upload",
                "findBy": "id",
                "target": "upload",
                "path": "/tmp/example.txt",
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        element.send_keys.assert_called_once_with("/tmp/example.txt")

    def test_unsupported_operation_fails_safely(self):
        driver = Mock()
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_command",
            driver,
            {},
            {"operation": "execute_unrestricted_code"},
        )

        self.assertEqual(Result.KO, result["returnCode"])
        driver.execute_script.assert_not_called()


if __name__ == "__main__":
    unittest.main()
