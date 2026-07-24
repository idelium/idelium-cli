"""Contract tests for the versioned Idelium plugin API."""

import unittest

from idelium._internal.pluginapi import (
    LEGACY_PLUGIN_API_VERSION,
    PLUGIN_STEP_CAPABILITY,
    SUPPORTED_PLUGIN_API_VERSION,
    PluginContractError,
    PluginRegistry,
    normalize_plugin_payload,
    redact_plugin_error,
)


class PluginApiTest(unittest.TestCase):
    def test_explicit_manifest_declares_version_and_capability(self):
        definition = normalize_plugin_payload(
            "custom_step",
            {
                "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                "capabilities": [PLUGIN_STEP_CAPABILITY],
                "entrypoint": "run",
                "source": "def run(driver, json_config, params):\n    return 1\n",
            },
        )

        self.assertEqual("custom_step", definition.name)
        self.assertEqual(SUPPORTED_PLUGIN_API_VERSION, definition.api_version)
        self.assertEqual((PLUGIN_STEP_CAPABILITY,), definition.capabilities)
        self.assertEqual("run", definition.entrypoint)
        self.assertFalse(definition.legacy)

    def test_legacy_payload_is_normalized_for_compatibility(self):
        definition = normalize_plugin_payload(
            "legacy_step",
            '["def init(driver, json_config, params):\\n    return 1\\n"]',
        )

        self.assertEqual(LEGACY_PLUGIN_API_VERSION, definition.api_version)
        self.assertEqual((PLUGIN_STEP_CAPABILITY,), definition.capabilities)
        self.assertEqual("init", definition.entrypoint)
        self.assertTrue(definition.legacy)

    def test_invalid_contracts_are_rejected_before_dispatch(self):
        invalid_payloads = {
            "unsafe name": ("../secret", {"apiVersion": SUPPORTED_PLUGIN_API_VERSION}),
            "unsupported capability": (
                "step",
                {
                    "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                    "capabilities": ["subprocess"],
                    "source": "def init(driver, json_config, params): pass",
                },
            ),
            "unsupported version": (
                "step",
                {
                    "apiVersion": "idelium-plugin/2.0",
                    "capabilities": [PLUGIN_STEP_CAPABILITY],
                    "source": "def init(driver, json_config, params): pass",
                },
            ),
            "bad entrypoint": (
                "step",
                {
                    "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                    "capabilities": [PLUGIN_STEP_CAPABILITY],
                    "entrypoint": "__import__('os')",
                    "source": "def init(driver, json_config, params): pass",
                },
            ),
        }

        for name, (plugin_name, payload) in invalid_payloads.items():
            with self.subTest(name=name):
                with self.assertRaises(PluginContractError):
                    normalize_plugin_payload(plugin_name, payload)

    def test_registry_only_returns_capability_declared_plugins(self):
        registry = PluginRegistry.from_config(
            {
                "allowed_step": {
                    "apiVersion": SUPPORTED_PLUGIN_API_VERSION,
                    "capabilities": [PLUGIN_STEP_CAPABILITY],
                    "source": "def init(driver, json_config, params): return 1",
                }
            }
        )

        self.assertIsNotNone(registry.get_step_plugin("allowed_step"))
        self.assertIsNone(registry.get_step_plugin("missing_step"))

    def test_plugin_errors_are_redacted(self):
        error = RuntimeError("password=hunter2 token abc authorization bearer value")

        redacted = redact_plugin_error(error)

        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("abc", redacted)
        self.assertNotIn("bearer", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
