"""Validated parameter resolution for Idelium DSL runtime variables."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DslParameterError(ValueError):
    """Raised when DSL parameters cannot be resolved safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DslResolvedParameters:
    """Runtime-safe DSL parameter maps."""

    variables: dict[str, str]
    secret_names: set[str]

    def as_config(self) -> dict[str, Any]:
        """Return the runtime parameter config with explicit secret metadata."""

        return {
            "variables": self.variables,
            "secretNames": sorted(self.secret_names),
        }


def resolve_dsl_parameters(
    *,
    parameter_file: str | None = None,
    cli_parameters: list[str] | None = None,
    cli_secret_parameters: list[str] | None = None,
) -> DslResolvedParameters:
    """Resolve DSL runtime variables with precedence file < CLI."""

    variables: dict[str, str] = {}
    secret_names: set[str] = set()
    if parameter_file:
        file_variables, file_secret_names = _read_parameter_file(parameter_file)
        variables.update(file_variables)
        secret_names.update(file_secret_names)
    for item in cli_parameters or []:
        name, value = _parse_assignment(item)
        variables[name] = value
        secret_names.discard(name)
    for item in cli_secret_parameters or []:
        name, value = _parse_assignment(item)
        variables[name] = value
        secret_names.add(name)
    return DslResolvedParameters(variables=variables, secret_names=secret_names)


def _read_parameter_file(path: str) -> tuple[dict[str, str], set[str]]:
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as error:
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETERS_FILE_ERROR",
            "Unable to read DSL parameter file.",
        ) from error
    except json.JSONDecodeError as error:
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETERS_MALFORMED_JSON",
            "DSL parameter file must be valid JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETERS_INVALID_SHAPE",
            "DSL parameter file must contain a JSON object.",
        )
    variables: dict[str, str] = {}
    secret_names: set[str] = set()
    for section_name, secret in (("variables", False), ("secrets", True)):
        section = payload.get(section_name, {})
        if section is None:
            section = {}
        if not isinstance(section, dict):
            raise DslParameterError(
                "IDELIUM_DSL_PARAMETERS_INVALID_SHAPE",
                f"DSL parameter file field {section_name} must be an object.",
            )
        for name, value in section.items():
            _validate_name(name)
            _validate_value(value)
            variables[name] = str(value)
            if secret:
                secret_names.add(name)
            else:
                secret_names.discard(name)
    return variables, secret_names


def _parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETER_ASSIGNMENT_INVALID",
            "DSL parameters must use name=value syntax.",
        )
    name, parameter_value = value.split("=", 1)
    _validate_name(name)
    _validate_value(parameter_value)
    return name, parameter_value


def _validate_name(name: Any) -> None:
    if not isinstance(name, str) or not _PARAMETER_NAME_RE.fullmatch(name):
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETER_NAME_INVALID",
            "DSL parameter names must start with a letter or underscore and contain only letters, numbers, or underscore.",
        )


def _validate_value(value: Any) -> None:
    if not isinstance(value, str):
        raise DslParameterError(
            "IDELIUM_DSL_PARAMETER_VALUE_INVALID",
            "DSL parameter values must be strings.",
        )
