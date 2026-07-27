"""Worker and session health monitoring contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from idelium._internal.commons.resultenum import Result
from idelium._internal.webdriver_adapter import W3CWebDriverAdapter


HEALTH_CONTRACT_VERSION = "idelium-health-monitor.v1"
_SENSITIVE_PATTERN = re.compile(
    r"\b(api[-_\s]?key|authorization|cookie|password|secret|session|token)"
    r"\s*[:=]\s*([^&\s,;]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HealthCheckResult:
    """Serializable health result separated from test assertions."""

    resource_id: str
    resource_type: str
    phase: str
    status: str
    diagnostics: tuple[dict[str, Any], ...] = ()
    cleanup_status: str = "not-required"

    def as_dict(self) -> dict[str, Any]:
        """Return stable JSON-compatible health metadata."""

        return {
            "schemaVersion": HEALTH_CONTRACT_VERSION,
            "resourceId": self.resource_id,
            "resourceType": self.resource_type,
            "phase": self.phase,
            "status": self.status,
            "category": "health",
            "cleanupStatus": self.cleanup_status,
            "diagnostics": [dict(diagnostic) for diagnostic in self.diagnostics],
        }


class HealthMonitor:
    """Track unhealthy workers and remote sessions with deterministic cleanup."""

    def __init__(self):
        self.quarantined_resources: set[str] = set()

    def check_driver(
        self,
        resource_id: str,
        driver: Any,
        *,
        phase: str,
    ) -> HealthCheckResult:
        """Check a WebDriver-like session and quarantine it when unhealthy."""

        result = W3CWebDriverAdapter(driver).is_session_healthy()
        if result.return_code == Result.OK:
            if resource_id in self.quarantined_resources:
                self.quarantined_resources.remove(resource_id)
                return HealthCheckResult(resource_id, "driver", phase, "recovered")
            return HealthCheckResult(resource_id, "driver", phase, "healthy")

        self.quarantined_resources.add(resource_id)
        cleanup = W3CWebDriverAdapter(driver).quit()
        cleanup_status = "passed" if cleanup.return_code == Result.OK else "failed"
        diagnostic = result.error.as_dict() if result.error else {}
        return HealthCheckResult(
            resource_id,
            "driver",
            phase,
            "quarantined",
            diagnostics=(_health_diagnostic(diagnostic),),
            cleanup_status=cleanup_status,
        )

    def check_timeout(
        self,
        resource_id: str,
        *,
        elapsed_milliseconds: int,
        timeout_milliseconds: int,
        resource_type: str = "worker",
    ) -> HealthCheckResult:
        """Classify health timeout boundaries without running test assertions."""

        if elapsed_milliseconds <= timeout_milliseconds:
            return HealthCheckResult(resource_id, resource_type, "timeout", "healthy")
        self.quarantined_resources.add(resource_id)
        return HealthCheckResult(
            resource_id,
            resource_type,
            "timeout",
            "quarantined",
            diagnostics=(
                {
                    "level": "error",
                    "code": "IDELIUM_HEALTH_TIMEOUT",
                    "category": "health",
                    "message": "Resource exceeded its health timeout budget.",
                },
            ),
            cleanup_status="not-required",
        )

    def is_quarantined(self, resource_id: str) -> bool:
        """Return whether the resource has been removed from scheduling."""

        return resource_id in self.quarantined_resources


def _health_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": _redact_text(str(diagnostic.get("level") or "error")),
        "code": _redact_text(str(diagnostic.get("code") or "IDELIUM_HEALTH_FAILED")),
        "category": "health",
        "message": _redact_text(
            str(diagnostic.get("message") or "Resource health check failed.")
        ),
        "transient": bool(diagnostic.get("transient")),
    }


def _redact_text(value: str) -> str:
    return _SENSITIVE_PATTERN.sub(lambda match: match.group(1) + "=[REDACTED]", value)
