"""Validated setup and teardown lifecycle hook contracts."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


LIFECYCLE_CONTRACT_VERSION = "idelium-lifecycle-hooks.v1"
DEFAULT_ALLOWED_HOOKS = frozenset({"log", "set_variable", "clear_artifacts"})
_SENSITIVE_PATTERN = re.compile(
    r"\b(api[-_\s]?key|authorization|cookie|password|secret|session|token)"
    r"\s*[:=]\s*([^&\s,;]+)",
    re.IGNORECASE,
)


class LifecycleHookError(ValueError):
    """Raised when lifecycle hooks cannot be planned or executed safely."""


def execute_lifecycle(
    *,
    test_body: Callable[[], None],
    suite_setup: list[dict[str, Any]] | None = None,
    test_setup: list[dict[str, Any]] | None = None,
    test_teardown: list[dict[str, Any]] | None = None,
    suite_teardown: list[dict[str, Any]] | None = None,
    handlers: dict[str, Callable[[dict[str, Any]], None]] | None = None,
    allowed_hooks: set[str] | frozenset[str] = DEFAULT_ALLOWED_HOOKS,
) -> dict[str, Any]:
    """Execute lifecycle hooks with deterministic teardown semantics."""

    hook_handlers = handlers or {}
    events: list[dict[str, Any]] = []
    status = "passed"
    interrupted = False

    try:
        _run_hooks("suiteSetup", suite_setup, hook_handlers, allowed_hooks, events)
        _run_hooks("testSetup", test_setup, hook_handlers, allowed_hooks, events)
        try:
            test_body()
            events.append({"phase": "test", "status": "passed", "diagnostics": []})
        except KeyboardInterrupt as error:
            interrupted = True
            status = "interrupted"
            events.append(_failure_event("test", error))
        except Exception as error:
            status = "failed"
            events.append(_failure_event("test", error))
    except Exception as error:
        status = "failed"
        events.append(_failure_event("setup", error))
    finally:
        teardown_status = _run_teardown_hooks(
            test_teardown,
            suite_teardown,
            hook_handlers,
            allowed_hooks,
            events,
        )
        if status == "passed" and teardown_status == "failed":
            status = "failed"

    return {
        "schemaVersion": LIFECYCLE_CONTRACT_VERSION,
        "status": status,
        "interrupted": interrupted,
        "events": events,
    }


def validate_hook(
    hook: dict[str, Any],
    *,
    allowed_hooks: set[str] | frozenset[str] = DEFAULT_ALLOWED_HOOKS,
) -> dict[str, Any]:
    """Validate one hook and return a redacted copy safe for diagnostics."""

    if not isinstance(hook, dict):
        raise LifecycleHookError("Lifecycle hook payload must be an object.")
    command = hook.get("command")
    if command not in allowed_hooks:
        raise LifecycleHookError("Lifecycle hook command is not allow-listed.")
    return {
        "command": str(command),
        "name": _redact_text(str(hook.get("name") or command)),
        "args": _redact_value(hook.get("args") or {}),
    }


def _run_hooks(
    phase: str,
    hooks: list[dict[str, Any]] | None,
    handlers: dict[str, Callable[[dict[str, Any]], None]],
    allowed_hooks: set[str] | frozenset[str],
    events: list[dict[str, Any]],
) -> None:
    for hook in hooks or []:
        safe_hook = validate_hook(hook, allowed_hooks=allowed_hooks)
        command = safe_hook["command"]
        if command not in handlers:
            raise LifecycleHookError("Lifecycle hook handler is not registered.")
        try:
            handlers[command](dict(hook.get("args") or {}))
            events.append(
                {
                    "phase": phase,
                    "hook": safe_hook,
                    "status": "passed",
                    "diagnostics": [],
                }
            )
        except Exception as error:
            events.append(_failure_event(phase, error, hook=safe_hook))
            raise


def _run_teardown_hooks(
    test_teardown: list[dict[str, Any]] | None,
    suite_teardown: list[dict[str, Any]] | None,
    handlers: dict[str, Callable[[dict[str, Any]], None]],
    allowed_hooks: set[str] | frozenset[str],
    events: list[dict[str, Any]],
) -> str:
    status = "passed"
    for phase, hooks in (
        ("testTeardown", test_teardown),
        ("suiteTeardown", suite_teardown),
    ):
        try:
            _run_hooks(phase, hooks, handlers, allowed_hooks, events)
        except Exception:
            status = "failed"
    return status


def _failure_event(
    phase: str,
    error: BaseException,
    *,
    hook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "phase": phase,
        "status": "failed",
        "diagnostics": [
            {
                "level": "error",
                "message": _redact_text(str(error)),
            }
        ],
    }
    if hook is not None:
        event["hook"] = hook
    return event


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    return _SENSITIVE_PATTERN.sub(lambda match: match.group(1) + "=[REDACTED]", value)
