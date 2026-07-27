"""Regression tests for setup and teardown lifecycle hooks."""

from __future__ import annotations

import unittest

from idelium._internal.lifecycle import (
    LIFECYCLE_CONTRACT_VERSION,
    LifecycleHookError,
    execute_lifecycle,
    validate_hook,
)


class LifecycleHookTest(unittest.TestCase):
    def test_successful_lifecycle_uses_deterministic_order(self):
        calls = []
        handlers = {
            "log": lambda args: calls.append(args["message"]),
            "clear_artifacts": lambda args: calls.append(args["path"]),
        }

        result = execute_lifecycle(
            suite_setup=[{"command": "log", "args": {"message": "suite-setup"}}],
            test_setup=[{"command": "log", "args": {"message": "test-setup"}}],
            test_body=lambda: calls.append("test"),
            test_teardown=[
                {"command": "clear_artifacts", "args": {"path": "test-artifacts"}}
            ],
            suite_teardown=[
                {"command": "clear_artifacts", "args": {"path": "suite-artifacts"}}
            ],
            handlers=handlers,
        )

        self.assertEqual(LIFECYCLE_CONTRACT_VERSION, result["schemaVersion"])
        self.assertEqual("passed", result["status"])
        self.assertEqual(
            ["suite-setup", "test-setup", "test", "test-artifacts", "suite-artifacts"],
            calls,
        )
        self.assertEqual(
            ["suiteSetup", "testSetup", "test", "testTeardown", "suiteTeardown"],
            [event["phase"] for event in result["events"]],
        )

    def test_teardown_runs_after_setup_failure(self):
        calls = []

        def fail_setup(_args):
            calls.append("suite-setup")
            raise RuntimeError("password=secret failed")

        result = execute_lifecycle(
            suite_setup=[{"command": "log"}],
            test_body=lambda: calls.append("test"),
            test_teardown=[{"command": "clear_artifacts"}],
            suite_teardown=[{"command": "clear_artifacts"}],
            handlers={
                "log": fail_setup,
                "clear_artifacts": lambda _args: calls.append("teardown"),
            },
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual(["suite-setup", "teardown", "teardown"], calls)
        self.assertNotIn("secret", repr(result))
        self.assertIn("[REDACTED]", repr(result))

    def test_teardown_runs_after_cancellation(self):
        calls = []

        def cancel():
            calls.append("test")
            raise KeyboardInterrupt()

        result = execute_lifecycle(
            test_body=cancel,
            test_teardown=[{"command": "clear_artifacts"}],
            handlers={"clear_artifacts": lambda _args: calls.append("teardown")},
        )

        self.assertEqual("interrupted", result["status"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(["test", "teardown"], calls)

    def test_hook_payloads_are_allow_listed_and_redacted(self):
        with self.assertRaises(LifecycleHookError):
            validate_hook({"command": "shell", "args": {"command": "rm -rf /"}})

        hook = validate_hook(
            {
                "command": "log",
                "name": "password=secret",
                "args": {"message": "token=abc"},
            }
        )

        self.assertNotIn("secret", repr(hook))
        self.assertNotIn("abc", repr(hook))
        self.assertIn("[REDACTED]", repr(hook))


if __name__ == "__main__":
    unittest.main()
