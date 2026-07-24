"""Offline DSL AST export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from idelium._internal.dsl import DslSyntaxError, parse_source


def export_ast_report(source_path: str, output_path: str, printer) -> None:
    """Parse a DSL source file and write the canonical AST JSON document."""

    try:
        source_file = Path(source_path).expanduser()
        source = source_file.read_text(encoding="utf-8")
    except OSError as error:
        printer.danger("Unable to read DSL source: " + str(error))
        raise SystemExit(1) from error

    try:
        ast = parse_source(source, source_name=source_file.name)
        _validate_ast_contract(ast)
    except DslSyntaxError as error:
        printer.danger(str(error))
        raise SystemExit(1) from error
    except ValueError as error:
        printer.danger(str(error))
        raise SystemExit(1) from error

    try:
        report_path = Path(output_path).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(ast, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        printer.danger("Unable to write DSL AST report: " + str(error))
        raise SystemExit(1) from error

    printer.success("DSL AST report written to " + str(report_path))


def _validate_ast_contract(ast: dict[str, Any]) -> None:
    if ast.get("kind") != "document":
        raise ValueError("DSL AST export failed validation: expected document root.")
    if ast.get("schemaVersion") != "1.0":
        raise ValueError("Unsupported DSL AST schema version. Use schema 1.0.")
    if ast.get("languageVersion") != "1.0":
        raise ValueError("Unsupported DSL language version. Use idelium 1.0.")
    tests = ast.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("DSL AST export failed validation: at least one test is required.")
