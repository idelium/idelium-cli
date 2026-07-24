"""WebDriver BiDi capability negotiation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BIDI_MODE_DISABLED = "disabled"
BIDI_MODE_AUTO = "auto"
BIDI_MODE_REQUIRED = "required"
BIDI_SUPPORTED_BROWSERS = {"chrome", "edge", "firefox"}
BIDI_MODES = {BIDI_MODE_DISABLED, BIDI_MODE_AUTO, BIDI_MODE_REQUIRED}


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
