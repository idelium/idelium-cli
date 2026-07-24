"""Canonical local execution report export for Idelium CLI."""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from idelium._internal.bidi import redact_bidi_value


REPORT_SCHEMA_VERSION = "1.0"
MAX_FIELD_LENGTH = 4096
MAX_ARTIFACTS_PER_STEP = 20
MAX_ARTIFACT_DATA_LIST_ITEMS = 100
_SENSITIVE_KEYS = (
    "authorization",
    "cookie",
    "key",
    "password",
    "secret",
    "session",
    "token",
)


def build_execution_report(
    events: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    """Build the canonical report used by JSON and HTML exporters."""

    normalized_events = [_normalize_event(event) for event in events]
    total_steps = sum(len(event["steps"]) for event in normalized_events)
    failed_steps = sum(
        1
        for event in normalized_events
        for step in event["steps"]
        if step["status"] == "failed"
    )
    skipped_steps = sum(
        1
        for event in normalized_events
        for step in event["steps"]
        if step["status"] == "skipped"
    )
    passed_steps = total_steps - failed_steps - skipped_steps
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run": {
            "status": "passed" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "projectId": _safe_string(config.get("idProject")),
            "cycleId": _safe_string(config.get("idCycle")),
            "environment": _safe_string(config.get("environment")),
            "reportingService": _safe_string(config.get("reportingService")),
        },
        "summary": {
            "tests": len(normalized_events),
            "steps": total_steps,
            "passed": passed_steps,
            "failed": failed_steps,
            "skipped": skipped_steps,
        },
        "tests": normalized_events,
    }


def write_json_report(report: dict[str, Any], path: str | Path) -> None:
    """Write a deterministic JSON report document."""

    report_path = _prepare_output_path(path)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_html_report(report: dict[str, Any], path: str | Path) -> None:
    """Write a self-contained HTML report with escaped untrusted content."""

    report_path = _prepare_output_path(path)
    report_path.write_text(render_html_report(report), encoding="utf-8")


def write_junit_report(report: dict[str, Any], path: str | Path) -> None:
    """Write a JUnit XML report suitable for CI test result consumers."""

    report_path = _prepare_output_path(path)
    report_path.write_text(render_junit_report(report), encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: str | Path) -> None:
    """Write a deterministic Markdown execution report."""

    report_path = _prepare_output_path(path)
    report_path.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render the canonical report as escaped Markdown for review artifacts."""

    run = report.get("run", {})
    summary = report.get("summary", {})
    lines = [
        "# Idelium Execution Report",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Status | {_markdown_cell(run.get('status'))} |",
        f"| Project | {_markdown_cell(run.get('projectId'))} |",
        f"| Cycle | {_markdown_cell(run.get('cycleId'))} |",
        f"| Environment | {_markdown_cell(run.get('environment'))} |",
        f"| Generated at | {_markdown_cell(report.get('generatedAt'))} |",
        "",
        "## Summary",
        "",
        "| Tests | Steps | Passed | Failed | Skipped |",
        "| ---: | ---: | ---: | ---: | ---: |",
        "| {} | {} | {} | {} | {} |".format(
            int(summary.get("tests", 0)),
            int(summary.get("steps", 0)),
            int(summary.get("passed", 0)),
            int(summary.get("failed", 0)),
            int(summary.get("skipped", 0)),
        ),
        "",
        "## Steps",
        "",
        "| Test | Step | Status | Duration ms | Diagnostics | Artifacts |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    rows = 0
    for test in report.get("tests", []):
        for step in test.get("steps", []):
            rows += 1
            diagnostics = "<br>".join(
                _markdown_cell(diagnostic.get("message", ""))
                for diagnostic in step.get("diagnostics", [])
            )
            artifacts = "<br>".join(
                _markdown_cell(artifact.get("path") or artifact.get("name", "artifact"))
                for artifact in step.get("artifacts", [])
            )
            lines.append(
                "| {} | {} | {} | {} | {} | {} |".format(
                    _markdown_cell(test.get("name")),
                    _markdown_cell(step.get("name")),
                    _markdown_cell(step.get("status")),
                    int(step.get("durationMilliseconds", 0)),
                    diagnostics or "—",
                    artifacts or "—",
                )
            )
    if rows == 0:
        lines.append("| — | — | skipped | 0 | No steps were recorded. | — |")
    lines.append("")
    return "\n".join(lines)


def render_junit_report(report: dict[str, Any]) -> str:
    """Render the canonical execution report as JUnit XML."""

    summary = report.get("summary", {})
    tests = report.get("tests", [])
    root = ET.Element(
        "testsuites",
        {
            "name": "Idelium",
            "tests": str(int(summary.get("steps", 0))),
            "failures": str(int(summary.get("failed", 0))),
            "skipped": str(int(summary.get("skipped", 0))),
            "time": _seconds(sum(_test_duration(test) for test in tests)),
        },
    )
    for test in tests:
        steps = test.get("steps", [])
        suite = ET.SubElement(
            root,
            "testsuite",
            {
                "name": _safe_string(test.get("name") or "Idelium test"),
                "tests": str(len(steps)),
                "failures": str(
                    sum(1 for step in steps if step.get("status") == "failed")
                ),
                "skipped": str(
                    sum(1 for step in steps if step.get("status") == "skipped")
                ),
                "time": _seconds(_test_duration(test)),
            },
        )
        for step in steps:
            diagnostics = _step_diagnostics_text(step)
            case = ET.SubElement(
                suite,
                "testcase",
                {
                    "classname": _safe_string(test.get("name") or "Idelium test"),
                    "name": _safe_string(step.get("name") or "Idelium step"),
                    "time": _seconds(int(step.get("durationMilliseconds", 0))),
                },
            )
            if step.get("status") == "failed":
                failure = ET.SubElement(
                    case,
                    "failure",
                    {
                        "message": diagnostics or "Step failed.",
                        "type": _safe_string(step.get("type") or "idelium.step"),
                    },
                )
                failure.text = diagnostics or "Step failed."
            elif step.get("status") == "skipped":
                skipped = ET.SubElement(
                    case,
                    "skipped",
                    {"message": diagnostics or "Step skipped."},
                )
                skipped.text = diagnostics or "Step skipped."
            if diagnostics:
                system_out = ET.SubElement(case, "system-out")
                system_out.text = diagnostics
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def render_html_report(report: dict[str, Any]) -> str:
    """Render the canonical report into a compact self-contained HTML document."""

    rows = []
    for test in report.get("tests", []):
        for step in test.get("steps", []):
            diagnostics = "<br>".join(
                _escape(diagnostic.get("message", ""))
                for diagnostic in step.get("diagnostics", [])
            )
            artifacts = "<br>".join(
                _escape(artifact.get("name", "artifact"))
                for artifact in step.get("artifacts", [])
            )
            rows.append(
                "<tr>"
                f"<td>{_escape(test.get('name'))}</td>"
                f"<td>{_escape(step.get('name'))}</td>"
                f'<td><span class="status {step.get("status")}">{_escape(step.get("status"))}</span></td>'
                f"<td>{int(step.get('durationMilliseconds', 0))}</td>"
                f"<td>{diagnostics or '&mdash;'}</td>"
                f"<td>{artifacts or '&mdash;'}</td>"
                "</tr>"
            )
    rows_html = "\n".join(rows) or (
        '<tr><td colspan="6" class="empty">No steps were recorded.</td></tr>'
    )
    summary = report.get("summary", {})
    run = report.get("run", {})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Idelium Execution Report</title>
  <style>
    body {{ background: #111827; color: #e5e7eb; font-family: Arial, sans-serif; margin: 0; padding: 32px; }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .meta, .empty {{ color: #9ca3af; }}
    .cards {{ display: grid; gap: 12px; grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 24px 0; }}
    .card {{ border: 1px solid #374151; border-radius: 8px; padding: 14px; background: #1f2937; }}
    .card strong {{ display: block; font-size: 22px; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: #1f2937; border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #374151; padding: 12px; text-align: left; vertical-align: top; }}
    th {{ color: #d1d5db; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    .status {{ border-radius: 999px; padding: 4px 8px; font-size: 12px; font-weight: bold; }}
    .passed {{ background: #065f46; color: #d1fae5; }}
    .failed {{ background: #7f1d1d; color: #fee2e2; }}
    .skipped {{ background: #374151; color: #e5e7eb; }}
  </style>
</head>
<body>
<main>
  <h1>Idelium Execution Report</h1>
  <div class="meta">Generated at {_escape(report.get("generatedAt"))} for project {_escape(run.get("projectId"))}, cycle {_escape(run.get("cycleId"))}, environment {_escape(run.get("environment"))}.</div>
  <section class="cards" aria-label="Run summary">
    <div class="card">Status<strong>{_escape(run.get("status"))}</strong></div>
    <div class="card">Tests<strong>{int(summary.get("tests", 0))}</strong></div>
    <div class="card">Passed<strong>{int(summary.get("passed", 0))}</strong></div>
    <div class="card">Failed<strong>{int(summary.get("failed", 0))}</strong></div>
    <div class="card">Skipped<strong>{int(summary.get("skipped", 0))}</strong></div>
  </section>
  <table>
    <thead>
      <tr><th>Test</th><th>Step</th><th>Status</th><th>Duration ms</th><th>Diagnostics</th><th>Artifacts</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</main>
</body>
</html>
"""


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _safe_string(event.get("id")),
        "name": _safe_string(event.get("name")),
        "description": _safe_string(event.get("description")),
        "steps": [_normalize_step(step) for step in event.get("steps", [])],
    }


def _normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    postman_results = step.get("postmanResults") or []
    diagnostics = list(step.get("diagnostics") or [])
    diagnostics.extend(_postman_diagnostics(postman_results))
    return {
        "id": _safe_string(step.get("id")),
        "name": _safe_string(step.get("name")),
        "type": _safe_string(step.get("type")),
        "status": _normalize_status(step.get("status")),
        "durationMilliseconds": max(0, int(step.get("durationMilliseconds") or 0)),
        "diagnostics": [
            _normalize_diagnostic(diagnostic) for diagnostic in diagnostics
        ],
        "artifacts": [
            _normalize_artifact(artifact)
            for artifact in (step.get("artifacts") or [])[:MAX_ARTIFACTS_PER_STEP]
        ],
        "postmanResults": [_normalize_postman(result) for result in postman_results],
    }


def _postman_diagnostics(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    diagnostics = []
    for result in results:
        for assertion in result.get("assertions", []) or []:
            if assertion.get("passed") is False:
                diagnostics.append(
                    {
                        "level": "error",
                        "message": assertion.get("message")
                        or assertion.get("name")
                        or "Postman assertion failed.",
                    }
                )
    return diagnostics


def _normalize_postman(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _safe_string(result.get("name")),
        "method": _safe_string(result.get("method")),
        "url": _redact_url(result.get("url", "")),
        "status": _safe_string(result.get("status")),
        "passed": bool(result.get("passed")),
        "timeMilliseconds": max(0, int(result.get("time") or 0)),
        "assertions": [
            {
                "name": _safe_string(assertion.get("name")),
                "passed": bool(assertion.get("passed")),
                "message": _safe_string(assertion.get("message")),
            }
            for assertion in result.get("assertions", [])
        ],
    }


def _normalize_diagnostic(diagnostic: dict[str, Any]) -> dict[str, str]:
    return {
        "level": _safe_string(diagnostic.get("level") or "error"),
        "message": _safe_string(diagnostic.get("message")),
    }


def _normalize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "name": _safe_string(artifact.get("name") or "artifact"),
        "type": _safe_string(artifact.get("type") or "unknown"),
        "path": _safe_string(artifact.get("path")),
    }
    if "data" in artifact:
        normalized["data"] = _limit_artifact_data(redact_bidi_value(artifact["data"]))
    return normalized


def _normalize_status(status: Any) -> str:
    if str(status) == "1" or status == "passed":
        return "passed"
    if str(status) == "5" or status == "skipped":
        return "skipped"
    return "failed"


def _safe_string(value: Any) -> str:
    text = "" if value is None else str(value)
    for key in _SENSITIVE_KEYS:
        text = re.sub(
            rf"(?i)({re.escape(key)})(\s*[:=]\s*|\s+)([^\s,;&]+)",
            r"\1\2[REDACTED]",
            text,
        )
    return text[:MAX_FIELD_LENGTH]


def _limit_artifact_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key)[:MAX_FIELD_LENGTH]: _limit_artifact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _limit_artifact_data(item) for item in value[:MAX_ARTIFACT_DATA_LIST_ITEMS]
        ]
    return _safe_string(value)


def _redact_url(value: Any) -> str:
    text = _safe_string(value)
    if "?" not in text:
        return text
    base, query = text.split("?", 1)
    safe_parts = []
    for part in query.split("&"):
        key = part.split("=", 1)[0]
        if any(sensitive in key.lower() for sensitive in _SENSITIVE_KEYS):
            safe_parts.append(key + "=[REDACTED]")
        else:
            safe_parts.append(part[:MAX_FIELD_LENGTH])
    return base + "?" + "&".join(safe_parts)


def _prepare_output_path(path: str | Path) -> Path:
    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return report_path


def _test_duration(test: dict[str, Any]) -> int:
    return sum(
        int(step.get("durationMilliseconds") or 0) for step in test.get("steps", [])
    )


def _seconds(milliseconds: int) -> str:
    return f"{max(0, milliseconds) / 1000:.3f}"


def _step_diagnostics_text(step: dict[str, Any]) -> str:
    diagnostics = [
        diagnostic.get("message", "")
        for diagnostic in step.get("diagnostics", [])
        if diagnostic.get("message")
    ]
    return "\n".join(_safe_string(message) for message in diagnostics)


def _markdown_cell(value: Any) -> str:
    text = _safe_string(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return text or "—"


def _escape(value: Any) -> str:
    return html.escape(_safe_string(value), quote=True)
