"""Pydantic AI capture and durable evidence for semantic composition attempts."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from pydantic_ai import Agent, ModelRetry, RunContext, capture_run_messages
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from melos.domain.composition import RawUserContent, WholeSongCompositionInput
from melos.domain.lyrics import SongSource
from melos.domain.provenance import (
    ErrorEvidence,
    ExperimentRepository,
    ExperimentRun,
    InjectedInstructionEvidence,
    ModelIdentity,
    ModelRequestEvidence,
    ModelResponseEvidence,
    RequestedMeta,
    UsageEvidence,
    ValidationFailure,
)
from melos.domain.semantic import SemanticScore, semantic_score_hash
from melos.generation.experiments import EvidenceRedactor


class ProvenancePersistenceError(RuntimeError):
    """A composition result cannot be returned when its evidence was not saved."""

    def __init__(self, message: str, *, persistence_error: Exception) -> None:
        super().__init__(message)
        self.persistence_error = persistence_error


class _RunEvidence:
    """Per-call hook state; one recorder can safely observe concurrent runs."""

    def __init__(self, redactor: EvidenceRedactor) -> None:
        self._redactor = redactor
        self.last_request_messages: list[ModelMessage] = []
        self.model_requests: list[ModelRequestEvidence] = []
        self.responses: list[tuple[ModelResponse, ModelRequestEvidence]] = []
        self.validation_failures: list[ValidationFailure] = []
        self.latest_request: ModelRequestEvidence | None = None

    def observe_request(self, request_context: ModelRequestContext) -> None:
        self.last_request_messages = list(request_context.messages)
        request = ModelRequestEvidence(
            effective_model=_model_identity(request_context, self._redactor),
            parameters_json=_json_evidence(
                asdict(request_context.model_request_parameters), self._redactor
            ),
        )
        self.model_requests.append(request)
        self.latest_request = request

    def observe_response(self, response: ModelResponse) -> None:
        if self.latest_request is None:
            raise RuntimeError("received a model response without a captured request")
        self.responses.append((response, self.latest_request))


class _UsageValues(Protocol):
    """The token fields shared by Pydantic AI request and run usage objects."""

    @property
    def requests(self) -> int: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def cache_write_tokens(self) -> int: ...

    @property
    def cache_read_tokens(self) -> int: ...

    @property
    def details(self) -> Mapping[str, object]: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return f"run-{uuid4()}"


def _pydantic_ai_version() -> str:
    return version("pydantic-ai-slim")


class CompositionExperimentRecorder:
    """Run an agent and save complete provenance before returning or re-raising."""

    def __init__(
        self,
        *,
        repository: ExperimentRepository,
        model: Model,
        model_settings: ModelSettings | None,
        clock: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[], str] | None = None,
        redactor: EvidenceRedactor | None = None,
        pydantic_ai_version: str | None = None,
    ) -> None:
        self._repository = repository
        self._model = model
        self._model_settings = model_settings
        self._clock = clock or _utc_now
        self._run_id_factory = run_id_factory or _new_run_id
        self._redactor = redactor or EvidenceRedactor()
        self._pydantic_ai_version = pydantic_ai_version or _pydantic_ai_version()

    async def run(
        self,
        agent: Agent[WholeSongCompositionInput, SemanticScore],
        composition: WholeSongCompositionInput,
        prompt: str,
    ) -> SemanticScore:
        """Capture successful and failed Pydantic AI runs through supported APIs."""
        started_at = self._clock()
        started = perf_counter()
        run_id = self._run_id_factory()
        evidence = _RunEvidence(self._redactor)
        score: SemanticScore | None = None
        terminal_error: Exception | None = None
        result_usage: RunUsage | None = None

        with capture_run_messages() as captured_messages:
            try:
                result = await agent.run(
                    prompt,
                    deps=composition,
                    run_id=run_id,
                    capabilities=[self._hooks(evidence)],
                )
                score = result.output
                result_usage = result.usage
            except Exception as error:
                terminal_error = error
        final_messages = list(captured_messages) or evidence.last_request_messages

        run = self._build_run(
            composition=composition,
            run_id=run_id,
            started_at=started_at,
            elapsed_seconds=perf_counter() - started,
            evidence=evidence,
            final_messages=final_messages,
            result_usage=result_usage,
            score=score,
            terminal_error=terminal_error,
        )
        try:
            self._repository.save(run)
        except Exception as persistence_error:
            if terminal_error is not None:
                raise ProvenancePersistenceError(
                    "failed to persist composition provenance after composition failed",
                    persistence_error=persistence_error,
                ) from terminal_error
            raise ProvenancePersistenceError(
                "failed to persist successful composition provenance",
                persistence_error=persistence_error,
            ) from persistence_error

        if terminal_error is not None:
            raise terminal_error
        assert score is not None
        return score

    def _hooks(self, evidence: _RunEvidence) -> Hooks:
        async def before_model_request(
            _ctx: RunContext[WholeSongCompositionInput],
            request_context: ModelRequestContext,
        ) -> ModelRequestContext:
            evidence.observe_request(request_context)
            return request_context

        async def after_model_request(
            _ctx: RunContext[WholeSongCompositionInput],
            *,
            request_context: ModelRequestContext,
            response: ModelResponse,
        ) -> ModelResponse:
            del request_context
            evidence.observe_response(response)
            return response

        async def model_request_error(
            _ctx: RunContext[WholeSongCompositionInput],
            *,
            request_context: ModelRequestContext,
            error: Exception,
        ) -> ModelResponse:
            del request_context
            raise error

        async def output_validation_error(
            ctx: RunContext[WholeSongCompositionInput],
            *,
            output_context: object,
            output: object,
            error: Exception,
        ) -> object:
            del output_context, output
            evidence.validation_failures.append(_validation_failure(ctx, error))
            raise error

        async def output_process(
            ctx: RunContext[WholeSongCompositionInput],
            *,
            output_context: object,
            output: object,
            handler: Callable[[object], Awaitable[object]],
        ) -> object:
            del output_context
            try:
                return await handler(output)
            except ModelRetry as error:
                evidence.validation_failures.append(_validation_failure(ctx, error))
                raise

        return Hooks(
            before_model_request=before_model_request,
            after_model_request=after_model_request,
            model_request_error=model_request_error,
            output_validate_error=output_validation_error,
            output_process=output_process,
        )

    def _build_run(
        self,
        *,
        composition: WholeSongCompositionInput,
        run_id: str,
        started_at: datetime,
        elapsed_seconds: float,
        evidence: _RunEvidence,
        final_messages: list[ModelMessage],
        result_usage: object | None,
        score: SemanticScore | None,
        terminal_error: Exception | None,
    ) -> ExperimentRun:
        persisted_score = _redacted_score(score, self._redactor)
        responses = tuple(
            _response_evidence(response, request, self._redactor)
            for response, request in evidence.responses
        )
        usage: _UsageValues | Mapping[str, object] = _aggregate_response_usage(
            responses
        )
        if isinstance(result_usage, RunUsage):
            usage = result_usage
        aggregate_usage = _usage_evidence(
            usage,
            requests=len(responses),
            redactor=self._redactor,
        )
        return ExperimentRun(
            experiment_group_id=_experiment_group_id(composition),
            run_id=run_id,
            parent_revision_id=composition.parent_revision_id,
            started_at=started_at,
            finished_at=self._clock(),
            elapsed_seconds=elapsed_seconds,
            raw_user_content=RawUserContent.model_validate(
                self._redactor.redact(composition.raw_user_content.model_dump())
            ),
            requested_meta=RequestedMeta.model_validate(
                composition.requested_meta.model_dump()
            ),
            resolved_constraints=composition.resolved_constraints,
            requested_instruments=composition.requested_instruments,
            source=SongSource.model_validate(
                self._redactor.redact(composition.source.model_dump(mode="json"))
            ),
            injected_instructions=tuple(
                InjectedInstructionEvidence(
                    id=instruction.id,
                    version=instruction.version,
                    content_hash=_hash_text(instruction.text),
                )
                for instruction in composition.injected_instructions
            ),
            pydantic_ai_version=self._pydantic_ai_version,
            final_messages_json=_messages_json(final_messages, self._redactor),
            model_requests=tuple(evidence.model_requests),
            responses=responses,
            validation_failures=tuple(
                failure.model_copy(
                    update={"message": self._redactor.redact(failure.message)}
                )
                for failure in evidence.validation_failures
            ),
            effective_model=evidence.latest_request.effective_model
            if evidence.latest_request is not None
            else ModelIdentity(
                provider=_redacted_optional(
                    _model_provider(self._model), self._redactor
                ),
                model=_redacted_optional(self._model.model_name, self._redactor),
                settings_json=_json_evidence(
                    self._model_settings or {}, self._redactor
                ),
            ),
            aggregate_usage=aggregate_usage,
            schema_version=(
                persisted_score.schema_version if persisted_score is not None else None
            ),
            realization=(
                persisted_score.realization if persisted_score is not None else None
            ),
            semantic_score=persisted_score,
            semantic_score_hash=(
                semantic_score_hash(persisted_score)
                if persisted_score is not None
                else None
            ),
            terminal_error=(
                ErrorEvidence(
                    type=type(terminal_error).__name__,
                    message=self._redactor.redact(
                        str(terminal_error) or type(terminal_error).__name__
                    ),
                )
                if terminal_error is not None
                else None
            ),
        )


def _experiment_group_id(composition: WholeSongCompositionInput) -> str:
    payload = composition.model_dump(mode="json", exclude={"parent_revision_id"})
    return f"experiment-{_hash_json(payload)[:32]}"


def _hash_json(value: object) -> str:
    return _hash_text(
        json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    )


def _hash_text(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _messages_json(messages: list[ModelMessage], redactor: EvidenceRedactor) -> str:
    payload = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    return _json_evidence(_strip_provider_fields(payload), redactor)


def _strip_provider_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _strip_provider_fields(item)
            for key, item in value.items()
            if key not in {"provider_details", "metadata"}
        }
    if isinstance(value, list):
        return [_strip_provider_fields(item) for item in value]
    return value


def _response_evidence(
    response: ModelResponse,
    request: ModelRequestEvidence,
    redactor: EvidenceRedactor,
) -> ModelResponseEvidence:
    return ModelResponseEvidence(
        response_json=_messages_json([response], redactor),
        provider_response_id=_redacted_optional(
            response.provider_response_id, redactor
        ),
        provider=_redacted_optional(response.provider_name, redactor),
        model=_redacted_optional(response.model_name, redactor),
        effective_model=request.effective_model,
        usage=_usage_evidence(response.usage, requests=1, redactor=redactor),
    )


def _redacted_score(
    score: SemanticScore | None, redactor: EvidenceRedactor
) -> SemanticScore | None:
    if score is None:
        return None
    return SemanticScore.model_validate(redactor.redact(score.model_dump(mode="json")))


def _model_identity(
    request_context: ModelRequestContext, redactor: EvidenceRedactor
) -> ModelIdentity:
    return ModelIdentity(
        provider=_redacted_optional(_model_provider(request_context.model), redactor),
        model=_redacted_optional(request_context.model.model_name, redactor),
        settings_json=_json_evidence(request_context.model_settings or {}, redactor),
    )


def _model_provider(model: Model) -> str | None:
    try:
        return model.system
    except AttributeError, NotImplementedError:
        return None


def _redacted_optional(value: str | None, redactor: EvidenceRedactor) -> str | None:
    return redactor.redact(value) if value is not None else None


def _usage_evidence(
    usage: _UsageValues | Mapping[str, object],
    *,
    requests: int,
    redactor: EvidenceRedactor,
) -> UsageEvidence:
    values = _usage_mapping(usage)
    return UsageEvidence(
        requests=_usage_int(values, "requests", requests),
        input_tokens=_usage_int(values, "input_tokens"),
        output_tokens=_usage_int(values, "output_tokens"),
        cache_write_tokens=_usage_int(values, "cache_write_tokens"),
        cache_read_tokens=_usage_int(values, "cache_read_tokens"),
        details_json=_json_evidence(_usage_details(values), redactor),
    )


def _usage_mapping(
    usage: _UsageValues | Mapping[str, object],
) -> Mapping[str, object]:
    if isinstance(usage, Mapping):
        return {str(key): value for key, value in usage.items()}
    return {
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "details": usage.details,
    }


def _usage_int(values: Mapping[str, object], name: str, default: int = 0) -> int:
    value = values.get(name, default)
    return value if isinstance(value, int) else default


def _usage_details(values: Mapping[str, object]) -> dict[str, object]:
    details = values.get("details", {})
    if not isinstance(details, Mapping):
        return {}
    return {str(key): value for key, value in details.items()}


def _aggregate_response_usage(
    responses: tuple[ModelResponseEvidence, ...],
) -> dict[str, object]:
    details: dict[str, int] = {}
    for response in responses:
        for key, value in json.loads(response.usage.details_json).items():
            if isinstance(value, int):
                details[key] = details.get(key, 0) + value
    return {
        "requests": len(responses),
        "input_tokens": sum(response.usage.input_tokens for response in responses),
        "output_tokens": sum(response.usage.output_tokens for response in responses),
        "cache_write_tokens": sum(
            response.usage.cache_write_tokens for response in responses
        ),
        "cache_read_tokens": sum(
            response.usage.cache_read_tokens for response in responses
        ),
        "details": details,
    }


def _validation_failure(
    ctx: RunContext[WholeSongCompositionInput], error: Exception
) -> ValidationFailure:
    return ValidationFailure(
        retry_index=ctx.retry,
        message=str(error) or type(error).__name__,
    )


def _json_evidence(value: object, redactor: EvidenceRedactor) -> str:
    return json.dumps(
        redactor.redact(value),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
