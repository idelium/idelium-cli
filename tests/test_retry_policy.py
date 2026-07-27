"""Regression tests for centralized retry and wait policies."""

from __future__ import annotations

import unittest

from idelium._internal.retry_policy import (
    RETRY_POLICY_CONTRACT_VERSION,
    RetryPolicy,
    RetryPolicyError,
    WaitPolicy,
)


class RetryPolicyTest(unittest.TestCase):
    def test_retryable_operations_and_transient_statuses_are_explicit(self):
        policy = RetryPolicy(total=2)

        self.assertTrue(policy.is_retryable_status("GET", 503))
        self.assertTrue(policy.is_retryable_status("PUT", 429))
        self.assertFalse(policy.is_retryable_status("POST", 503))
        self.assertFalse(policy.is_retryable_status("GET", 400))

    def test_backoff_budget_is_bounded_and_deterministic(self):
        policy = RetryPolicy(total=3, backoff_factor=0.5)

        self.assertEqual(0.5, policy.backoff_seconds(1))
        self.assertEqual(1.0, policy.backoff_seconds(2))
        self.assertEqual(2.0, policy.backoff_seconds(3))
        self.assertEqual(0.0, policy.backoff_seconds(0))

    def test_policy_exports_urllib3_contract_used_by_http_client(self):
        policy = RetryPolicy(total=1)
        retry = policy.to_urllib3()
        metadata = policy.as_dict()

        self.assertEqual(1, retry.total)
        self.assertIn("GET", retry.allowed_methods)
        self.assertNotIn("POST", retry.allowed_methods)
        self.assertEqual(RETRY_POLICY_CONTRACT_VERSION, metadata["schemaVersion"])

    def test_deterministic_failures_are_not_hidden_by_retries(self):
        policy = RetryPolicy(total=2)

        self.assertFalse(policy.is_retryable_status("GET", 404))
        self.assertFalse(policy.is_retryable_status("PATCH", 409))

    def test_invalid_retry_budget_is_rejected(self):
        with self.assertRaises(RetryPolicyError):
            RetryPolicy(total=-1)


class WaitPolicyTest(unittest.TestCase):
    def test_wait_policy_resolves_default_and_explicit_timeout(self):
        policy = WaitPolicy(
            default_timeout_milliseconds=5000,
            max_timeout_milliseconds=120000,
            poll_interval_seconds=0.1,
        )

        self.assertEqual(5000, policy.resolve_timeout_milliseconds())
        self.assertEqual(250, policy.resolve_timeout_milliseconds(250))

    def test_wait_policy_rejects_unbounded_or_invalid_timeouts(self):
        policy = WaitPolicy(
            default_timeout_milliseconds=5000,
            max_timeout_milliseconds=10000,
            poll_interval_seconds=0.1,
        )

        for value in (0, -1, 10001, "10s"):
            with self.subTest(value=value):
                with self.assertRaises(RetryPolicyError):
                    policy.resolve_timeout_milliseconds(value)

    def test_wait_policy_rejects_invalid_polling_contracts(self):
        with self.assertRaises(RetryPolicyError):
            WaitPolicy(
                default_timeout_milliseconds=1000,
                max_timeout_milliseconds=500,
                poll_interval_seconds=0.1,
            )
        with self.assertRaises(RetryPolicyError):
            WaitPolicy(
                default_timeout_milliseconds=1000,
                max_timeout_milliseconds=1000,
                poll_interval_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
