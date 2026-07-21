"""Network-free tests for Selenium W3C Actions support."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.resultenum import Result
from idelium._internal.wrappers.ideliumselenium import IdeliumSelenium


class SeleniumActionsTest(unittest.TestCase):
    @patch("idelium._internal.wrappers.ideliumselenium.ActionChains")
    def test_keyboard_actions_are_dispatched(self, action_chains):
        chain = action_chains.return_value
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_actions",
            Mock(),
            {},
            {
                "actions": [
                    {"type": "key_down", "key": "SHIFT"},
                    {"type": "send_keys", "text": "a"},
                    {"type": "key_up", "key": "SHIFT"},
                ],
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        chain.key_down.assert_called_once_with("SHIFT")
        chain.send_keys.assert_called_once_with("a")
        chain.key_up.assert_called_once_with("SHIFT")
        chain.perform.assert_called_once_with()

    @patch("idelium._internal.wrappers.ideliumselenium.ActionChains")
    def test_pointer_and_wheel_actions_are_dispatched(self, action_chains):
        chain = action_chains.return_value
        element = Mock()
        driver = Mock()
        driver.find_element.return_value = element
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_actions",
            driver,
            {},
            {
                "actions": [
                    {"type": "move_to", "findBy": "id", "target": "menu"},
                    {"type": "double_click", "findBy": "id", "target": "menu"},
                    {"type": "context_click", "findBy": "id", "target": "menu"},
                    {"type": "scroll_by", "deltaX": 0, "deltaY": 300},
                ],
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        chain.move_to_element.assert_called_once_with(element)
        chain.double_click.assert_called_once_with(element)
        chain.context_click.assert_called_once_with(element)
        chain.scroll_by_amount.assert_called_once_with(0, 300)
        chain.perform.assert_called_once_with()

    @patch("idelium._internal.wrappers.ideliumselenium.ActionChains")
    def test_drag_and_drop_action_is_dispatched(self, action_chains):
        chain = action_chains.return_value
        source = Mock()
        target = Mock()
        driver = Mock()
        driver.find_element.side_effect = [source, target]
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_actions",
            driver,
            {},
            {
                "actions": [
                    {
                        "type": "drag_and_drop",
                        "sourceFindBy": "id",
                        "sourceTarget": "source",
                        "targetFindBy": "id",
                        "targetTarget": "target",
                    },
                ],
            },
        )

        self.assertEqual(Result.OK, result["returnCode"])
        chain.drag_and_drop.assert_called_once_with(source, target)
        chain.perform.assert_called_once_with()

    @patch("idelium._internal.wrappers.ideliumselenium.ActionChains")
    def test_unsupported_action_fails_safely(self, action_chains):
        chain = action_chains.return_value
        wrapper = IdeliumSelenium()

        result = wrapper.command(
            "selenium_actions",
            Mock(),
            {},
            {"actions": [{"type": "execute_unrestricted_code"}]},
        )

        self.assertEqual(Result.KO, result["returnCode"])
        chain.perform.assert_not_called()


if __name__ == "__main__":
    unittest.main()
