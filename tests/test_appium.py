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


if __name__ == "__main__":
    unittest.main()
