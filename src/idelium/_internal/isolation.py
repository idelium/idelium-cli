"""Runtime isolation helpers for independent Idelium executions."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ISOLATION_CONTRACT_VERSION = "idelium-runtime-isolation.v1"


@dataclass
class IsolatedExecutionContext:
    """Own the mutable state for one execution worker."""

    tenant_id: str
    worker_id: str
    base_directory: Path | None = None
    source_config: dict[str, Any] | None = None
    keep_artifacts: bool = False
    directory: Path | None = None
    artifact_directory: Path | None = None
    config: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    cleanup_errors: list[str] = field(default_factory=list)

    def __enter__(self) -> "IsolatedExecutionContext":
        base = self.base_directory
        if base is not None:
            base.mkdir(parents=True, exist_ok=True)
        directory = Path(
            tempfile.mkdtemp(
                prefix="idelium-worker-",
                dir=str(base) if base is not None else None,
            )
        )
        artifact_directory = directory / "artifacts"
        artifact_directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.artifact_directory = artifact_directory
        self.config = dict(self.source_config or {})
        self.config.update(
            {
                "dir_idelium_scripts": str(directory),
                "artifactDirectory": str(artifact_directory),
                "workerId": self.worker_id,
                "tenantId": self.tenant_id,
            }
        )
        self.state = {
            "driver": None,
            "postmanResults": [],
            "artifacts": [],
            "diagnostics": [],
        }
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.cleanup()
        return False

    def cleanup(self) -> None:
        """Remove private temporary state without changing execution outcome."""

        if self.keep_artifacts or self.directory is None:
            return
        try:
            shutil.rmtree(self.directory)
        except OSError as error:
            self.cleanup_errors.append(str(error))

    def metadata(self) -> dict[str, Any]:
        """Return non-secret context metadata safe for execution reports."""

        return {
            "schemaVersion": ISOLATION_CONTRACT_VERSION,
            "tenantId": self.tenant_id,
            "workerId": self.worker_id,
            "temporaryDirectory": str(self.directory or ""),
            "artifactDirectory": str(self.artifact_directory or ""),
            "cleanupErrors": list(self.cleanup_errors),
        }
