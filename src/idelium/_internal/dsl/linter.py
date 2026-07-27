"""Network-free linter for Idelium DSL v1 sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from idelium._internal.dsl.parser import DslSyntaxError, parse_source


@dataclass(frozen=True)
class DslLintDiagnostic:
    """Stable linter diagnostic with source location and severity."""

    rule_id: str
    severity: str
    message: str
    span: dict[str, Any] | None = None
    remediation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "ruleId": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.span:
            payload["span"] = self.span
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload


def lint_source(source: str, *, source_name: str | None = None) -> dict[str, Any]:
    """Lint a DSL source string without network, browser, or API access."""

    diagnostics: list[DslLintDiagnostic] = []
    try:
        ast = parse_source(source, source_name=source_name)
    except DslSyntaxError as error:
        diagnostic = error.diagnostic
        diagnostics.append(
            DslLintDiagnostic(
                rule_id="IDL-LINT-SYNTAX",
                severity="error",
                message=diagnostic.message,
                span={
                    "start": {
                        "line": diagnostic.line,
                        "column": diagnostic.column,
                    },
                    "end": {
                        "line": diagnostic.line,
                        "column": diagnostic.column,
                    },
                },
                remediation=diagnostic.remediation,
            )
        )
        return _result(source_name, diagnostics)
    diagnostics.extend(_lint_ast(ast))
    return _result(source_name, diagnostics)


def lint_file(source_path: str, report_path: str | None, printer) -> int:
    """Lint a DSL file and optionally write a JSON lint report."""

    try:
        path = Path(source_path).expanduser()
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        printer.danger("Unable to read DSL source for linting: " + str(error))
        raise SystemExit(1) from error
    result = lint_source(source, source_name=path.name)
    if report_path:
        try:
            output_path = Path(report_path).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            printer.danger("Unable to write DSL lint report: " + str(error))
            raise SystemExit(1) from error
    summary = result["summary"]
    printer.success(
        "DSL lint completed with "
        + str(summary["errors"])
        + " error(s) and "
        + str(summary["warnings"])
        + " warning(s)."
    )
    return 2 if summary["errors"] else 0


def _lint_ast(ast: dict[str, Any]) -> list[DslLintDiagnostic]:
    diagnostics: list[DslLintDiagnostic] = []
    defined_steps = {step["name"] for step in ast.get("steps", [])}
    for reusable_step in ast.get("steps", []):
        _lint_statements(reusable_step["statements"], diagnostics, defined_steps)
    for test in ast.get("tests", []):
        statements = test.get("statements", [])
        if not statements:
            diagnostics.append(
                DslLintDiagnostic(
                    rule_id="IDL-LINT-EMPTY-TEST",
                    severity="warning",
                    message="Test has no executable statements.",
                    span=test.get("span"),
                    remediation="Add at least one statement or remove the empty test.",
                )
            )
        _lint_statements(statements, diagnostics, defined_steps)
    return diagnostics


def _lint_statements(
    statements: list[dict[str, Any]],
    diagnostics: list[DslLintDiagnostic],
    defined_steps: set[str],
) -> None:
    for node in statements:
        kind = node.get("kind")
        if kind == "call" and node.get("name") not in defined_steps:
            diagnostics.append(
                DslLintDiagnostic(
                    rule_id="IDL-LINT-UNKNOWN-STEP",
                    severity="error",
                    message="Reusable step call references an undefined step.",
                    span=node.get("span"),
                    remediation="Declare the reusable step before linting or fix the call name.",
                )
            )
        if kind == "open" and node.get("url", "").startswith("http://"):
            diagnostics.append(
                DslLintDiagnostic(
                    rule_id="IDL-LINT-INSECURE-URL",
                    severity="warning",
                    message="Open command uses insecure HTTP.",
                    span=node.get("span"),
                    remediation="Prefer HTTPS URLs for browser tests.",
                )
            )
        if kind == "wait" and "timeoutMilliseconds" not in node:
            diagnostics.append(
                DslLintDiagnostic(
                    rule_id="IDL-LINT-IMPLICIT-WAIT-TIMEOUT",
                    severity="warning",
                    message="Wait statement relies on the runtime default timeout.",
                    span=node.get("span"),
                    remediation="Add an explicit timeout to make CI behavior predictable.",
                )
            )
        if kind in {"if", "repeat"}:
            _lint_statements(node.get("statements", []), diagnostics, defined_steps)


def _result(source_name: str | None, diagnostics: list[DslLintDiagnostic]) -> dict[str, Any]:
    errors = sum(1 for diagnostic in diagnostics if diagnostic.severity == "error")
    warnings = sum(1 for diagnostic in diagnostics if diagnostic.severity == "warning")
    result = {
        "schemaVersion": "dsl-lint-result.v1",
        "status": "failed" if errors else "passed",
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "diagnostics": len(diagnostics),
        },
        "diagnostics": [diagnostic.as_dict() for diagnostic in diagnostics],
    }
    if source_name:
        result["sourceName"] = source_name
    return result
