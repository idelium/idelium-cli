"""Regression tests for isolated runtime execution contexts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from idelium._internal.isolation import (
    ISOLATION_CONTRACT_VERSION,
    IsolatedExecutionContext,
)


class RuntimeIsolationTest(unittest.TestCase):
    def test_each_worker_owns_configuration_artifacts_and_result_state(self):
        source_config = {"ideliumKey": "tenant-secret", "environment": "ci"}

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with (
                IsolatedExecutionContext(
                    "tenant-a",
                    "worker-1",
                    base_directory=base,
                    source_config=source_config,
                ) as first,
                IsolatedExecutionContext(
                    "tenant-a",
                    "worker-2",
                    base_directory=base,
                    source_config=source_config,
                ) as second,
            ):
                first.config["environment"] = "first"
                first.state["artifacts"].append("first.png")
                second.state["artifacts"].append("second.png")

                self.assertNotEqual(first.directory, second.directory)
                self.assertNotEqual(first.artifact_directory, second.artifact_directory)
                self.assertEqual("ci", source_config["environment"])
                self.assertEqual("ci", second.config["environment"])
                self.assertEqual(["first.png"], first.state["artifacts"])
                self.assertEqual(["second.png"], second.state["artifacts"])

            self.assertFalse(first.directory.exists())
            self.assertFalse(second.directory.exists())

    def test_cleanup_runs_when_execution_fails_or_is_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaises(KeyboardInterrupt):
                with IsolatedExecutionContext(
                    "tenant-a",
                    "worker-1",
                    base_directory=base,
                ) as context:
                    execution_directory = context.directory
                    raise KeyboardInterrupt()

            self.assertIsNotNone(execution_directory)
            self.assertFalse(execution_directory.exists())

    def test_metadata_is_versioned_and_omits_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with IsolatedExecutionContext(
                "tenant-a",
                "worker-1",
                base_directory=Path(directory),
                source_config={"password": "secret"},
            ) as context:
                metadata = context.metadata()

        self.assertEqual(ISOLATION_CONTRACT_VERSION, metadata["schemaVersion"])
        self.assertEqual("tenant-a", metadata["tenantId"])
        self.assertEqual("worker-1", metadata["workerId"])
        self.assertNotIn("secret", repr(metadata))
        self.assertNotIn("password", repr(metadata))


if __name__ == "__main__":
    unittest.main()
