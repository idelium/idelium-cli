"""Runtime boundary tests for plugin dispatch."""

import unittest
from unittest.mock import Mock, patch

from idelium._internal.commons.resultenum import Result
from idelium._internal.ideliummanager import StartManager
from idelium._internal.pluginapi import (
    PLUGIN_STEP_CAPABILITY,
    SUPPORTED_PLUGIN_API_VERSION,
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

    @patch("idelium._internal.ideliummanager.importlib.import_module")
    def test_unregistered_plugin_step_fails_without_import(self, import_module):
        step = {"stepType": "missing_plugin", "params": {}}

        result = StartManager.execute_step(None, self._config(step))

        self.assertEqual("2", result["status"])
        self.assertEqual(step, result["step_failed"])
        import_module.assert_not_called()

    @patch("idelium._internal.ideliummanager.importlib.import_module")
    def test_registered_plugin_uses_declared_entrypoint(self, import_module):
        module = Mock()
        module.run.return_value = Result.OK
        import_module.return_value = module
        step = {"stepType": "custom_step", "params": {"value": "ok"}}
        plugins = {
            "custom_step": {
                "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                "capabilities": [PLUGIN_STEP_CAPABILITY],
                "entrypoint": "run",
                "source": "def run(driver, json_config, params): return 1",
            }
        }

        result = StartManager.execute_step("driver", self._config(step, plugins))

        self.assertEqual("1", result["status"])
        import_module.assert_called_once_with(
            "plugin.custom_step", package="idelium._internal"
        )
        module.run.assert_called_once_with("driver", {}, {"value": "ok"})

    @patch("idelium._internal.ideliummanager.importlib.import_module")
    def test_plugin_exception_is_isolated_and_redacted(self, import_module):
        module = Mock()
        module.init.side_effect = RuntimeError("token abc password=hunter2")
        import_module.return_value = module
        step = {"stepType": "custom_step", "params": {}}
        config = self._config(
            step,
            {
                "custom_step": {
                    "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                    "capabilities": [PLUGIN_STEP_CAPABILITY],
                    "source": "def init(driver, json_config, params): return 1",
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
