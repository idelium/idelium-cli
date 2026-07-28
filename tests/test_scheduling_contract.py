"""Regression tests for Idelium execution scheduling contracts."""

from __future__ import annotations

import unittest

from idelium._internal.scheduling import (
    SCHEDULING_CONTRACT_VERSION,
    SchedulingContractError,
    build_execution_schedule,
    normalize_worker_count,
)


class SchedulingContractTest(unittest.TestCase):
    def test_zero_workers_are_rejected_before_execution(self):
        with self.assertRaises(SchedulingContractError):
            normalize_worker_count(0)

    def test_one_worker_preserves_current_sequential_contract(self):
        schedule = build_execution_schedule(
            [{"id": 10, "stepId": 20}, {"id": 11, "stepId": 21}],
            workers=1,
        ).as_dict()

        self.assertEqual(SCHEDULING_CONTRACT_VERSION, schedule["schemaVersion"])
        self.assertEqual("sequential", schedule["mode"])
        self.assertEqual(1, schedule["maxWorkers"])
        self.assertEqual("input-order", schedule["resultOrdering"])
        self.assertEqual([0, 1], [item["index"] for item in schedule["items"]])

    def test_multiple_workers_preserve_deterministic_result_ordering(self):
        schedule = build_execution_schedule(
            [
                {"tenantId": "tenant-a", "id": 10, "stepId": 20},
                {"tenantId": "tenant-a", "id": 11, "stepId": 21},
                {"tenantId": "tenant-a", "id": 12, "stepId": 22},
            ],
            workers="2",
        ).as_dict()

        self.assertEqual("parallel", schedule["mode"])
        self.assertEqual(2, schedule["requestedWorkers"])
        self.assertEqual(2, schedule["maxWorkers"])
        self.assertEqual(
            "input-order-dispatch-with-stable-tie-break", schedule["ordering"]
        )
        self.assertEqual("input-order", schedule["resultOrdering"])
        self.assertIn("tenant", schedule["isolation"])
        self.assertIn("credentials", schedule["isolation"])
        self.assertEqual(
            ["10", "11", "12"], [item["testId"] for item in schedule["items"]]
        )

    def test_worker_count_is_bounded_by_available_work(self):
        schedule = build_execution_schedule([{"id": 10}], workers=8).as_dict()

        self.assertEqual(8, schedule["requestedWorkers"])
        self.assertEqual(1, schedule["maxWorkers"])
        self.assertEqual("sequential", schedule["mode"])


if __name__ == "__main__":
    unittest.main()
