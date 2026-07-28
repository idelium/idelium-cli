"""Subprocess execution boundary for approved Idelium CLI plugins."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from idelium._internal.commons.resultenum import Result
from idelium._internal.pluginapi import PluginDefinition, redact_plugin_error


class PluginExecutionError(RuntimeError):
    """Raised when a plugin cannot complete inside the subprocess boundary."""


def execute_plugin_in_subprocess(
    definition: PluginDefinition,
    json_config: dict[str, Any],
    params: Any,
) -> Result:
    """Execute an approved plugin with finite timeout and redacted environment."""

    if not definition.approved_for_execution():
        raise PluginExecutionError(
            "Plugin is not approved for subprocess execution or failed integrity checks."
        )

    with tempfile.TemporaryDirectory(prefix="idelium-plugin-") as tmpdir:
        plugin_path = Path(tmpdir) / f"{definition.name}.py"
        plugin_path.write_text(definition.source, encoding="utf-8")
        request = {
            "pluginPath": str(plugin_path),
            "entrypoint": definition.entrypoint,
            "jsonConfig": json_config,
            "params": params,
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "idelium._internal.pluginrunner_child"],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=definition.timeout_seconds,
                env=_safe_environment(),
                cwd=tmpdir,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise PluginExecutionError("Plugin execution timed out.") from error

    if completed.returncode != 0:
        raise PluginExecutionError(redact_plugin_error(RuntimeError(completed.stderr)))

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as error:
        raise PluginExecutionError("Plugin returned invalid execution output.") from error

    status = payload.get("result")
    if status == "OK":
        return Result.OK
    if status == "KO":
        return Result.KO
    if status == "NA":
        return Result.NA
    raise PluginExecutionError("Plugin returned an unsupported result value.")


def _safe_environment() -> dict[str, str]:
    safe: dict[str, str] = {}
    for key in ("PATH", "PYTHONPATH", "PYTHONHOME", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            safe[key] = value
    package_root = str(Path(__file__).resolve().parents[2])
    safe["PYTHONPATH"] = (
        package_root
        if "PYTHONPATH" not in safe
        else package_root + os.pathsep + safe["PYTHONPATH"]
    )
    safe["IDELIUM_PLUGIN_SANDBOX"] = "1"
    return safe
