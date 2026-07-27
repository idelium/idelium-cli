"""Validated multi-environment configuration resolution."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any


ENVIRONMENT_CONTRACT_VERSION = "idelium-environment-resolution.v1"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
}


class EnvironmentResolutionError(ValueError):
    """Raised when an environment cannot be resolved safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_diagnostic(self) -> dict[str, str]:
        """Return a redacted diagnostic payload."""

        return {"code": self.code, "message": _redact_text(self.message)}


@dataclass(frozen=True)
class ResolvedEnvironment:
    """Resolved environment configuration and non-secret provenance metadata."""

    name: str
    config: dict[str, Any]
    provenance: tuple[str, ...]
    diagnostics: tuple[dict[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return stable JSON-compatible resolution metadata."""

        return {
            "schemaVersion": ENVIRONMENT_CONTRACT_VERSION,
            "name": self.name,
            "provenance": list(self.provenance),
            "diagnostics": [dict(diagnostic) for diagnostic in self.diagnostics],
        }


def resolve_environment(
    environments: dict[str, dict[str, Any]],
    selected: str,
    *,
    project_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResolvedEnvironment:
    """Resolve environment inheritance and CLI overrides deterministically."""

    if selected not in environments:
        raise EnvironmentResolutionError(
            "IDELIUM_ENVIRONMENT_NOT_FOUND",
            f'Environment "{selected}" does not exist for project {project_id}.',
        )
    resolved, provenance = _resolve_chain(
        environments,
        selected,
        project_id=project_id,
        seen=(),
    )
    applied_overrides = {
        key: value
        for key, value in (overrides or {}).items()
        if value is not None
    }
    if applied_overrides:
        resolved.update(copy.deepcopy(applied_overrides))
        provenance = (*provenance, "cli-overrides")
    diagnostics = tuple(_sensitive_key_diagnostics(resolved))
    return ResolvedEnvironment(selected, resolved, provenance, diagnostics)


def _resolve_chain(
    environments: dict[str, dict[str, Any]],
    name: str,
    *,
    project_id: str | None,
    seen: tuple[str, ...],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    if name in seen:
        raise EnvironmentResolutionError(
            "IDELIUM_ENVIRONMENT_INHERITANCE_CYCLE",
            "Environment inheritance contains a cycle.",
        )
    environment = environments.get(name)
    if not isinstance(environment, dict):
        raise EnvironmentResolutionError(
            "IDELIUM_ENVIRONMENT_INVALID",
            f'Environment "{name}" must be an object.',
        )
    _validate_project(name, environment, project_id)
    parent_name = environment.get("extends")
    if parent_name is None:
        base: dict[str, Any] = {}
        provenance: tuple[str, ...] = ()
    else:
        if not isinstance(parent_name, str) or parent_name not in environments:
            raise EnvironmentResolutionError(
                "IDELIUM_ENVIRONMENT_PARENT_NOT_FOUND",
                f'Environment "{name}" extends an unknown environment.',
            )
        base, provenance = _resolve_chain(
            environments,
            parent_name,
            project_id=project_id,
            seen=(*seen, name),
        )
    merged = copy.deepcopy(base)
    merged.update(
        {
            key: copy.deepcopy(value)
            for key, value in environment.items()
            if key != "extends"
        }
    )
    return merged, (*provenance, name)


def _validate_project(
    name: str,
    environment: dict[str, Any],
    project_id: str | None,
) -> None:
    environment_project = environment.get("projectId")
    if (
        project_id is not None
        and environment_project is not None
        and str(environment_project) != str(project_id)
    ):
        raise EnvironmentResolutionError(
            "IDELIUM_ENVIRONMENT_PROJECT_MISMATCH",
            f'Environment "{name}" belongs to a different project.',
        )


def _sensitive_key_diagnostics(config: dict[str, Any]) -> list[dict[str, str]]:
    diagnostics = []
    for key in _walk_keys(config):
        if _is_sensitive_key(key):
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "IDELIUM_ENVIRONMENT_SECRET_REFERENCE",
                    "message": (
                        "Environment contains a sensitive-looking key; keep the "
                        "secret value in an external secret store."
                    ),
                }
            )
    return diagnostics


def _walk_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
        return keys
    if isinstance(value, list):
        keys = []
        for item in value:
            keys.extend(_walk_keys(item))
        return keys
    return []


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEYS)


def _redact_text(value: str) -> str:
    return re.sub(
        r"(?i)(api[-_\s]?key|authorization|cookie|password|secret|session|token)"
        r"(\s*[:=]\s*|\s+)([^\s,;&]+)",
        r"\1\2[REDACTED]",
        value,
    )
