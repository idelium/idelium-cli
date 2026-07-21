"""Network-free representative tests for Appium command translation."""

import unittest
from unittest.mock import Mock

from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumappium import IdeliumAppium


class AppiumTranslationTest(unittest.TestCase):
    def test_timeout_commands_are_forwarded_to_the_driver(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        page_result = wrapper.appium_set_page_load_timeout(
            driver,
            {},
            {"milliseconds": 15000},
        )
        script_result = wrapper.appium_set_script_timeout(
            driver,
            {},
            {"milliseconds": 5000},
        )

        self.assertEqual(Result.OK, page_result)
        self.assertEqual(Result.OK, script_result)
        driver.set_page_load_timeout.assert_called_once_with(15000)
        driver.set_script_timeout.assert_called_once_with(5000)

    def test_capabilities_are_normalized_for_appium_2(self):
        capabilities = IdeliumAppium._normalize_appium_capabilities(
            {
                "platformName": "Android",
                "browserName": "Chrome",
                "automationName": "UiAutomator2",
                "deviceName": "Pixel_8",
                "provider:options": {"sessionName": "smoke"},
            },
        )

        self.assertEqual("Android", capabilities["platformName"])
        self.assertEqual("Chrome", capabilities["browserName"])
        self.assertEqual("UiAutomator2", capabilities["appium:automationName"])
        self.assertEqual("Pixel_8", capabilities["appium:deviceName"])
        self.assertEqual(
            {"sessionName": "smoke"},
            capabilities["provider:options"],
        )

    def test_appium_options_select_espresso_for_android_espresso(self):
        options = IdeliumAppium._appium_options(
            {
                "appiumDesiredCaps": {
                    "platformName": "Android",
                    "automationName": "Espresso",
                    "deviceName": "Pixel_8",
                },
            },
        )

        capabilities = options.to_capabilities()
        self.assertEqual("Android", capabilities["platformName"])
        self.assertEqual("Espresso", capabilities["appium:automationName"])
        self.assertEqual("Pixel_8", capabilities["appium:deviceName"])

    def test_appium_options_select_xcuitest_for_ios(self):
        options = IdeliumAppium._appium_options(
            {
                "appiumDesiredCaps": {
                    "platformName": "iOS",
                    "automationName": "XCUITest",
                    "deviceName": "iPhone",
                },
            },
        )

        capabilities = options.to_capabilities()
        self.assertEqual("iOS", capabilities["platformName"])
        self.assertEqual("XCUITest", capabilities["appium:automationName"])
        self.assertEqual("iPhone", capabilities["appium:deviceName"])

    def test_declared_driver_metadata_accepts_selected_driver(self):
        result = IdeliumAppium._validate_appium_environment_metadata(
            {
                "appiumDesiredCaps": {
                    "platformName": "Android",
                    "automationName": "UiAutomator2",
                },
                "appiumRequiredDrivers": ["uiautomator2"],
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])

    def test_declared_driver_metadata_rejects_missing_selected_driver(self):
        result = IdeliumAppium._validate_appium_environment_metadata(
            {
                "appiumDesiredCaps": {
                    "platformName": "Android",
                    "automationName": "Espresso",
                },
                "appiumRequiredDrivers": ["uiautomator2"],
            },
        )

        self.assertEqual(Result.KO, result["returnCode"])

    def test_connect_appium_stops_before_session_when_driver_metadata_is_invalid(self):
        wrapper = IdeliumAppium()

        result = wrapper.connect_appium(
            None,
            {
                "appiumServer": "http://127.0.0.1:4723",
                "appiumDesiredCaps": {
                    "platformName": "Android",
                    "automationName": "Espresso",
                },
                "appiumRequiredDrivers": ["uiautomator2"],
                "is_debug": False,
                "ideliumServer": True,
                "json_step": {"attachScreenshot": True, "failedExit": True},
            },
            {"note": "connect"},
        )

        self.assertEqual(Result.KO, result["returnCode"])
        self.assertIsNone(result["driver"])

    def test_command_normalizes_raw_driver_values(self):
        driver = Mock()
        driver.current_package = "org.idelium.demo"
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_current_package",
            driver,
            {},
            {},
        )

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual("org.idelium.demo", result["value"])

    def test_command_reports_driver_exceptions_as_failures(self):
        driver = Mock()
        driver.back.side_effect = RuntimeError("device is not reachable")
        wrapper = IdeliumAppium()

        result = wrapper.command("appium_back", driver, {}, {})

        self.assertEqual(Result.KO, result["returnCode"])

    def test_location_uses_correct_read_timeout_key(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_get_performance_data",
            driver,
            {},
            {
                "packageName": "org.idelium.demo",
                "dataType": "cpuinfo",
                "dataReadTimeout": 5,
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        driver.get_performance_data.assert_called_once_with(
            "org.idelium.demo",
            "cpuinfo",
            5,
        )

    def test_mobile_command_executes_allow_listed_command(self):
        driver = Mock()
        driver.execute_script.return_value = {"state": "charging"}
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {},
            {"mobileCommand": "batteryInfo", "params": {"unit": "percent"}},
        )

        self.assertEqual(Result.OK, result["returnCode"])
        self.assertEqual({"state": "charging"}, result["value"])
        driver.execute_script.assert_called_once_with(
            "mobile: batteryInfo",
            {"unit": "percent"},
        )

    def test_mobile_command_can_use_environment_allow_list(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {"json_config": {"appiumMobileCommandsAllowed": ["customPluginCommand"]}},
            {"mobileCommand": "customPluginCommand", "params": {}},
        )

        self.assertEqual(Result.OK, result["returnCode"])
        driver.execute_script.assert_called_once_with(
            "mobile: customPluginCommand",
            {},
        )

    def test_mobile_command_requires_declared_plugin_when_requested(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {
                "json_config": {
                    "appiumMobileCommandsAllowed": ["customPluginCommand"],
                    "appiumRequiredPlugins": ["images"],
                },
            },
            {
                "mobileCommand": "customPluginCommand",
                "requiredPlugin": "images",
                "params": {},
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        driver.execute_script.assert_called_once_with(
            "mobile: customPluginCommand",
            {},
        )

    def test_mobile_command_rejects_missing_required_plugin_metadata(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {"json_config": {"appiumMobileCommandsAllowed": ["customPluginCommand"]}},
            {
                "mobileCommand": "customPluginCommand",
                "requiredPlugin": "images",
                "params": {},
            },
        )

        self.assertEqual(Result.KO, result["returnCode"])
        driver.execute_script.assert_not_called()

    def test_mobile_command_rejects_unlisted_command(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {},
            {"mobileCommand": "deleteFile", "params": {}},
        )

        self.assertEqual(Result.KO, result["returnCode"])
        driver.execute_script.assert_not_called()

    def test_mobile_command_rejects_sensitive_parameters(self):
        driver = Mock()
        wrapper = IdeliumAppium()

        result = wrapper.command(
            "appium_mobile_command",
            driver,
            {},
            {
                "mobileCommand": "batteryInfo",
                "params": {"nested": {"authorization": "Bearer secret"}},
            },
        )

        self.assertEqual(Result.KO, result["returnCode"])
        driver.execute_script.assert_not_called()


if __name__ == "__main__":
    unittest.main()
