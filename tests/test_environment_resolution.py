"""Regression tests for multi-environment configuration resolution."""

from __future__ import annotations

import unittest

from idelium._internal.environment_resolution import (
    ENVIRONMENT_CONTRACT_VERSION,
    EnvironmentResolutionError,
    resolve_environment,
)


class EnvironmentResolutionTest(unittest.TestCase):
    def test_inheritance_and_cli_overrides_use_documented_precedence(self):
        result = resolve_environment(
            {
                "base": {
                    "projectId": "3",
                    "browser": "chrome",
                    "url": "https://base.example.invalid",
                    "seleniumGridCapabilities": {"browserVersion": "stable"},
                },
                "staging": {
                    "extends": "base",
                    "projectId": "3",
                    "url": "https://staging.example.invalid",
                    "bidiMode": "auto",
                },
            },
            "staging",
            project_id="3",
            overrides={"url": "https://cli.example.invalid"},
        )

        self.assertEqual("https://cli.example.invalid", result.config["url"])
        self.assertEqual("chrome", result.config["browser"])
        self.assertEqual("auto", result.config["bidiMode"])
        self.assertEqual(("base", "staging", "cli-overrides"), result.provenance)
        self.assertEqual(
            ENVIRONMENT_CONTRACT_VERSION,
            result.as_dict()["schemaVersion"],
        )

    def test_missing_or_cross_project_environments_fail_before_execution(self):
        with self.assertRaises(EnvironmentResolutionError) as missing:
            resolve_environment({}, "production", project_id="3")

        with self.assertRaises(EnvironmentResolutionError) as mismatch:
            resolve_environment(
                {"production": {"projectId": "4", "url": "https://example.invalid"}},
                "production",
                project_id="3",
            )

        self.assertEqual("IDELIUM_ENVIRONMENT_NOT_FOUND", missing.exception.code)
        self.assertEqual(
            "IDELIUM_ENVIRONMENT_PROJECT_MISMATCH",
            mismatch.exception.code,
        )

    def test_invalid_inheritance_is_rejected(self):
        with self.assertRaises(EnvironmentResolutionError) as missing_parent:
            resolve_environment(
                {"staging": {"extends": "base"}},
                "staging",
                project_id="3",
            )

        with self.assertRaises(EnvironmentResolutionError) as cycle:
            resolve_environment(
                {
                    "a": {"extends": "b"},
                    "b": {"extends": "a"},
                },
                "a",
                project_id="3",
            )

        self.assertEqual(
            "IDELIUM_ENVIRONMENT_PARENT_NOT_FOUND",
            missing_parent.exception.code,
        )
        self.assertEqual("IDELIUM_ENVIRONMENT_INHERITANCE_CYCLE", cycle.exception.code)

    def test_secret_keys_are_diagnosed_without_exposing_values(self):
        result = resolve_environment(
            {
                "production": {
                    "projectId": "3",
                    "url": "https://example.invalid",
                    "apiToken": "super-secret-token",
                }
            },
            "production",
            project_id="3",
        )

        metadata = result.as_dict()

        self.assertEqual(
            "IDELIUM_ENVIRONMENT_SECRET_REFERENCE", metadata["diagnostics"][0]["code"]
        )
        self.assertNotIn("super-secret-token", repr(metadata))


if __name__ == "__main__":
    unittest.main()
