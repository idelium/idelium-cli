"""Versioned contract for Idelium CLI Python plugins."""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from typing import Any


SUPPORTED_PLUGIN_API_VERSION = "idelium-plugin/1.0"
ENTERPRISE_PLUGIN_API_VERSION = "idelium-plugin/1.1"
LEGACY_PLUGIN_API_VERSION = "idelium-plugin-legacy/1"
PLUGIN_STEP_CAPABILITY = "browser.step"
SUPPORTED_PLUGIN_CAPABILITIES = frozenset({PLUGIN_STEP_CAPABILITY})
APPROVED_PLUGIN_STATUS = "approved"
SUBPROCESS_EXECUTION_MODE = "subprocess"
IN_PROCESS_EXECUTION_MODE = "in-process"

_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_KEYS = (
    "authorization",
    "cookie",
    "key",
    "password",
    "secret",
    "session",
    "token",
)


@dataclass(frozen=True)
class PluginDefinition:
    """Validated plugin metadata used by the dispatch boundary."""

    name: str
    api_version: str
    capabilities: tuple[str, ...]
    entrypoint: str
    source: str
    legacy: bool = False
    approval_status: str = "legacy"
    source_sha256: str | None = None
    provenance: dict[str, Any] | None = None
    execution_mode: str = IN_PROCESS_EXECUTION_MODE
    timeout_seconds: int = 10

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "apiVersion": self.api_version,
            "capabilities": list(self.capabilities),
            "entrypoint": self.entrypoint,
            "source": self.source,
            "legacy": self.legacy,
            "approvalStatus": self.approval_status,
            "sourceSha256": self.source_sha256,
            "provenance": self.provenance or {},
            "executionMode": self.execution_mode,
            "timeoutSeconds": self.timeout_seconds,
        }

    def approved_for_execution(self) -> bool:
        return (
            self.api_version == ENTERPRISE_PLUGIN_API_VERSION
            and self.approval_status == APPROVED_PLUGIN_STATUS
            and self.source_sha256 == source_hash(self.source)
            and self.execution_mode == SUBPROCESS_EXECUTION_MODE
        )


class PluginContractError(ValueError):
    """Raised when plugin metadata violates the constrained API contract."""


class PluginRegistry:
    """Capability-aware plugin lookup for runtime dispatch."""

    def __init__(self, definitions: dict[str, PluginDefinition]):
        self._definitions = definitions

    @classmethod
    def from_config(cls, plugins: dict[str, Any] | None) -> "PluginRegistry":
        definitions = {}
        for name, payload in (plugins or {}).items():
            definition = normalize_plugin_payload(name, payload)
            definitions[definition.name] = definition
        return cls(definitions)

    def get_step_plugin(self, name: str) -> PluginDefinition | None:
        definition = self._definitions.get(name)
        if definition and definition.supports(PLUGIN_STEP_CAPABILITY):
            return definition
        return None


def normalize_plugin_payload(name: str, payload: Any) -> PluginDefinition:
    """Validate and normalize an API plugin payload into a stable definition."""

    _validate_plugin_name(name)
    decoded = _decode_payload(payload)
    if isinstance(decoded, list):
        if not decoded or not isinstance(decoded[0], str):
            raise PluginContractError("Legacy plugin payload must contain source code.")
        return PluginDefinition(
            name=name,
            api_version=LEGACY_PLUGIN_API_VERSION,
            capabilities=(PLUGIN_STEP_CAPABILITY,),
            entrypoint="init",
            source=decoded[0],
            legacy=True,
        )

    if not isinstance(decoded, dict):
        raise PluginContractError("Plugin payload must be a JSON object or legacy list.")

    api_version = decoded.get("apiVersion")
    if api_version not in {SUPPORTED_PLUGIN_API_VERSION, ENTERPRISE_PLUGIN_API_VERSION}:
        raise PluginContractError(
            "Unsupported plugin API version. Use idelium-plugin/1.1."
        )

    capabilities = decoded.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise PluginContractError("Plugin capabilities must be a non-empty list.")
    normalized_capabilities = tuple(str(capability) for capability in capabilities)
    unsupported = sorted(set(normalized_capabilities) - SUPPORTED_PLUGIN_CAPABILITIES)
    if unsupported:
        raise PluginContractError(
            "Unsupported plugin capabilities: " + ", ".join(unsupported)
        )

    entrypoint = decoded.get("entrypoint", "init")
    if not isinstance(entrypoint, str) or not _ENTRYPOINT_RE.fullmatch(entrypoint):
        raise PluginContractError("Plugin entrypoint must be a valid Python identifier.")

    source = decoded.get("source")
    if not isinstance(source, str) or not source.strip():
        raise PluginContractError("Plugin source must be a non-empty string.")

    approval_status = str(decoded.get("approvalStatus", "unapproved"))
    source_sha256 = decoded.get("sourceSha256")
    execution_mode = str(decoded.get("executionMode", IN_PROCESS_EXECUTION_MODE))
    timeout_seconds = int(decoded.get("timeoutSeconds", 10))
    provenance = decoded.get("provenance", {})

    if api_version == ENTERPRISE_PLUGIN_API_VERSION:
        if approval_status != APPROVED_PLUGIN_STATUS:
            raise PluginContractError("Plugin approval status must be approved.")
        if source_sha256 != source_hash(source):
            raise PluginContractError("Plugin source hash does not match the manifest.")
        if execution_mode != SUBPROCESS_EXECUTION_MODE:
            raise PluginContractError(
                "Enterprise plugins must use subprocess execution mode."
            )
        if timeout_seconds < 1 or timeout_seconds > 60:
            raise PluginContractError("Plugin timeout must be between 1 and 60 seconds.")
        if not isinstance(provenance, dict) or not provenance.get("reviewedBy"):
            raise PluginContractError("Plugin provenance must include reviewedBy.")

    return PluginDefinition(
        name=name,
        api_version=api_version,
        capabilities=normalized_capabilities,
        entrypoint=entrypoint,
        source=source,
        approval_status=approval_status,
        source_sha256=source_sha256,
        provenance=provenance if isinstance(provenance, dict) else {},
        execution_mode=execution_mode,
        timeout_seconds=timeout_seconds,
    )


def redact_plugin_error(error: Exception) -> str:
    """Return a plugin error message with common credential fragments redacted."""

    message = str(error) or error.__class__.__name__
    redacted_parts = []
    redact_next = False
    for part in message.split():
        lowered = part.lower()
        if redact_next:
            redacted_parts.append("[REDACTED]")
            redact_next = False
        elif any(key in lowered for key in _SENSITIVE_KEYS):
            redacted_parts.append("[REDACTED]")
            if "=" not in part and ":" not in part:
                redact_next = True
        else:
            redacted_parts.append(part)
    return " ".join(redacted_parts)


def _decode_payload(payload: Any) -> Any:
    if isinstance(payload, PluginDefinition):
        return payload.as_config()
    if isinstance(payload, dict | list):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise PluginContractError("Plugin payload must be valid JSON.") from error
    raise PluginContractError("Unsupported plugin payload type.")


def source_hash(source: str) -> str:
    """Return the stable SHA-256 digest used by approved plugin manifests."""

    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _validate_plugin_name(name: str) -> None:
    if not isinstance(name, str) or not _PLUGIN_NAME_RE.fullmatch(name):
        raise PluginContractError(
            "Plugin name must be a safe Python module identifier."
        )
