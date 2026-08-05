"""Safe runtime for canonical Idelium DSL AST documents."""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from idelium._internal.retry_policy import RetryPolicyError, WaitPolicy


REDACTED = "[REDACTED]"
SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_LANGUAGE_VERSION = "1.0"
ASSERTION_CONTRACT_VERSION = "dsl-assertion.v1"
TRACE_CONTRACT_VERSION = "performed-step-trace.v1"
DEFAULT_WAIT_TIMEOUT_MILLISECONDS = 5000
DEFAULT_POLL_INTERVAL_SECONDS = 0.1
MAX_WAIT_TIMEOUT_MILLISECONDS = 120000
DEFAULT_MAX_LOOP_ITERATIONS = 50
DEFAULT_MAX_MACRO_EXPANSIONS = 25
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INTERPOLATION_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class DslRuntimeError(RuntimeError):
    """Raised when a canonical AST cannot be executed safely."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node: dict[str, Any] | None = None,
        remediation: str | None = None,
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.node = node or {}
        self.remediation = remediation
        self.data = data or {}

    def as_diagnostic(self) -> dict[str, Any]:
        diagnostic = {
            "level": "error",
            "code": self.code,
            "message": self.message,
        }
        if self.remediation:
            diagnostic["remediation"] = self.remediation
        if self.data:
            diagnostic["data"] = self.data
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
    variables: dict[str, str] = field(default_factory=dict)
    secret_names: set[str] = field(default_factory=set)
    max_loop_iterations: int = DEFAULT_MAX_LOOP_ITERATIONS
    max_macro_expansions: int = DEFAULT_MAX_MACRO_EXPANSIONS


class DslAstRuntime:
    """Execute a validated canonical AST through allow-listed browser commands."""

    _DOCUMENT_KEYS = {
        "kind",
        "schemaVersion",
        "languageVersion",
        "sourceName",
        "steps",
        "tests",
    }
    _TEST_KEYS = {"kind", "name", "statements", "span"}
    _REUSABLE_STEP_KEYS = {"kind", "name", "parameters", "statements", "span"}
    _LOCATOR_KEYS = {"strategy", "value"}
    _NODE_KEYS = {
        "open": {"kind", "url", "span"},
        "variable": {"kind", "name", "value", "secret", "span"},
        "call": {"kind", "name", "arguments", "span"},
        "if": {"kind", "condition", "locator", "statements", "span"},
        "repeat": {"kind", "count", "statements", "span"},
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
        "assertValue": {
            "kind",
            "locator",
            "comparison",
            "expected",
            "sensitive",
            "span",
        },
        "assertCount": {"kind", "locator", "comparison", "expected", "span"},
        "assertRuntime": {
            "kind",
            "target",
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
        self._variables: dict[str, str] = {}
        self._secret_names: set[str] = set()
        self._secret_values: set[str] = set()
        self._reusable_steps: dict[str, dict[str, Any]] = {}
        self._macro_depth = 0
        self._handlers = {
            "open": self._open,
            "variable": self._variable,
            "call": self._call,
            "if": self._if,
            "repeat": self._repeat,
            "click": self._click,
            "write": self._write,
            "wait": self._wait,
            "assertVisibility": self._assert_visibility,
            "assertText": self._assert_text,
            "assertValue": self._assert_value,
            "assertCount": self._assert_count,
            "assertRuntime": self._assert_runtime,
            "back": self._back,
            "forward": self._forward,
            "screenshot": self._screenshot,
        }

    def execute(self, ast: dict[str, Any]) -> dict[str, Any]:
        """Execute every AST test and return a stable serializable result."""

        self._validate_document(ast)
        self._reusable_steps = self._collect_reusable_steps(ast)
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
        self._variables = {str(key): str(value) for key, value in self.options.variables.items()}
        self._secret_names = {
            str(name)
            for name in self.options.secret_names
            if str(name) in self._variables
        }
        self._secret_values = {
            self._variables[name] for name in self._secret_names if self._variables[name]
        }
        statements, failed = self._execute_sequence(test["statements"])
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
            status = "failed" if output.pop("__failed", False) else "passed"
            return self._node_result(
                node,
                status,
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
        except NoSuchElementException as error:
            diagnostic = {
                "level": "error",
                "code": "IDELIUM_DSL_RUNTIME_LOCATOR_NOT_FOUND",
                "message": self._redact_text(str(error)),
            }
            if "span" in node:
                diagnostic["span"] = node["span"]
            return self._node_result(node, "failed", started, diagnostics=[diagnostic])
        except Exception as error:
            diagnostic = {
                "level": "error",
                "code": "IDELIUM_DSL_RUNTIME_COMMAND_FAILED",
                "message": self._redact_text(str(error)),
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
        steps = ast.get("steps", [])
        if not isinstance(steps, list):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_REUSABLE_STEPS",
                "Reusable step definitions must be an array.",
            )
        self._validate_reusable_steps(steps)

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
                remediation="Use one of: variable, call, open, click, write, wait, assertVisibility, assertText, back, forward, screenshot.",
            )
        self._reject_unknown_keys(node, self._NODE_KEYS[kind], node)
        if kind == "variable":
            self._validate_variable(node)
        if kind == "call":
            self._validate_call(node)
        if kind == "if":
            self._validate_if(node)
        if kind == "repeat":
            self._validate_repeat(node)
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
        if kind == "assertValue" and node.get("comparison") not in {
            "equals",
            "contains",
        }:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                "Value assertions must use equals or contains.",
                node=node,
            )
        if kind == "assertCount" and node.get("comparison") not in {
            "equals",
            "greater_than",
            "less_than",
            "at_least",
            "at_most",
        }:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                "Count assertions must use a supported count comparison.",
                node=node,
            )
        if kind == "assertCount" and (
            not isinstance(node.get("expected"), int) or node["expected"] < 0
        ):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                "Count assertions require a non-negative integer expected value.",
                node=node,
            )
        if kind == "assertRuntime":
            if node.get("target") not in {"url", "title"}:
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                    "Runtime assertions must target url or title.",
                    node=node,
                )
            if node.get("comparison") not in {"equals", "contains"}:
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_ASSERTION",
                    "Runtime assertions must use equals or contains.",
                    node=node,
                )

    def _validate_reusable_steps(self, steps: list[dict[str, Any]]) -> None:
        seen = set()
        for reusable_step in steps:
            if not isinstance(reusable_step, dict):
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_REUSABLE_STEP",
                    "Reusable step definitions must be objects.",
                )
            self._reject_unknown_keys(
                reusable_step,
                self._REUSABLE_STEP_KEYS,
                reusable_step,
            )
            if reusable_step.get("kind") != "reusableStep":
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_REUSABLE_STEP",
                    "Reusable step definitions must use kind reusableStep.",
                    node=reusable_step,
                )
            name = reusable_step.get("name")
            if not isinstance(name, str) or not _VARIABLE_NAME_RE.fullmatch(name):
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_REUSABLE_STEP",
                    "Reusable step names must be valid identifiers.",
                    node=reusable_step,
                )
            if name in seen:
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_DUPLICATE_REUSABLE_STEP",
                    "Reusable step names must be unique.",
                    node=reusable_step,
                )
            seen.add(name)
            parameters = reusable_step.get("parameters")
            if not isinstance(parameters, list) or not all(
                isinstance(parameter, str) and _VARIABLE_NAME_RE.fullmatch(parameter)
                for parameter in parameters
            ):
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_INVALID_REUSABLE_STEP",
                    "Reusable step parameters must be valid identifiers.",
                    node=reusable_step,
                )
            if len(parameters) != len(set(parameters)):
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_DUPLICATE_PARAMETER",
                    "Reusable step parameters must be unique.",
                    node=reusable_step,
                )
            self._validate_statement_list(reusable_step.get("statements"), reusable_step)

    def _collect_reusable_steps(
        self, ast: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return {step["name"]: step for step in ast.get("steps", [])}

    def _validate_call(self, node: dict[str, Any]) -> None:
        name = node.get("name")
        if not isinstance(name, str) or not _VARIABLE_NAME_RE.fullmatch(name):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_CALL",
                "Reusable step calls require a valid step name.",
                node=node,
            )
        arguments = node.get("arguments")
        if not isinstance(arguments, list) or not all(
            isinstance(argument, str) for argument in arguments
        ):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_CALL",
                "Reusable step calls require a string argument list.",
                node=node,
            )

    def _validate_if(self, node: dict[str, Any]) -> None:
        if node.get("condition") not in {"visible", "hidden"}:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_IF",
                "If conditions must be visible or hidden.",
                node=node,
            )
        self._validate_statement_list(node.get("statements"), node)

    def _validate_repeat(self, node: dict[str, Any]) -> None:
        count = node.get("count")
        if not isinstance(count, int) or count <= 0:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_REPEAT",
                "Repeat count must be a positive integer.",
                node=node,
            )
        if count > self.options.max_loop_iterations:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_LOOP_BOUND_EXCEEDED",
                "Repeat count exceeds the configured runtime bound.",
                node=node,
            )
        self._validate_statement_list(node.get("statements"), node)

    def _validate_statement_list(self, statements: Any, node: dict[str, Any]) -> None:
        if not isinstance(statements, list):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_STATEMENTS",
                "Control blocks require a statements array.",
                node=node,
            )
        for child in statements:
            self._validate_node(child)

    def _validate_variable(self, node: dict[str, Any]) -> None:
        if not isinstance(node.get("name"), str) or not _VARIABLE_NAME_RE.fullmatch(
            node["name"]
        ):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_VARIABLE",
                "Variable names must start with a letter or underscore and contain only letters, numbers, or underscore.",
                node=node,
            )
        if not isinstance(node.get("value"), str):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_VARIABLE",
                "Variable values must be strings.",
                node=node,
            )
        if not isinstance(node.get("secret"), bool):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_VARIABLE",
                "Variable secret metadata must be boolean.",
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
        try:
            self._wait_policy().resolve_timeout_milliseconds(
                node.get("timeoutMilliseconds")
            )
        except RetryPolicyError as error:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_TIMEOUT",
                str(error),
                node=node,
            ) from error

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
        url = self._interpolate(node["url"], node)
        self._validate_runtime_url(url, node)
        self.driver.get(url)
        return {"url": self._redact_url(url)}

    def _variable(self, node: dict[str, Any]) -> dict[str, Any]:
        value = self._interpolate(node["value"], node)
        self._variables[node["name"]] = value
        if node.get("secret"):
            self._secret_names.add(node["name"])
            if value:
                self._secret_values.add(value)
        else:
            self._secret_names.discard(node["name"])
        return {"name": node["name"], "secret": bool(node.get("secret"))}

    def _call(self, node: dict[str, Any]) -> dict[str, Any]:
        if node["name"] not in self._reusable_steps:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_UNKNOWN_REUSABLE_STEP",
                "Reusable step is not defined.",
                node=node,
            )
        if self._macro_depth >= self.options.max_macro_expansions:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_MACRO_EXPANSION_LIMIT",
                "Reusable step expansion exceeded the configured runtime bound.",
                node=node,
            )
        reusable_step = self._reusable_steps[node["name"]]
        parameters = reusable_step["parameters"]
        if len(node["arguments"]) != len(parameters):
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_CALL_ARITY_MISMATCH",
                "Reusable step call argument count does not match its definition.",
                node=node,
            )
        saved_variables = dict(self._variables)
        saved_secret_names = set(self._secret_names)
        saved_secret_values = set(self._secret_values)
        arguments = []
        try:
            for parameter, argument in zip(parameters, node["arguments"], strict=True):
                value = self._interpolate(argument, node)
                self._variables[parameter] = value
                if self._contains_secret_reference(argument):
                    self._secret_names.add(parameter)
                    if value:
                        self._secret_values.add(value)
                arguments.append(
                    REDACTED if self._contains_secret_reference(argument) else value
                )
            self._macro_depth += 1
            statements, failed = self._execute_sequence(reusable_step["statements"])
            return {
                "name": node["name"],
                "arguments": arguments,
                "statements": statements,
                "__failed": failed,
            }
        finally:
            self._macro_depth = max(0, self._macro_depth - 1)
            self._variables = saved_variables
            self._secret_names = saved_secret_names
            self._secret_values = saved_secret_values

    def _if(self, node: dict[str, Any]) -> dict[str, Any]:
        matched = self._is_visible(node["locator"])
        if node["condition"] == "hidden":
            matched = not matched
        if not matched:
            return {
                "conditionMatched": False,
                "statements": [
                    self._skipped_result(
                        child,
                        code="IDELIUM_DSL_RUNTIME_SKIPPED_CONDITION_FALSE",
                        message="Statement skipped because the if condition was false.",
                    )
                    for child in node["statements"]
                ],
            }
        statements, failed = self._execute_sequence(node["statements"])
        return {
            "conditionMatched": True,
            "statements": statements,
            "__failed": failed,
        }

    def _repeat(self, node: dict[str, Any]) -> dict[str, Any]:
        iterations = []
        failed = False
        for iteration in range(node["count"]):
            if failed:
                iterations.append(
                    {
                        "index": iteration,
                        "statements": [
                            self._skipped_result(child)
                            for child in node["statements"]
                        ],
                    }
                )
                continue
            statements, failed = self._execute_sequence(node["statements"])
            iterations.append({"index": iteration, "statements": statements})
        return {"count": node["count"], "iterations": iterations, "__failed": failed}

    def _click(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        self._scroll_element_into_view(element)
        try:
            element.click()
        except ElementClickInterceptedException:
            self._scroll_element_into_view(element)
            ActionChains(self.driver).move_to_element(element).click(element).perform()
        return {"locator": self._safe_locator(node["locator"])}

    def _write(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        value = self._interpolate(node["value"], node)
        element.send_keys(value)
        return {
            "locator": self._safe_locator(node["locator"]),
            "value": REDACTED
            if node.get("sensitive") or self._contains_secret_reference(node["value"])
            else value,
        }

    def _wait(self, node: dict[str, Any]) -> dict[str, Any]:
        wait_policy = self._wait_policy()
        timeout_ms = wait_policy.resolve_timeout_milliseconds(
            node.get("timeoutMilliseconds")
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
            self.options.sleep(wait_policy.poll_interval_seconds)

    def _assert_visibility(self, node: dict[str, Any]) -> dict[str, Any]:
        visible = self._is_visible(node["locator"])
        expected_visible = node["expected"] == "visible"
        if visible != expected_visible:
            assertion = self._assertion_payload(
                "visibility",
                node["expected"],
                "equals",
                node["expected"],
                "visible" if visible else "hidden",
                sensitive=False,
            )
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Visibility assertion failed.",
                node=node,
                data={"assertion": assertion},
            )
        return {
            "assertion": self._assertion_payload(
                "visibility",
                node["expected"],
                "equals",
                node["expected"],
                "visible" if visible else "hidden",
                sensitive=False,
            ),
            "locator": self._safe_locator(node["locator"]),
        }

    def _assert_text(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        actual = getattr(element, "text", "")
        expected = self._interpolate(node["expected"], node)
        passed = (
            actual == expected if node["comparison"] == "equals" else expected in actual
        )
        sensitive = node.get("sensitive") or self._contains_secret_reference(
            node["expected"]
        )
        assertion = self._assertion_payload(
            "text",
            "text",
            node["comparison"],
            expected,
            actual,
            sensitive=sensitive,
        )
        if not passed:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Text assertion failed.",
                node=node,
                data={"assertion": assertion},
            )
        return {
            "locator": self._safe_locator(node["locator"]),
            "assertion": assertion,
        }

    def _assert_value(self, node: dict[str, Any]) -> dict[str, Any]:
        element = self._find(node["locator"])
        actual = element.get_attribute("value") or ""
        expected = self._interpolate(node["expected"], node)
        passed = (
            actual == expected if node["comparison"] == "equals" else expected in actual
        )
        sensitive = node.get("sensitive") or self._contains_secret_reference(
            node["expected"]
        )
        assertion = self._assertion_payload(
            "value",
            "value",
            node["comparison"],
            expected,
            actual,
            sensitive=sensitive,
        )
        if not passed:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Value assertion failed.",
                node=node,
                data={"assertion": assertion},
            )
        return {"locator": self._safe_locator(node["locator"]), "assertion": assertion}

    def _assert_count(self, node: dict[str, Any]) -> dict[str, Any]:
        actual = len(self._find_elements(node["locator"]))
        expected = node["expected"]
        passed = _compare_count(actual, expected, node["comparison"])
        assertion = self._assertion_payload(
            "count",
            "count",
            node["comparison"],
            expected,
            actual,
            sensitive=False,
        )
        if not passed:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Count assertion failed.",
                node=node,
                data={"assertion": assertion},
            )
        return {"locator": self._safe_locator(node["locator"]), "assertion": assertion}

    def _assert_runtime(self, node: dict[str, Any]) -> dict[str, Any]:
        actual = (
            self.driver.current_url if node["target"] == "url" else self.driver.title
        )
        expected = self._interpolate(node["expected"], node)
        passed = (
            actual == expected if node["comparison"] == "equals" else expected in actual
        )
        sensitive = self._contains_secret_reference(node["expected"])
        assertion = self._assertion_payload(
            "runtime",
            node["target"],
            node["comparison"],
            expected,
            actual,
            sensitive=sensitive,
        )
        if not passed:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_ASSERTION_FAILED",
                "Runtime assertion failed.",
                node=node,
                data={"assertion": assertion},
            )
        return {"assertion": assertion}

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
        return self.driver.find_element(by, self._interpolate(locator["value"], {}))

    def _find_elements(self, locator: dict[str, str]) -> Any:
        by = By.CSS_SELECTOR if locator["strategy"] == "css" else By.XPATH
        return self.driver.find_elements(by, self._interpolate(locator["value"], {}))

    def _scroll_element_into_view(self, element: Any) -> None:
        execute_script = getattr(self.driver, "execute_script", None)
        if callable(execute_script):
            execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                element,
            )

    def _safe_locator(self, locator: dict[str, str]) -> dict[str, str]:
        return {
            "strategy": locator["strategy"],
            "value": self._redact_text(self._interpolate(locator["value"], {})),
        }

    def _interpolate(self, value: str, node: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in self._variables:
                raise DslRuntimeError(
                    "IDELIUM_DSL_RUNTIME_MISSING_VARIABLE",
                    "Referenced DSL variable is not defined.",
                    node=node,
                    remediation="Declare it earlier in the same test with let or secret, or pass it as a runtime variable.",
                )
            return self._variables[name]

        return _INTERPOLATION_RE.sub(replace, value)

    def _contains_secret_reference(self, value: str) -> bool:
        return any(
            match.group(1) in self._secret_names
            for match in _INTERPOLATION_RE.finditer(value)
        )

    def _validate_runtime_url(self, value: str, node: dict[str, Any]) -> None:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_INVALID_URL",
                "Open command URL must resolve to absolute HTTP or HTTPS.",
                node=node,
            )
        if parts.username or parts.password:
            raise DslRuntimeError(
                "IDELIUM_DSL_RUNTIME_URL_CREDENTIALS",
                "URL credentials are not allowed.",
                node=node,
            )

    def _redact_text(self, value: str) -> str:
        redacted = _redact_text(value)
        for secret_value in sorted(self._secret_values, key=len, reverse=True):
            if secret_value:
                redacted = redacted.replace(secret_value, REDACTED)
        return redacted

    def _redact_url(self, value: str) -> str:
        redacted = _redact_url(value)
        for secret_value in sorted(self._secret_values, key=len, reverse=True):
            if secret_value:
                redacted = redacted.replace(secret_value, REDACTED)
        return redacted

    def _wait_policy(self) -> WaitPolicy:
        return WaitPolicy(
            default_timeout_milliseconds=self.options.default_wait_timeout_milliseconds,
            max_timeout_milliseconds=self.options.max_wait_timeout_milliseconds,
            poll_interval_seconds=self.options.poll_interval_seconds,
        )

    def _assertion_payload(
        self,
        kind: str,
        target: str,
        operator: str,
        expected: Any,
        actual: Any,
        *,
        sensitive: bool,
    ) -> dict[str, Any]:
        if sensitive:
            expected_value = REDACTED
            actual_value = REDACTED
        else:
            expected_value = self._redact_text(str(expected))
            actual_value = self._redact_text(str(actual))
        return {
            "contractVersion": ASSERTION_CONTRACT_VERSION,
            "kind": kind,
            "target": target,
            "operator": operator,
            "expected": expected_value,
            "actual": actual_value,
        }

    def _execute_sequence(
        self, statements: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], bool]:
        results = []
        failed = False
        for node in statements:
            if failed:
                results.append(self._skipped_result(node))
                continue
            result = self._execute_node(node)
            results.append(result)
            if result["status"] != "passed":
                failed = True
        return results, failed

    def _node_result(
        self,
        node: dict[str, Any],
        status: str,
        started: float,
        *,
        output: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        duration_ms = max(0, int((self.options.monotonic() - started) * 1000))
        safe_diagnostics = [
            self._safe_diagnostic(diagnostic) for diagnostic in (diagnostics or [])
        ]
        safe_output = dict(output or {})
        if "locator" in node and "locator" not in safe_output:
            safe_output["locator"] = self._safe_locator(node["locator"])
        result = {
            "kind": node.get("kind", "unknown"),
            "status": status,
            "durationMilliseconds": duration_ms,
            "diagnostics": safe_diagnostics,
            "output": safe_output,
            "trace": self._trace_payload(
                node,
                status,
                duration_ms,
                diagnostics=safe_diagnostics,
            ),
        }
        if "span" in node:
            result["span"] = node["span"]
        return result

    def _skipped_result(
        self,
        node: dict[str, Any],
        *,
        code: str = "IDELIUM_DSL_RUNTIME_SKIPPED_AFTER_FAILURE",
        message: str = "Statement skipped because a previous DSL statement failed.",
    ) -> dict[str, Any]:
        duration_ms = 0
        diagnostics = [
            {
                "level": "warning",
                "code": code,
                "message": message,
            }
        ]
        safe_output = {}
        if "locator" in node:
            safe_output["locator"] = self._safe_locator(node["locator"])
        result = {
            "kind": node.get("kind", "unknown"),
            "status": "skipped",
            "durationMilliseconds": duration_ms,
            "diagnostics": diagnostics,
            "output": safe_output,
            "trace": self._trace_payload(
                node,
                "skipped",
                duration_ms,
                diagnostics=diagnostics,
            ),
        }
        if "span" in node:
            result["span"] = node["span"]
        return result

    def _trace_payload(
        self,
        node: dict[str, Any],
        status: str,
        duration_ms: int,
        *,
        diagnostics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        trace = {
            "schemaVersion": TRACE_CONTRACT_VERSION,
            "identity": self._trace_identity(node),
            "timing": {"durationMilliseconds": duration_ms},
            "status": status,
            "page": self._safe_page_context(),
            "diagnostics": [
                self._trace_diagnostic(diagnostic) for diagnostic in diagnostics
            ],
        }
        if "locator" in node:
            trace["locator"] = self._safe_locator(node["locator"])
        if status == "skipped":
            trace["interrupted"] = True
        return trace

    def _trace_identity(self, node: dict[str, Any]) -> dict[str, Any]:
        identity = {"kind": self._redact_text(str(node.get("kind", "unknown")))}
        if "name" in node:
            identity["name"] = self._redact_text(str(node["name"]))
        if "span" in node:
            identity["span"] = node["span"]
        return identity

    def _safe_page_context(self) -> dict[str, str]:
        return {
            "url": self._safe_driver_attribute("current_url", redact_url=True),
            "title": self._safe_driver_attribute("title", redact_url=False),
        }

    def _safe_driver_attribute(self, name: str, *, redact_url: bool) -> str:
        try:
            value = getattr(self.driver, name, "")
        except Exception:
            return ""
        if value is None:
            return ""
        text = str(value)
        return self._redact_url(text) if redact_url else self._redact_text(text)

    def _safe_diagnostic(self, diagnostic: dict[str, Any]) -> dict[str, Any]:
        safe = dict(diagnostic)
        if "message" in safe:
            safe["message"] = self._redact_text(str(safe["message"]))
        if "remediation" in safe:
            safe["remediation"] = self._redact_text(str(safe["remediation"]))
        if "data" in safe:
            safe["data"] = self._redact_value(safe["data"])
        return safe

    def _trace_diagnostic(self, diagnostic: dict[str, Any]) -> dict[str, Any]:
        code = str(diagnostic.get("code") or "IDELIUM_DSL_RUNTIME_DIAGNOSTIC")
        trace_diagnostic = {
            "level": self._redact_text(str(diagnostic.get("level") or "error")),
            "code": self._redact_text(code),
            "category": _diagnostic_category(code),
            "message": self._redact_text(str(diagnostic.get("message") or "")),
        }
        if "span" in diagnostic:
            trace_diagnostic["span"] = diagnostic["span"]
        return trace_diagnostic

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                self._redact_text(str(key)): self._redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value


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


def _compare_count(actual: int, expected: int, operator: str) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "greater_than":
        return actual > expected
    if operator == "less_than":
        return actual < expected
    if operator == "at_least":
        return actual >= expected
    if operator == "at_most":
        return actual <= expected
    return False


def _diagnostic_category(code: str) -> str:
    normalized = code.upper()
    if "ASSERTION" in normalized:
        return "assertion"
    if "LOCATOR" in normalized or "NO_SUCH_ELEMENT" in normalized:
        return "locator"
    if "TIMEOUT" in normalized:
        return "timeout"
    if "SKIPPED" in normalized:
        return "interruption"
    if "UNSUPPORTED" in normalized or "INVALID" in normalized or "UNKNOWN" in normalized:
        return "validation"
    return "runtime"


_SENSITIVE_PATTERN = re.compile(
    r"\b(api[-_\s]?key|access[-_\s]?token|authorization|cookie|password|refresh[-_\s]?token|secret|session|token)\s*[:=]\s*([^&\s,;]+)",
    re.IGNORECASE,
)
