"""WebDriver BiDi capability negotiation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BIDI_MODE_DISABLED = "disabled"
BIDI_MODE_AUTO = "auto"
BIDI_MODE_REQUIRED = "required"
BIDI_SUPPORTED_BROWSERS = {"chrome", "edge", "firefox"}
BIDI_MODES = {BIDI_MODE_DISABLED, BIDI_MODE_AUTO, BIDI_MODE_REQUIRED}
BIDI_LIFECYCLE_INACTIVE = "inactive"
BIDI_LIFECYCLE_OPEN = "open"
BIDI_LIFECYCLE_CLOSED = "closed"
BIDI_LIFECYCLE_FAILED = "failed"


@dataclass(frozen=True)
class BidiNegotiation:
    """Result of an optional WebDriver BiDi capability negotiation."""

    state: str
    mode: str
    requested: bool
    fallback_to_classic: bool
    message: str
    capabilities: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "mode": self.mode,
            "requested": self.requested,
            "fallbackToClassic": self.fallback_to_classic,
            "message": self.message,
            "capabilities": dict(self.capabilities),
        }


class BidiLifecycleError(RuntimeError):
    """Raised when an optional BiDi lifecycle cannot be started or closed safely."""


class BidiSessionLifecycle:
    """Track optional BiDi resources without exposing the session endpoint."""

    def __init__(self, negotiation: dict[str, Any] | BidiNegotiation | None = None):
        self.negotiation = self._negotiation_dict(negotiation)
        self.state = BIDI_LIFECYCLE_INACTIVE
        self.endpoint_available = False
        self.message = "WebDriver BiDi lifecycle is inactive."
        self._resources: list[Any] = []

    @staticmethod
    def _negotiation_dict(
        negotiation: dict[str, Any] | BidiNegotiation | None,
    ) -> dict[str, Any]:
        if isinstance(negotiation, BidiNegotiation):
            return negotiation.as_dict()
        return dict(negotiation or {})

    @staticmethod
    def _driver_capabilities(driver: Any) -> dict[str, Any]:
        capabilities = getattr(driver, "capabilities", None)
        if capabilities is None:
            capabilities = getattr(driver, "caps", None)
        if not isinstance(capabilities, dict):
            return {}
        return dict(capabilities or {})

    def register_resource(self, resource: Any) -> None:
        """Register a future BiDi listener or connection for deterministic cleanup."""

        self._resources.append(resource)

    def open(self, driver: Any) -> "BidiSessionLifecycle":
        """Start lifecycle tracking after a successful WebDriver session."""

        if self.negotiation.get("state") != "supported":
            self.state = BIDI_LIFECYCLE_INACTIVE
            self.message = self.negotiation.get(
                "message", "WebDriver BiDi was not negotiated for this session."
            )
            return self

        capabilities = self._driver_capabilities(driver)
        self.endpoint_available = isinstance(capabilities.get("webSocketUrl"), str)
        if not self.endpoint_available:
            if self.negotiation.get("mode") == BIDI_MODE_REQUIRED:
                self.state = BIDI_LIFECYCLE_FAILED
                self.message = (
                    "WebDriver BiDi was required, but the created session did not "
                    "return a BiDi endpoint."
                )
                raise BidiLifecycleError(self.message)
            self.state = BIDI_LIFECYCLE_INACTIVE
            self.message = (
                "WebDriver BiDi endpoint was not returned by the session. "
                "Continuing with classic WebDriver."
            )
            return self

        self.state = BIDI_LIFECYCLE_OPEN
        self.message = "WebDriver BiDi lifecycle started."
        return self

    def close(self) -> None:
        """Close registered BiDi resources in reverse creation order."""

        errors = []
        while self._resources:
            resource = self._resources.pop()
            close_method = getattr(resource, "close", None)
            if close_method is None:
                continue
            try:
                close_method()
            except Exception as err:  # pragma: no cover - defensive aggregation
                errors.append(str(err))

        if errors:
            self.state = BIDI_LIFECYCLE_FAILED
            self.message = "WebDriver BiDi lifecycle cleanup failed."
            raise BidiLifecycleError(self.message)
        if self.state == BIDI_LIFECYCLE_OPEN:
            self.state = BIDI_LIFECYCLE_CLOSED
            self.message = "WebDriver BiDi lifecycle closed."

    def as_dict(self) -> dict[str, Any]:
        """Return lifecycle metadata safe to persist in execution reports."""

        return {
            "state": self.state,
            "endpointAvailable": self.endpoint_available,
            "message": self.message,
        }


def normalize_bidi_mode(value: Any) -> str:
    """Normalize and validate the configured BiDi mode."""

    mode = str(value or BIDI_MODE_DISABLED).strip().lower()
    if mode not in BIDI_MODES:
        raise ValueError("bidiMode must be one of: disabled, auto, required")
    return mode


def negotiate_bidi_capabilities(
    *,
    browser: Any,
    mode: Any = BIDI_MODE_DISABLED,
    capabilities: dict[str, Any] | None = None,
) -> BidiNegotiation:
    """Return the BiDi negotiation decision and effective capabilities."""

    normalized_mode = normalize_bidi_mode(mode)
    effective_capabilities = dict(capabilities or {})
    browser_name = str(browser or "").strip().lower()
    manually_requested = effective_capabilities.get("webSocketUrl") is True
    requested = (
        normalized_mode in {BIDI_MODE_AUTO, BIDI_MODE_REQUIRED} or manually_requested
    )

    if not requested:
        return BidiNegotiation(
            state="disabled",
            mode=normalized_mode,
            requested=False,
            fallback_to_classic=False,
            message="WebDriver BiDi was not requested.",
            capabilities=effective_capabilities,
        )

    if browser_name not in BIDI_SUPPORTED_BROWSERS:
        message = (
            "WebDriver BiDi is not supported for browser "
            + (browser_name or "unknown")
            + "."
        )
        if normalized_mode == BIDI_MODE_REQUIRED:
            return BidiNegotiation(
                state="failed",
                mode=normalized_mode,
                requested=True,
                fallback_to_classic=False,
                message=message
                + " Use chrome, edge, or firefox, or set bidiMode=auto.",
                capabilities=effective_capabilities,
            )
        return BidiNegotiation(
            state="unsupported",
            mode=normalized_mode,
            requested=True,
            fallback_to_classic=True,
            message=message + " Continuing with classic WebDriver.",
            capabilities=effective_capabilities,
        )

    effective_capabilities["webSocketUrl"] = True
    return BidiNegotiation(
        state="supported",
        mode=normalized_mode,
        requested=True,
        fallback_to_classic=False,
        message="WebDriver BiDi capability negotiation succeeded.",
        capabilities=effective_capabilities,
    )
