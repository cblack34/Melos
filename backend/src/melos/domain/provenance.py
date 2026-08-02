"""Immutable experiment evidence and the repository port for composition runs."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from melos.domain.composition import (
    RawUserContent,
    RequestedInstrumentConstraints,
    ResolvedCompositionConstraints,
)
from melos.domain.lyrics import SongSource
from melos.domain.music import KeyName
from melos.domain.semantic import Meter, RealizationIdentity, SemanticScore


class ProvenanceModel(BaseModel):
    """Closed, frozen records: a saved run is historical evidence, never state."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RequestedMeta(ProvenanceModel):
    """Meta exactly as the user supplied it, before missing values were resolved."""

    tempo_bpm: float | None = Field(default=None, ge=20, le=400)
    key: KeyName | None = None
    meter: Meter | None = None


class InjectedInstructionEvidence(ProvenanceModel):
    """Version and content identity for a non-user prompt component."""

    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidationFailure(ProvenanceModel):
    """One rejected output, including the feedback Pydantic AI used for retry."""

    retry_index: int = Field(ge=0)
    message: str = Field(min_length=1)


class ErrorEvidence(ProvenanceModel):
    """A terminal exception represented without retaining traceback locals."""

    type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ModelIdentity(ProvenanceModel):
    """The effective Pydantic AI model selection and settings for a run."""

    provider: str | None = None
    model: str | None = None
    settings_json: str


class UsageEvidence(ProvenanceModel):
    """Normalized request or aggregate Pydantic AI usage."""

    requests: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    details_json: str


class ModelResponseEvidence(ProvenanceModel):
    """One normalized Pydantic AI response, serialized after redaction."""

    response_json: str
    provider_response_id: str | None = None
    provider: str | None = None
    model: str | None = None
    effective_model: ModelIdentity
    usage: UsageEvidence


class ModelRequestEvidence(ProvenanceModel):
    """Effective Pydantic AI request configuration for one model turn."""

    effective_model: ModelIdentity
    parameters_json: str


class ExperimentRun(ProvenanceModel):
    """All available evidence for exactly one successful or failed composition run."""

    experiment_group_id: str = Field(min_length=1, max_length=96)
    run_id: str = Field(min_length=1, max_length=96)
    parent_revision_id: str | None = Field(default=None, max_length=96)
    started_at: datetime
    finished_at: datetime
    elapsed_seconds: float = Field(ge=0)
    raw_user_content: RawUserContent
    requested_meta: RequestedMeta
    resolved_constraints: ResolvedCompositionConstraints
    requested_instruments: RequestedInstrumentConstraints
    source: SongSource
    injected_instructions: tuple[InjectedInstructionEvidence, ...]
    pydantic_ai_version: str = Field(min_length=1, max_length=80)
    final_messages_json: str
    model_requests: tuple[ModelRequestEvidence, ...]
    responses: tuple[ModelResponseEvidence, ...]
    validation_failures: tuple[ValidationFailure, ...]
    effective_model: ModelIdentity
    aggregate_usage: UsageEvidence
    schema_version: str | None = None
    realization: RealizationIdentity | None = None
    semantic_score: SemanticScore | None = None
    semantic_score_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    terminal_error: ErrorEvidence | None = None


class DuplicateExperimentRunError(ValueError):
    """Raised when an immutable run ID is submitted more than once."""


class ExperimentRepository(Protocol):
    """Storage boundary for immutable composition experiment evidence."""

    def save(self, run: ExperimentRun) -> None: ...

    def get(self, run_id: str) -> ExperimentRun | None: ...

    def list_group(self, experiment_group_id: str) -> tuple[ExperimentRun, ...]: ...
