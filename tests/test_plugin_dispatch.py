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


if __name__ == "__main__":
    unittest.main()
