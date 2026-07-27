"""Regression tests for worker and session health monitoring."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from idelium._internal.health import HEALTH_CONTRACT_VERSION, HealthMonitor


class HealthMonitorTest(unittest.TestCase):
    def test_startup_failure_is_classified_and_quarantined(self):
        driver = Mock()
        type(driver).current_window_handle = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("session=secret dead"))
        )
        monitor = HealthMonitor()

        result = monitor.check_driver("worker-1", driver, phase="startup").as_dict()

        self.assertEqual(HEALTH_CONTRACT_VERSION, result["schemaVersion"])
        self.assertEqual("health", result["category"])
        self.assertEqual("quarantined", result["status"])
        self.assertEqual("startup", result["phase"])
        self.assertTrue(monitor.is_quarantined("worker-1"))
        self.assertEqual("passed", result["cleanupStatus"])
        self.assertNotIn("secret", repr(result))
        driver.quit.assert_called_once()

    def test_mid_run_session_loss_is_separate_from_test_assertions(self):
        driver = Mock()
        type(driver).current_window_handle = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("lost"))
        )
        monitor = HealthMonitor()

        result = monitor.check_driver("worker-2", driver, phase="midRun").as_dict()

        self.assertEqual("quarantined", result["status"])
        self.assertEqual("health", result["diagnostics"][0]["category"])
        self.assertNotEqual("assertion", result["diagnostics"][0]["category"])

    def test_timeout_boundary_quarantines_without_driver_cleanup(self):
        monitor = HealthMonitor()

        healthy = monitor.check_timeout(
            "worker-3",
            elapsed_milliseconds=1000,
            timeout_milliseconds=1000,
        ).as_dict()
        timed_out = monitor.check_timeout(
            "worker-4",
            elapsed_milliseconds=1001,
            timeout_milliseconds=1000,
        ).as_dict()

        self.assertEqual("healthy", healthy["status"])
        self.assertEqual("quarantined", timed_out["status"])
        self.assertEqual("IDELIUM_HEALTH_TIMEOUT", timed_out["diagnostics"][0]["code"])
        self.assertTrue(monitor.is_quarantined("worker-4"))

    def test_recovery_removes_resource_from_quarantine(self):
        driver = Mock()
        type(driver).current_window_handle = property(lambda self: "window-1")
        monitor = HealthMonitor()
        monitor.quarantined_resources.add("worker-5")

        result = monitor.check_driver("worker-5", driver, phase="recovery").as_dict()

        self.assertEqual("recovered", result["status"])
        self.assertFalse(monitor.is_quarantined("worker-5"))
        driver.quit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
