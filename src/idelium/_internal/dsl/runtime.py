"""Safe runtime for canonical Idelium DSL AST documents."""

from __future__ import annotations

import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By


REDACTED = "[REDACTED]"
SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_LANGUAGE_VERSION = "1.0"
DEFAULT_WAIT_TIMEOUT_MILLISECONDS = 5000
DEFAULT_POLL_INTERVAL_SECONDS = 0.1
MAX_WAIT_TIMEOUT_MILLISECONDS = 120000


class DslRuntimeError(RuntimeError):
    """Raised when a canonical AST cannot be executed safely."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node: dict[str, Any] | None = None,
        remediation: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.node = node or {}
        self.remediation = remediation

    def as_diagnostic(self) -> dict[str, Any]:
        diagnostic = {
            "level": "error",
            "code": self.code,
            "message": self.message,
        }
        if self.remediation:
            diagnostic["remediation"] = self.remediation
        if "span" in self.node:
            diagnostic["span"] = self.node["span"]
        return diagnostic


@dataclass(frozen=True)
class DslRuntimeOptions:
    """Bounded execution options for a DSL AST runtime invocation."""

    screenshot_directory: str | Path | None = None
    default_wait_timeout_milliseconds: int = DEFAULT_WAIT_TIMEOUT_MILLISECONDS
    max_wait_timeout_milliseconds: int = MAX_WAIT_TIMEOUT_MILLISECONDS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic


class DslAstRuntime:
    """Execute a validated canonical AST through allow-listed browser commands."""

    _DOCUMENT_KEYS = {"kind", "schemaVersion", "languageVersion", "sourceName", "tests"}
    _TEST_KEYS = {"kind", "name", "statements", "span"}
    _LOCATOR_KEYS = {"strategy", "value"}
    _NODE_KEYS = {
        "open": {"kind", "url", "span"},
        "click": {"kind", "locator", "span"},
        "write": {"kind", "locator", "value", "sensitive", "span"},
        "wait": {"kind", "locator", "condition", "timeoutMilliseconds", "span"},
        "assertVisibility": {"kind", "locator", "expected", "span"},
        "assertText": {
            "kind",
            "locator",
            "comparison",
            "expected",
            "sensitive",
            "span",
        },
        "back": {"kind", "span"},
        "forward": {"kind", "span"},
        "screenshot": {"kind", "name", "span"},
    }

    def __init__(self, driver: Any, options: DslRuntimeOptions | None = None):
        self.driver = driver
        self.options = options or DslRuntimeOptions()
        self._handlers = {
            "open": self._open,
            "click": self._click,
            "write": self._write,
            "wait": self._wait,
            "assertVisibility": self._assert_visibility,
            "assertText": self._assert_text,
            "back": self._back,
            "forward": self._forward,
            "screenshot": self._screenshot,
        }

    def execute(self, ast: dict[str, Any]) -> dict[str, Any]:
        """Execute every AST test and return a stable serializable result."""

        self._validate_document(ast)
        tests = []
        for test in ast["tests"]:
            tests.append(self._execute_test(test))
        status = (
            "passed" if all(test["status"] == "passed" for test in tests) else "failed"
        )
        return {
            "schemaVersion": "dsl-runtime-result.v1",
            "status": status,
            "tests": tests,
        }

    def _execute_test(self, test: dict[str, Any]) -> dict[str, Any]:
        self._validate_test(test)
        statements = []
        failed = False
        for node in test["statements"]:
            if failed:
                statements.append(self._skipped_result(node))
                continue
            result = self._execute_node(node)
            statements.append(result)
            if result["status"] != "passed":
                failed = True
        status = "passed" if not failed else "failed"
        return {
            "name": test["name"],
            "status": status,
            "statements": statements,
        }

    def _execute_node(self, node: dict[str, Any]) -> dict[str, Any]:
        started = self.options.monotonic()
        try:
            self._validate_node(node)
            output = self._handlers[node["kind"]](node)
            return self._node_result(
                node,
                "passed",
                started,
                output=output,
            )
        except DslRuntimeError as error:
            return self._node_result(
                node,
                "failed",
                started,
                diagnostics=[error.as_diagnostic()],
            )
        except Exception as error:
            diagnostic = {
                "level": "error",
                "code": "IDELIUM_DSL_RUNTIME_COMMAND_FAILED",
                "message": _redact_text(str(error)),
            }
            if "span" in node:
                diagnostic["span"] = node["span"]
            return self._node_result(node, "failed", started, diagnostics=[diagnostic])

    def _validate_document(self, ast: dict[str, Any]) -> None:
        if not isinstance(ast, dict):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_AST",
                "The DSL runtime requires a canonical AST document object.",
            )
        self._reject_unknown_keys(ast, self._DOCUMENT_KEYS, None)
        if ast.get("kind") != "document":
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_DOCUMENT",
                "The DSL AST root must have kind document.",
            )
        if ast.get("schemaVersion") != SUPPORTED_SCHEMA_VERSION:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_UNSUPPORTED_SCHEMA",
                "Unsupported DSL AST schema version.",
                remediation="Use schemaVersion 1.0 or migrate the AST before execution.",
            )
        if ast.get("languageVersion") != SUPPORTED_LANGUAGE_VERSION:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_UNSUPPORTED_LANGUAGE",
                "Unsupported DSL language version.",
                remediation="Use idelium 1.0 source or migrate it before execution.",
            )
        tests = ast.get("tests")
        if not isinstance(tests, list) or not tests:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_MISSING_TESTS",
                "The DSL AST document must contain at least one test.",
            )

    def _validate_test(self, test: dict[str, Any]) -> None:
        self._reject_unknown_keys(test, self._TEST_KEYS, test)
        if test.get("kind") != "test":
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_TEST",
                "The DSL AST test node must have kind test.",
                node=test,
            )
        if not isinstance(test.get("name"), str) or not test["name"].strip():
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_TEST_NAME",
                "The DSL AST test node requires a non-empty name.",
                node=test,
            )
        if not isinstance(test.get("statements"), list):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_STATEMENTS",
                "The DSL AST test node requires a statements array.",
                node=test,
            )

    def _validate_node(self, node: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_NODE",
                "A DSL AST statement must be an object.",
            )
        kind = node.get("kind")
        if kind not in self._handlers:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_UNSUPPORTED_NODE",
                "Unsupported DSL AST statement kind.",
                node=node,
                remediation="Use one of: open, click, write, wait, assertVisibility, assertText, back, forward, screenshot.",
            )
        self._reject_unknown_keys(node, self._NODE_KEYS[kind], node)
        if "locator" in node:
            self._validate_locator(node["locator"], node)
        if kind == "wait":
            self._validate_wait(node)
        if kind == "assertVisibility" and node.get("expected") not in {
            "visible",
            "hidden",
        }:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                "Visibility assertions must expect visible or hidden.",
                node=node,
            )
        if kind == "assertText" and node.get("comparison") not in {
            "equals",
            "contains",
        }:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                "Text assertions must use equals or contains.",
                node=node,
            )

    def _validate_locator(self, locator: Any, node: dict[str, Any]) -> None:
        if not isinstance(locator, dict):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_LOCATOR",
                "A DSL locator must be an object.",
                node=node,
            )
        self._reject_unknown_keys(locator, self._LOCATOR_KEYS, node)
        if locator.get("strategy") not in {"css", "xpath"}:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_LOCATOR",
                "A DSL locator strategy must be css or xpath.",
                node=node,
            )
        if not isinstance(locator.get("value"), str) or locator["value"] == "":
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_LOCATOR",
                "A DSL locator selector must be a non-empty string.",
                node=node,
            )

    def _validate_wait(self, node: dict[str, Any]) -> None:
        if node.get("condition") not in {"present", "visible", "hidden", "clickable"}:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_WAIT",
                "Unsupported DSL wait condition.",
                node=node,
            )
        timeout = node.get(
            "timeoutMilliseconds",
            self.options.default_wait_timeout_milliseconds,
        )
        if (
            not isinstance(timeout, int)
            or timeout <= 0
            or timeout > self.options.max_wait_timeout_milliseconds
        ):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_TIMEOUT",
                "DSL wait timeout is outside the allowed execution bounds.",
                node=node,
            )

    def _reject_unknown_keys(
        self,
        node: dict[str, Any],
        allowed: set[str],
        diagnostic_node: dict[str, Any] | None,
    ) -> None:
        unknown = sorted(set(node) - allowed)
        if unknown:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_UNKNOWN_FIELD",
                "The DSL AST contains unsupported fields: " + ", ".join(unknown),
                node=diagnostic_node,
            )

    def _open(self, node: dict[str, Any]) -> dict[str, Any]:
        self.driver.get(node["url"])
        return {"url": _redact_url(node["url"])}

    def _click(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        element.click()
        return {"locator": self._safe_locator(node["locator"])}

    def _write(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        element.send_keys(node["value"])
        return {
            "locator": self._safe_locator(node["locator"]),
            "value": REDACTED if node.get("sensitive") else node["value"],
        }

    def _wait(self, node: dict[str, Any]) -> dict[str, Any]:
        timeout_ms = node.get(
            "timeoutMilliseconds",
            self.options.default_wait_timeout_milliseconds,
        )
        deadline = self.options.monotonic() + timeout_ms / 1000
        while True:
            if self._condition_matches(node["locator"], node["condition"]):
                return {
                    "locator": self._safe_locator(node["locator"]),
                    "condition": node["condition"],
                    "timeoutMilliseconds": timeout_ms,
                }
            if self.options.monotonic() >= deadline:
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_WAIT_TIMEOUT",
                    "Timed out waiting for DSL condition.",
                    node=node,
                )
            self.options.sleep(self.options.poll_interval_seconds)

    def _assert_visibility(self, node: dict[str, Any]) -> dict[str, Any]:
        visible = self._is_visible(node["locator"])
        expected_visible = node["expected"] == "visible"
        if visible != expected_visible:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Visibility assertion failed.",
                node=node,
            )
        return {
            "locator": self._safe_locator(node["locator"]),
            "expected": node["expected"],
        }

    def _assert_text(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        actual = getattr(element, "text", "")
        expected = node["expected"]
        passed = (
            actual == expected if node["comparison"] == "equals" else expected in actual
        )
        if not passed:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Text assertion failed.",
                node=node,
            )
        return {
            "locator": self._safe_locator(node["locator"]),
            "comparison": node["comparison"],
            "expected": REDACTED if node.get("sensitive") else expected,
        }

    def _back(self, node: dict[str, Any]) -> dict[str, Any]:
        self.driver.back()
        return {}

    def _forward(self, node: dict[str, Any]) -> dict[str, Any]:
        self.driver.forward()
        return {}

    def _screenshot(self, node: dict[str, Any]) -> dict[str, Any]:
        screenshot_dir = Path(self.options.screenshot_directory or ".").expanduser()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / f"{node['name']}.png"
        self.driver.get_screenshot_as_file(str(path))
        return {
            "artifact": {
                "name": node["name"],
                "type": "image/png",
                "path": str(path),
            }
        }

    def _condition_matches(self, locator: dict[str, str], condition: str) -> bool:
        if condition == "hidden":
            return not self._is_visible(locator)
        try:
            element = self._find(locator)
        except NoSuchElementException:
            return False
        if condition == "present":
            return True
        if condition == "visible":
            return bool(element.is_displayed())
        if condition == "clickable":
            return bool(element.is_displayed() and element.is_enabled())
        raise TimeoutException("Unsupported wait condition.")

    def _is_visible(self, locator: dict[str, str]) -> bool:
        try:
            return bool(self._find(locator).is_displayed())
        except NoSuchElementException:
            return False

    def _find(self, locator: dict[str, str]) -> Any:
        by = By.CSS_SELECTOR if locator["strategy"] == "css" else By.XPATH
        return self.driver.find_element(by, locator["value"])

    def _safe_locator(self, locator: dict[str, str]) -> dict[str, str]:
        return {"strategy": locator["strategy"], "value": locator["value"]}

    def _node_result(
        self,
        node: dict[str, Any],
        status: str,
        started: float,
        *,
        output: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = {
            "kind": node.get("kind", "unknown"),
            "status": status,
            "durationMilliseconds": max(
                0, int((self.options.monotonic() - started) * 1000)
            ),
            "diagnostics": diagnostics or [],
            "output": output or {},
        }
        if "span" in node:
            result["span"] = node["span"]
        return result

    def _skipped_result(self, node: dict[str, Any]) -> dict[str, Any]:
        result = {
            "kind": node.get("kind", "unknown"),
            "status": "skipped",
            "durationMilliseconds": 0,
            "diagnostics": [
                {
                    "level": "warning",
                    "code": "IDELIUM_DSL_RUNTIME_SKIPPED_AFTER_FAILURE",
                    "message": "Statement skipped because a previous DSL statement failed.",
                }
            ],
            "output": {},
        }
        if "span" in node:
            result["span"] = node["span"]
        return result


def execute_ast(
    ast: dict[str, Any],
    driver: Any,
    *,
    options: DslRuntimeOptions | None = None,
) -> dict[str, Any]:
    """Execute a canonical AST document with the minimal DSL runtime."""

    return DslAstRuntime(driver, options).execute(ast)


def _redact_text(value: str) -> str:
    return _SENSITIVE_PATTERN.sub(lambda match: match.group(1) + REDACTED, value)


def _redact_url(value: str) -> str:
    parts = urlsplit(value)
    query = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, REDACTED if _is_sensitive_key(key) else item))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("_", "-")
    return normalized in {
        "access-token",
        "api-key",
        "authorization",
        "cookie",
        "password",
        "refresh-token",
        "secret",
        "session",
        "token",
        "x-api-key",
    }


_SENSITIVE_PATTERN = re.compile(
    r"\b(api[-_\s]?key|access[-_\s]?token|authorization|cookie|password|refresh[-_\s]?token|secret|session|token)\s*[:=]\s*([^&\s,;]+)",
    re.IGNORECASE,
)
