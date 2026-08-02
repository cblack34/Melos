"""Storage adapters and redaction for immutable local composition experiments."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from melos.domain.provenance import (
    DuplicateExperimentRunError,
    ExperimentRun,
)

_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer_token",
    }
)
_REDACTED = "[REDACTED]"


class EvidenceRedactor:
    """Remove configured secrets and secret-bearing fields from persisted evidence."""

    def __init__(self, configured_secrets: Iterable[str] = ()) -> None:
        self._configured_secrets = tuple(
            secret for secret in configured_secrets if secret
        )

    def redact(self, value: Any) -> Any:
        """Return JSON-compatible evidence with secrets replaced recursively."""
        if isinstance(value, dict):
            return {
                str(key): (
                    _REDACTED if self._is_secret_key(str(key)) else self.redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list | tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            result = value
            for secret in self._configured_secrets:
                result = result.replace(secret, _REDACTED)
            return result
        return value

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        normalized = key.casefold().replace("-", "_")
        return (
            normalized in _SECRET_FIELD_NAMES
            or normalized.endswith("_api_key")
            or normalized.endswith("_secret")
        )


class InMemoryExperimentRepository:
    """Small deterministic repository for unit tests and local adapter defaults."""

    def __init__(self) -> None:
        self._runs: dict[str, ExperimentRun] = {}

    def save(self, run: ExperimentRun) -> None:
        if run.run_id in self._runs:
            raise DuplicateExperimentRunError(
                f"experiment run already exists: {run.run_id}"
            )
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> ExperimentRun | None:
        return self._runs.get(run_id)

    def list_group(self, experiment_group_id: str) -> tuple[ExperimentRun, ...]:
        return tuple(
            sorted(
                (
                    run
                    for run in self._runs.values()
                    if run.experiment_group_id == experiment_group_id
                ),
                key=lambda run: (run.started_at, run.run_id),
            )
        )


class JsonExperimentRepository:
    """Append-only, per-run JSON storage with exclusive file creation."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, run: ExperimentRun) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(run.run_id)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(
                    run.model_dump(mode="json"),
                    stream,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
        except FileExistsError as error:
            raise DuplicateExperimentRunError(
                f"experiment run already exists: {run.run_id}"
            ) from error

    def get(self, run_id: str) -> ExperimentRun | None:
        path = self._path_for(run_id)
        if not path.is_file():
            return None
        return ExperimentRun.model_validate_json(path.read_text(encoding="utf-8"))

    def list_group(self, experiment_group_id: str) -> tuple[ExperimentRun, ...]:
        if not self._root.is_dir():
            return ()
        runs = [
            ExperimentRun.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self._root.glob("*.json")
        ]
        return tuple(
            sorted(
                (run for run in runs if run.experiment_group_id == experiment_group_id),
                key=lambda run: (run.started_at, run.run_id),
            )
        )

    def _path_for(self, run_id: str) -> Path:
        if not run_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "run_id must contain only letters, numbers, hyphens, or underscores"
            )
        return self._root / f"{run_id}.json"
