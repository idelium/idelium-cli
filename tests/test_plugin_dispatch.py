"""Runtime boundary tests for plugin dispatch."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.resultenum import Result
from idelium._internal.ideliummanager import StartManager
from idelium._internal.pluginapi import (
    ENTERPRISE_PLUGIN_API_VERSION,
    PLUGIN_STEP_CAPABILITY,
    source_hash,
)


class FakeDslElement:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True

    def send_keys(self, value):
        self.value = value

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def get_attribute(self, name):
        return getattr(self, name, "")


class FakeDslDriver:
    def __init__(self):
        self.elements = {}
        self.calls = []
        self.current_url = "https://example.invalid/demo"
        self.title = "Demo"

    def add(self, strategy, selector, element):
        self.elements[(strategy, selector)] = element
        return element

    def get(self, url):
        self.calls.append(("get", url))

    def find_element(self, strategy, selector):
        self.calls.append(("find_element", strategy, selector))
        return self.elements[(strategy, selector)]

    def find_elements(self, strategy, selector):
        self.calls.append(("find_elements", strategy, selector))
        return [
            element
            for (element_strategy, element_selector), element in self.elements.items()
            if element_strategy == strategy and element_selector == selector
        ]


class PluginDispatchTest(unittest.TestCase):
    def _config(self, step, plugins=None):
        wrapper = Mock()
        wrapper.command.return_value = None
        return {
            "wrapper": wrapper,
            "printer": Mock(),
            "json_step": {"steps": [step]},
            "json_config": {},
            "plugins": plugins or {},
            "is_debug": False,
            "ideliumServer": True,
        }

    @patch("idelium._internal.ideliummanager.execute_plugin_in_subprocess")
    def test_unregistered_plugin_step_fails_without_import(self, execute_plugin):
        step = {"stepType": "missing_plugin", "params": {}}

        result = StartManager.execute_step(None, self._config(step))

        self.assertEqual("2", result["status"])
        self.assertEqual(step, result["step_failed"])
        execute_plugin.assert_not_called()

    @patch("idelium._internal.ideliummanager.execute_plugin_in_subprocess")
    def test_registered_plugin_uses_declared_entrypoint(self, execute_plugin):
        execute_plugin.return_value = Result.OK
        step = {"stepType": "custom_step", "params": {"value": "ok"}}
        source = "def run(driver, json_config, params): return 1"
        plugins = {
            "custom_step": {
                "apiVersion": ENTERPRISE_PLUGIN_API_VERSION,
                "capabilities": [PLUGIN_STEP_CAPABILITY],
                "entrypoint": "run",
                "source": source,
                "approvalStatus": "approved",
                "sourceSha256": source_hash(source),
                "executionMode": "subprocess",
                "provenance": {"reviewedBy": "security@example.test"},
            }
        }

        result = StartManager.execute_step("driver", self._config(step, plugins))

        self.assertEqual("1", result["status"])
        execute_plugin.assert_called_once()
        definition, json_config, params = execute_plugin.call_args.args
        self.assertEqual("custom_step", definition.name)
        self.assertEqual({}, json_config)
        self.assertEqual({"value": "ok"}, params)

    @patch("idelium._internal.ideliummanager.execute_plugin_in_subprocess")
    def test_plugin_exception_is_isolated_and_redacted(self, execute_plugin):
        execute_plugin.side_effect = RuntimeError("token abc password=hunter2")
        step = {"stepType": "custom_step", "params": {}}
        source = "def init(driver, json_config, params): return 1"
        config = self._config(
            step,
            {
                "custom_step": {
                    "apiVersion": ENTERPRISE_PLUGIN_API_VERSION,
                    "capabilities": [PLUGIN_STEP_CAPABILITY],
                    "source": source,
                    "approvalStatus": "approved",
                    "sourceSha256": source_hash(source),
                    "executionMode": "subprocess",
                    "provenance": {"reviewedBy": "security@example.test"},
                }
            },
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("2", result["status"])
        printed = " ".join(
            str(call.args[0]) for call in config["printer"].danger.call_args_list
        )
        self.assertNotIn("hunter2", printed)


class DslStepDispatchTest(unittest.TestCase):
    def _config(self, step):
        wrapper = Mock()
        wrapper.command.side_effect = (
            lambda command, driver, config, object_step: {
                "driver": driver,
                "returnCode": Result.OK,
                "config": config,
            }
            if command == "open_browser"
            else None
        )
        return {
            "wrapper": wrapper,
            "printer": Mock(),
            "json_step": {"steps": [step]},
            "json_config": {},
            "plugins": {},
            "is_debug": False,
            "ideliumServer": True,
            "dir_step_files": None,
            "dslParameters": {"variables": {}, "secretNames": []},
        }

    def test_dsl_step_executes_without_plugin_fallback(self):
        source = """idelium 1.0

test "Imported DSL" {
    open "https://example.invalid/demo"
    wait css "#ready" visible timeout 250ms
    assert visible css "#ready"
}
"""
        step = {
            "stepType": "dsl",
            "runtime": "dsl",
            "schemaVersion": "dsl.source.v1",
            "languageVersion": "1.0",
            "source": source,
        }
        driver = FakeDslDriver()
        driver.add("css selector", "#ready", FakeDslElement())
        config = self._config(step)

        result = StartManager.execute_step(driver, config)

        self.assertEqual("1", result["status"])
        self.assertEqual("dsl", result["type"])
        self.assertEqual("passed", result["dsl_result"]["status"])
        self.assertIn(("get", "https://example.invalid/demo"), driver.calls)
        printed = " ".join(
            str(call.args[0]) for call in config["printer"].success.call_args_list
        )
        self.assertIn("wait css #ready -> PASSED", printed)
        config["wrapper"].command.assert_not_called()

    def test_dsl_step_bootstraps_browser_when_driver_is_missing(self):
        source = """idelium 1.0

test "Imported DSL" {
    open "https://example.invalid/demo"
    assert visible css "#ready"
}
"""
        step = {
            "stepType": "dsl",
            "runtime": "dsl",
            "schemaVersion": "dsl.source.v1",
            "languageVersion": "1.0",
            "source": source,
        }
        driver = FakeDslDriver()
        driver.add("css selector", "#ready", FakeDslElement())
        config = self._config(step)
        config["wrapper"].command.side_effect = (
            lambda command, current_driver, command_config, object_step: {
                "driver": driver,
                "returnCode": Result.OK,
                "config": command_config,
            }
            if command == "open_browser"
            else None
        )

        result = StartManager.execute_step(None, config)

        self.assertEqual("1", result["status"])
        self.assertEqual(driver, result["driver"])
        self.assertEqual("passed", result["dsl_result"]["status"])
        config["wrapper"].command.assert_called_once()

    def test_invalid_dsl_source_fails_without_plugin_fallback(self):
        step = {
            "stepType": "dsl",
            "runtime": "dsl",
            "schemaVersion": "dsl.source.v1",
            "languageVersion": "1.0",
            "source": "idelium 1.0\n\ntest \"Broken\" {\n    CLICK css \"#ready\"\n}\n",
        }
        config = self._config(step)

        result = StartManager.execute_step(FakeDslDriver(), config)

        self.assertEqual("2", result["status"])
        self.assertEqual("dsl", result["type"])
        self.assertEqual(step, result["step_failed"])
        self.assertIsNone(result["dsl_result"])
        config["wrapper"].command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
