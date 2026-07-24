"""WebDriver BiDi capability negotiation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
BIDI_CONSOLE_ARTIFACT_TYPE = "application/vnd.idelium.bidi.console+json"
BIDI_CONSOLE_SCHEMA_VERSION = "1.0"
BIDI_CONSOLE_MAX_EVENTS = 100
BIDI_CONSOLE_MAX_MESSAGE_LENGTH = 2000
BIDI_CONSOLE_EVENT_TYPES = {
    "log.entryAdded",
    "runtime.consoleAPICalled",
    "cdp.Runtime.consoleAPICalled",
}
BIDI_CONSOLE_LEVELS = {"debug", "error", "info", "log", "trace", "warning", "warn"}
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "key",
    "password",
    "secret",
    "session",
    "token",
}


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
        self._console_events: list[dict[str, Any]] = []

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

    def record_console_event(
        self,
        event: dict[str, Any],
        *,
        sensitive_values: list[Any] | None = None,
    ) -> None:
        """Record a normalized, redacted console event for later reporting."""

        normalized = normalize_bidi_console_event(
            event,
            sensitive_values=sensitive_values,
        )
        if normalized is not None:
            self._console_events.append(normalized)

    def console_artifact(self, *, limit: int = BIDI_CONSOLE_MAX_EVENTS):
        """Return a bounded console-event artifact or None when no events exist."""

        return build_bidi_console_artifact(self._console_events, limit=limit)

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


def redact_bidi_value(
    value: Any,
    *,
    sensitive_values: list[Any] | None = None,
) -> Any:
    """Redact credentials, tokens, cookies, and configured sensitive values."""

    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = (
                "[REDACTED]"
                if _is_sensitive_key(key_text)
                else redact_bidi_value(item, sensitive_values=sensitive_values)
            )
        return redacted
    if isinstance(value, list):
        return [
            redact_bidi_value(item, sensitive_values=sensitive_values) for item in value
        ]
    text = "" if value is None else str(value)
    for sensitive in sensitive_values or []:
        sensitive_text = str(sensitive)
        if sensitive_text:
            text = text.replace(sensitive_text, "[REDACTED]")
    return _redact_sensitive_assignments(text)


def normalize_bidi_console_event(
    event: dict[str, Any],
    *,
    sensitive_values: list[Any] | None = None,
    max_message_length: int = BIDI_CONSOLE_MAX_MESSAGE_LENGTH,
) -> dict[str, Any] | None:
    """Normalize one selected WebDriver BiDi console/log event fixture."""

    event_type = _safe_text(event.get("type") or event.get("method"))
    if event_type not in BIDI_CONSOLE_EVENT_TYPES:
        return None
    params = event.get("params") if isinstance(event.get("params"), dict) else event
    level = _normalize_console_level(params.get("level") or params.get("type"))
    source = params.get("source") if isinstance(params.get("source"), dict) else {}
    text = _console_event_text(params)
    redacted_text = redact_bidi_value(text, sensitive_values=sensitive_values)
    return {
        "type": event_type,
        "level": level,
        "text": _safe_text(redacted_text, limit=max_message_length),
        "timestamp": _safe_text(params.get("timestamp")),
        "source": _safe_text(source.get("realm") or source.get("context")),
        "url": _redact_url(source.get("url") or params.get("url"), sensitive_values),
        "lineNumber": _safe_int(source.get("lineNumber") or params.get("lineNumber")),
        "columnNumber": _safe_int(
            source.get("columnNumber") or params.get("columnNumber")
        ),
    }


def build_bidi_console_artifact(
    events: list[dict[str, Any]],
    *,
    limit: int = BIDI_CONSOLE_MAX_EVENTS,
) -> dict[str, Any] | None:
    """Build a bounded console-event artifact for execution reports."""

    bounded_limit = max(0, int(limit or 0))
    if not events or bounded_limit == 0:
        return None
    selected_events = events[:bounded_limit]
    return {
        "name": "bidi-console-events",
        "type": BIDI_CONSOLE_ARTIFACT_TYPE,
        "path": "",
        "data": {
            "schemaVersion": BIDI_CONSOLE_SCHEMA_VERSION,
            "totalEvents": len(events),
            "truncated": len(events) > len(selected_events),
            "events": selected_events,
        },
    }


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


def _console_event_text(params: dict[str, Any]) -> Any:
    if "text" in params:
        return params.get("text")
    if "message" in params:
        return params.get("message")
    if "args" in params:
        return " ".join(_safe_text(redact_bidi_value(arg)) for arg in params["args"])
    if "value" in params:
        return params.get("value")
    return ""


def _normalize_console_level(value: Any) -> str:
    level = _safe_text(value).lower()
    if level == "warn":
        return "warning"
    return level if level in BIDI_CONSOLE_LEVELS else "log"


def _redact_url(value: Any, sensitive_values: list[Any] | None = None) -> str:
    text = _safe_text(redact_bidi_value(value, sensitive_values=sensitive_values))
    parts = urlsplit(text)
    if not parts.query:
        return text
    query = urlencode(
        [
            (key, "[REDACTED]" if _is_sensitive_key(key) else val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _is_sensitive_key(value: Any) -> bool:
    key = str(value).lower()
    return any(sensitive in key for sensitive in _SENSITIVE_KEYS)


def _redact_sensitive_assignments(value: str) -> str:
    text = value
    text = re.sub(
        r"(?i)(authorization)(\s*[:=]\s*)Bearer\s+[^\s,;&]+",
        r"\1\2[REDACTED]",
        text,
    )
    for key in _SENSITIVE_KEYS:
        text = re.sub(
            rf"(?i)({key})(\s*[:=]\s*|\s+)([^\s,;&]+)",
            r"\1\2[REDACTED]",
            text,
        )
    return text


def _safe_text(value: Any, *, limit: int = BIDI_CONSOLE_MAX_MESSAGE_LENGTH) -> str:
    return ("" if value is None else str(value))[: max(0, limit)]


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
