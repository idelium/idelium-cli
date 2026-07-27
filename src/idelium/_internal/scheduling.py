"""Deterministic execution-scheduling contracts for Idelium runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SCHEDULING_CONTRACT_VERSION = "idelium-scheduling.v1"


class SchedulingContractError(ValueError):
    """Raised when a scheduling contract cannot be built safely."""


@dataclass(frozen=True)
class ExecutionSchedule:
    """Serializable scheduling metadata shared by future executors and reports."""

    schema_version: str
    requested_workers: int
    max_workers: int
    mode: str
    cancellation: str
    ordering: str
    result_ordering: str
    isolation: tuple[str, ...]
    items: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible scheduling contract."""

        return {
            "schemaVersion": self.schema_version,
            "requestedWorkers": self.requested_workers,
            "maxWorkers": self.max_workers,
            "mode": self.mode,
            "cancellation": self.cancellation,
            "ordering": self.ordering,
            "resultOrdering": self.result_ordering,
            "isolation": list(self.isolation),
            "items": [dict(item) for item in self.items],
        }


def build_execution_schedule(
    work_items: list[dict[str, Any]],
    *,
    workers: Any = 1,
) -> ExecutionSchedule:
    """Build a deterministic scheduling contract without executing any work."""

    requested_workers = normalize_worker_count(workers)
    max_workers = min(requested_workers, max(1, len(work_items)))
    mode = "sequential" if max_workers == 1 else "parallel"
    items = tuple(_schedule_item(index, item) for index, item in enumerate(work_items))
    return ExecutionSchedule(
        schema_version=SCHEDULING_CONTRACT_VERSION,
        requested_workers=requested_workers,
        max_workers=max_workers,
        mode=mode,
        cancellation="fail-fast-with-in-test-interruption",
        ordering="input-order-dispatch-with-stable-tie-break",
        result_ordering="input-order",
        isolation=(
            "tenant",
            "credentials",
            "browser-session",
            "configuration",
            "temporary-files",
            "artifacts",
        ),
        items=items,
    )


def normalize_worker_count(value: Any) -> int:
    """Normalize worker input and reject unsafe zero or negative concurrency."""

    try:
        workers = int(value)
    except (TypeError, ValueError) as error:
        raise SchedulingContractError("Worker count must be an integer.") from error
    if workers <= 0:
        raise SchedulingContractError("Worker count must be greater than zero.")
    return workers


def _schedule_item(index: int, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "tenantId": _safe_optional_string(item.get("tenantId")),
        "testId": _safe_optional_string(item.get("testId") or item.get("id")),
        "stepId": _safe_optional_string(item.get("stepId")),
    }


def _safe_optional_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)[:256]
