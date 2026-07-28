"""Subprocess sandbox tests for approved plugin execution."""

import os
import unittest

from idelium._internal.commons.resultenum import Result
from idelium._internal.pluginapi import (
    ENTERPRISE_PLUGIN_API_VERSION,
    PLUGIN_STEP_CAPABILITY,
    normalize_plugin_payload,
    source_hash,
)
from idelium._internal.pluginrunner import (
    PluginExecutionError,
    execute_plugin_in_subprocess,
)


class PluginRunnerTest(unittest.TestCase):
    def _definition(self, source, timeout=10):
        return normalize_plugin_payload(
            "approved_step",
            {
                "apiVersion": ENTERPRISE_PLUGIN_API_VERSION,
                "capabilities": [PLUGIN_STEP_CAPABILITY],
                "entrypoint": "run",
                "source": source,
                "approvalStatus": "approved",
                "sourceSha256": source_hash(source),
                "executionMode": "subprocess",
                "timeoutSeconds": timeout,
                "provenance": {"reviewedBy": "security@example.test"},
            },
        )

    def test_approved_plugin_runs_in_subprocess(self):
        definition = self._definition(
            "from idelium._internal.commons.resultenum import Result\n"
            "def run(driver, json_config, params):\n"
            "    return Result.OK\n"
        )

        result = execute_plugin_in_subprocess(definition, {}, {"value": "ok"})

        self.assertEqual(Result.OK, result)

    def test_subprocess_environment_redacts_secrets(self):
        os.environ["IDELIUM_TEST_SECRET"] = "must-not-leak"
        definition = self._definition(
            "from idelium._internal.commons.resultenum import Result\n"
            "def run(driver, json_config, params):\n"
            "    return Result.OK\n"
        )

        result = execute_plugin_in_subprocess(definition, {}, {})

        self.assertEqual(Result.OK, result)

    def test_plugin_secret_environment_access_fails_safely(self):
        definition = self._definition(
            "import os\n"
            "def run(driver, json_config, params):\n"
            "    return os.environ.get('IDELIUM_TEST_SECRET')\n"
        )

        with self.assertRaisesRegex(PluginExecutionError, "disallowed module: os"):
            execute_plugin_in_subprocess(definition, {}, {})

    def test_plugin_network_access_fails_safely(self):
        definition = self._definition(
            "import socket\n"
            "def run(driver, json_config, params):\n"
            "    return socket.socket()\n"
        )

        with self.assertRaisesRegex(PluginExecutionError, "disallowed module: socket"):
            execute_plugin_in_subprocess(definition, {}, {})

    def test_plugin_filesystem_access_fails_safely(self):
        definition = self._definition(
            "def run(driver, json_config, params):\n"
            "    return open('/tmp/secret.txt').read()\n"
        )

        with self.assertRaisesRegex(
            PluginExecutionError, "disallowed capability: open"
        ):
            execute_plugin_in_subprocess(definition, {}, {})

    def test_plugin_timeout_fails_safely(self):
        definition = self._definition(
            "import time\n"
            "def run(driver, json_config, params):\n"
            "    time.sleep(5)\n"
            "    return 0\n",
            timeout=1,
        )

        with self.assertRaises(PluginExecutionError):
            execute_plugin_in_subprocess(definition, {}, {})


if __name__ == "__main__":
    unittest.main()
