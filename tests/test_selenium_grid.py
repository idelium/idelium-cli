"""Unit tests for Selenium Grid session creation."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.resultenum import Result
from idelium._internal.ideliumclib import InitIdelium
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SeleniumGridTest(unittest.TestCase):
    def config(self):
        return {
            "seleniumGridUrl": "https://grid.example.test:4444",
            "seleniumGridCapabilities": {
                "platformName": "linux",
                "se:name": "Idelium test",
                "webSocketUrl": True,
            },
            "json_config": {
                "browser": "chrome",
                "url": "https://application.example.test",
                "xpath_check_url": "",
                "accept_self_certificate": False,
            },
            "browser": "chrome",
            "device": None,
            "useragent": "Idelium Grid Test",
            "width": 1280,
            "height": 720,
            "is_debug": False,
            "ideliumServer": True,
            "json_step": {
                "attachScreenshot": False,
                "failedExit": False,
            },
        }

    @patch("idelium._internal.wrappers.ideliumselenium.webdriver.Remote")
    def test_open_browser_creates_remote_grid_session(self, remote):
        driver = Mock()
        remote.return_value = driver
        wrapper = IdeliumSelenium()
        wrapper.wait_for_next_step = Mock(return_value={"returnCode": Result.OK})
        config = self.config()

        result = wrapper.open_browser(None, config, {})

        self.assertEqual(Result.OK, result["returnCode"])
        remote.assert_called_once()
        call = remote.call_args
        self.assertEqual(config["seleniumGridUrl"], call.kwargs["command_executor"])
        capabilities = call.kwargs["options"].capabilities
        self.assertEqual("chrome", capabilities["browserName"])
        self.assertEqual("linux", capabilities["platformName"])
        self.assertEqual("Idelium test", capabilities["se:name"])
        self.assertTrue(capabilities["webSocketUrl"])
        driver.set_window_size.assert_called_once_with(1280, 720)
        driver.get.assert_called_once_with("https://application.example.test")

    @patch("idelium._internal.wrappers.ideliumselenium.webdriver.Remote")
    def test_invalid_grid_url_is_rejected_before_session_creation(self, remote):
        config = self.config()
        config["seleniumGridUrl"] = "file:///tmp/grid"

        with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
            IdeliumSelenium.create_remote_driver(config)

        remote.assert_not_called()

    @patch("idelium._internal.wrappers.ideliumselenium.ChromeDriverManager")
    @patch("idelium._internal.wrappers.ideliumselenium.webdriver.Chrome")
    def test_local_chrome_uses_selenium_4_options(self, chrome, manager):
        driver = Mock()
        chrome.return_value = driver
        manager.return_value.install.return_value = "/drivers/chromedriver"
        wrapper = IdeliumSelenium()
        wrapper.wait_for_next_step = Mock(return_value={"returnCode": Result.OK})
        config = self.config()
        config["seleniumGridUrl"] = None
        config["device"] = "Nexus 5"
        config["json_config"]["accept_self_certificate"] = True

        result = wrapper.open_browser(None, config, {})

        self.assertEqual(Result.OK, result["returnCode"])
        chrome.assert_called_once()
        options = chrome.call_args.kwargs["options"]
        capabilities = options.to_capabilities()
        self.assertTrue(capabilities["acceptInsecureCerts"])
        self.assertTrue(capabilities["webSocketUrl"])
        self.assertIn("goog:chromeOptions", capabilities)

    def test_command_line_grid_settings_override_environment_settings(self):
        loader = InitIdelium()
        printer = Mock()
        web_service = Mock()
        web_service.get_configuration.return_value = {
            "environments": {
                "ci": {
                    "browser": "chrome",
                    "seleniumGridUrl": "https://environment-grid.test:4444",
                    "seleniumGridCapabilities": {"platformName": "windows"},
                },
            },
            "configStep": {},
        }
        defined = loader.define_parameters(
            [
                "idelium",
                "--idProject=1",
                "--idCycle=2",
                "--environment=ci",
                "--ideliumKey=key==",
                "--ideliumwsBaseurl=https://api.example.test",
                "--seleniumGridUrl=https://cli-grid.test:4444",
                '--seleniumGridCapabilities={"platformName":"linux"}',
            ],
            web_service,
            printer,
        )

        loaded = loader.load_parameters(defined["cl_params"], web_service, printer)

        self.assertEqual("key==", loaded["cl_params"]["ideliumKey"])
        self.assertEqual(
            "https://cli-grid.test:4444",
            loaded["cl_params"]["seleniumGridUrl"],
        )
        self.assertEqual(
            {"platformName": "linux"},
            loaded["cl_params"]["seleniumGridCapabilities"],
        )


if __name__ == "__main__":
    unittest.main()
