"""Central retry and wait policies for bounded Idelium operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from urllib3.util.retry import Retry


RETRY_POLICY_CONTRACT_VERSION = "idelium-retry-policy.v1"
DEFAULT_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_RETRYABLE_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})


class RetryPolicyError(ValueError):
    """Raised when a retry or wait policy is outside safe bounds."""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry contract for explicitly transient operations."""

    total: int = 2
    backoff_factor: float = 0.25
    status_forcelist: frozenset[int] = DEFAULT_TRANSIENT_HTTP_STATUSES
    allowed_methods: frozenset[str] = DEFAULT_RETRYABLE_METHODS

    def __post_init__(self) -> None:
        if self.total < 0:
            raise RetryPolicyError("Retry budget must not be negative.")
        if self.backoff_factor < 0:
            raise RetryPolicyError("Retry backoff must not be negative.")

    def to_urllib3(self) -> Retry:
        """Return the urllib3 retry object used by requests adapters."""

        return Retry(
            total=self.total,
            connect=self.total,
            read=self.total,
            status=self.total,
            backoff_factor=self.backoff_factor,
            status_forcelist=tuple(sorted(self.status_forcelist)),
            allowed_methods=frozenset(method.upper() for method in self.allowed_methods),
            raise_on_status=False,
        )

    def is_retryable_status(self, method: str, status_code: int) -> bool:
        """Return True only for allow-listed methods and transient statuses."""

        return (
            method.upper() in self.allowed_methods
            and status_code in self.status_forcelist
            and self.total > 0
        )

    def backoff_seconds(self, attempt: int) -> float:
        """Return bounded exponential backoff for a one-based retry attempt."""

        if attempt <= 0 or self.total == 0:
            return 0.0
        return self.backoff_factor * (2 ** (attempt - 1))

    def as_dict(self) -> dict[str, Any]:
        """Return stable policy metadata for diagnostics and reports."""

        return {
            "schemaVersion": RETRY_POLICY_CONTRACT_VERSION,
            "total": self.total,
            "backoffFactor": self.backoff_factor,
            "statusForcelist": sorted(self.status_forcelist),
            "allowedMethods": sorted(self.allowed_methods),
        }


@dataclass(frozen=True)
class WaitPolicy:
    """Bounded wait contract for polling-based runtime operations."""

    default_timeout_milliseconds: int
    max_timeout_milliseconds: int
    poll_interval_seconds: float

    def __post_init__(self) -> None:
        if self.default_timeout_milliseconds <= 0:
            raise RetryPolicyError("Default wait timeout must be positive.")
        if self.max_timeout_milliseconds <= 0:
            raise RetryPolicyError("Maximum wait timeout must be positive.")
        if self.default_timeout_milliseconds > self.max_timeout_milliseconds:
            raise RetryPolicyError("Default wait timeout must not exceed the maximum.")
        if self.poll_interval_seconds <= 0:
            raise RetryPolicyError("Poll interval must be positive.")

    def resolve_timeout_milliseconds(self, value: Any = None) -> int:
        """Return a validated timeout without hiding deterministic failures."""

        timeout = self.default_timeout_milliseconds if value is None else value
        if (
            not isinstance(timeout, int)
            or timeout <= 0
            or timeout > self.max_timeout_milliseconds
        ):
            raise RetryPolicyError("Wait timeout is outside the configured bounds.")
        return timeout

    def as_dict(self) -> dict[str, Any]:
        """Return stable wait policy metadata for diagnostics and reports."""

        return {
            "schemaVersion": RETRY_POLICY_CONTRACT_VERSION,
            "defaultTimeoutMilliseconds": self.default_timeout_milliseconds,
            "maxTimeoutMilliseconds": self.max_timeout_milliseconds,
            "pollIntervalSeconds": self.poll_interval_seconds,
        }
