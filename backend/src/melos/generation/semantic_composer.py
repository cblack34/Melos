"""Pydantic-AI adapter for one complete semantic-score composition attempt."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from pydantic_ai import (
    Agent,
    ModelRetry,
    NativeOutput,
    RunContext,
    capture_run_messages,
)
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.settings import ModelSettings

from melos.domain.composition import (
    InjectedInstruction,
    RawUserContent,
    RequestedInstrumentConstraints,
    RequestedMetaConstraints,
    ResolvedCompositionConstraints,
    WholeSongCompositionInput,
)
from melos.domain.generator import GenerationRequest
from melos.domain.lyrics import parse_song_source
from melos.domain.provenance import (
    ErrorEvidence,
    ExperimentRepository,
    ExperimentRun,
    InjectedInstructionEvidence,
    ModelIdentity,
    ModelResponseEvidence,
    RequestedMeta,
    UsageEvidence,
    ValidationFailure,
)
from melos.domain.semantic import Meter, SemanticScore, semantic_score_hash
from melos.generation.experiments import EvidenceRedactor, InMemoryExperimentRepository
from melos.generation.meta import ResolvedMeta
from melos.generation.observability import progress_hooks

_OUTPUT_RETRIES = 3
_INSTRUCTION_ID = "whole-song-semantic-composer"
_INSTRUCTION_VERSION = "1"
_AGENT_INSTRUCTIONS = (
    "Follow the versioned injected instructions in the whole-song composition "
    "input and return one valid SemanticScore."
)
_INJECTED_INSTRUCTIONS = (
    "Compose exactly one complete whole-song SemanticScore. The user content, "
    "resolved constraints, and ordered source markup are supplied as structured "
    "data. Preserve every supplied directive as user_directives; only put new "
    "compatible ideas in composer_enhancements. Never compose individual sections "
    "or emit MIDI-shaped note-event JSON."
)


class ProvenancePersistenceError(RuntimeError):
    """A composition result cannot be returned when its evidence was not saved."""

    def __init__(self, message: str, *, persistence_error: Exception) -> None:
        super().__init__(message)
        self.persistence_error = persistence_error


class _RunEvidence:
    """Per-call hook state; an adapter instance may compose concurrently."""

    def __init__(self) -> None:
        self.last_request_messages: list[ModelMessage] = []
        self.responses: list[ModelResponse] = []
        self.response_models: list[ModelIdentity] = []
        self.validation_failures: list[ValidationFailure] = []
        self.model: ModelIdentity | None = None

    def observe_request(
        self, request_context: ModelRequestContext, redactor: EvidenceRedactor
    ) -> None:
        self.last_request_messages = list(request_context.messages)
        self.model = _model_identity(request_context, redactor)

    def observe_response(
        self, request_context: ModelRequestContext, redactor: EvidenceRedactor
    ) -> None:
        self.observe_request(request_context, redactor)
        assert self.model is not None
        self.response_models.append(self.model)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_run_id() -> str:
    return f"run-{uuid4()}"


def composition_input_from(
    request: GenerationRequest, meta: ResolvedMeta
) -> WholeSongCompositionInput:
    """Normalize existing request/meta seams without changing their contracts."""
    return WholeSongCompositionInput(
        raw_user_content=RawUserContent(prompt=request.prompt, lyrics=request.lyrics),
        requested_meta=RequestedMetaConstraints(
            tempo_bpm=request.tempo_bpm,
            key=request.key,
            meter=(
                Meter(
                    numerator=request.time_signature.numerator,
                    denominator=request.time_signature.denominator,
                )
                if request.time_signature is not None
                else None
            ),
        ),
        resolved_constraints=ResolvedCompositionConstraints(
            tempo_bpm=meta.tempo_bpm,
            key=meta.key,
            meter=Meter(
                numerator=meta.time_signature.numerator,
                denominator=meta.time_signature.denominator,
            ),
        ),
        requested_instruments=RequestedInstrumentConstraints(
            include=tuple(request.include_instruments),
            exclude=tuple(request.exclude_instruments),
        ),
        source=parse_song_source(request.lyrics),
        injected_instructions=(
            InjectedInstruction(
                id=_INSTRUCTION_ID,
                version=_INSTRUCTION_VERSION,
                text=_INJECTED_INSTRUCTIONS,
            ),
        ),
    )


class PydanticAISemanticScoreComposer:
    """An isolated adapter; production routing remains on the legacy generator."""

    def __init__(
        self,
        model: Model,
        *,
        use_native_output: bool,
        model_settings: ModelSettings | None = None,
        repository: ExperimentRepository | None = None,
        clock: Callable[[], datetime] = _utc_now,
        run_id_factory: Callable[[], str] = _new_run_id,
        redactor: EvidenceRedactor | None = None,
    ) -> None:
        self._model = model
        self._model_settings = model_settings
        self._repository = repository or InMemoryExperimentRepository()
        self._clock = clock
        self._run_id_factory = run_id_factory
        self._redactor = redactor or EvidenceRedactor()
        output_type = (
            NativeOutput(SemanticScore) if use_native_output else SemanticScore
        )
        self._agent: Agent[WholeSongCompositionInput, SemanticScore] = Agent(
            model,
            output_type=output_type,
            instructions=_AGENT_INSTRUCTIONS,
            deps_type=WholeSongCompositionInput,
            retries={"output": _OUTPUT_RETRIES},
            model_settings=model_settings,
            capabilities=[progress_hooks()],
        )

        @self._agent.output_validator
        def _enforce(
            ctx: RunContext[WholeSongCompositionInput], score: SemanticScore
        ) -> SemanticScore:
            if violations := ctx.deps.score_violations(score):
                raise ModelRetry(
                    "Regenerate the complete SemanticScore without contradicting "
                    "the whole-song context:\n- " + "\n- ".join(violations)
                )
            return score

    async def compose(self, composition: WholeSongCompositionInput) -> SemanticScore:
        """Run and persist one whole-song attempt, including failed-run evidence."""
        started_at = self._clock()
        started = perf_counter()
        run_id = self._run_id_factory()
        evidence = _RunEvidence()
        score: SemanticScore | None = None
        terminal_error: Exception | None = None
        result_usage: object | None = None
        final_messages: list[ModelMessage] = []

        with capture_run_messages() as captured_messages:
            try:
                result = await self._agent.run(
                    _composition_message(composition),
                    deps=composition,
                    run_id=run_id,
                    capabilities=[self._provenance_hooks(evidence)],
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

    def _provenance_hooks(self, evidence: _RunEvidence) -> Hooks:
        async def before_model_request(
            _ctx: RunContext[WholeSongCompositionInput],
            request_context: ModelRequestContext,
        ) -> ModelRequestContext:
            evidence.observe_request(request_context, self._redactor)
            return request_context

        async def after_model_request(
            _ctx: RunContext[WholeSongCompositionInput],
            *,
            request_context: ModelRequestContext,
            response: ModelResponse,
        ) -> ModelResponse:
            evidence.observe_response(request_context, self._redactor)
            evidence.responses.append(response)
            return response

        async def model_request_error(
            _ctx: RunContext[WholeSongCompositionInput],
            *,
            request_context: ModelRequestContext,
            error: Exception,
        ) -> ModelResponse:
            evidence.observe_request(request_context, self._redactor)
            raise error

        async def output_validation_error(
            ctx: RunContext[WholeSongCompositionInput],
            *,
            output_context: object,
            output: object,
            error: Exception,
        ) -> object:
            del output_context, output
            evidence.validation_failures.append(
                ValidationFailure(
                    retry_index=ctx.retry,
                    message=str(error) or type(error).__name__,
                )
            )
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
                evidence.validation_failures.append(
                    ValidationFailure(
                        retry_index=ctx.retry,
                        message=str(error) or type(error).__name__,
                    )
                )
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
        responses = tuple(
            _response_evidence(response, model, self._redactor)
            for response, model in zip(
                evidence.responses, evidence.response_models, strict=True
            )
        )
        aggregate_usage = _usage_evidence(
            (
                result_usage
                if result_usage is not None
                else _aggregate_response_usage(responses)
            ),
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
            injected_instructions=tuple(
                InjectedInstructionEvidence(
                    id=instruction.id,
                    version=instruction.version,
                    content_hash=_hash_text(instruction.text),
                )
                for instruction in composition.injected_instructions
            ),
            final_messages_json=_messages_json(final_messages, self._redactor),
            responses=responses,
            validation_failures=tuple(
                failure.model_copy(
                    update={"message": self._redactor.redact(failure.message)}
                )
                for failure in evidence.validation_failures
            ),
            effective_model=evidence.model
            or ModelIdentity(
                provider=_redacted_optional(
                    _model_provider(self._model), self._redactor
                ),
                model=_redacted_optional(self._model.model_name, self._redactor),
                settings_json=_json_evidence(
                    self._model_settings or {}, self._redactor
                ),
            ),
            aggregate_usage=aggregate_usage,
            schema_version=score.schema_version if score is not None else None,
            realization=score.realization if score is not None else None,
            semantic_score=score,
            semantic_score_hash=(
                semantic_score_hash(score) if score is not None else None
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


def _composition_message(composition: WholeSongCompositionInput) -> str:
    """Keep the complete input in one stable, inspectable user message."""
    return "Whole-song composition input (JSON):\n" + composition.model_dump_json(
        by_alias=True
    )


def _experiment_group_id(composition: WholeSongCompositionInput) -> str:
    payload = json.dumps(
        composition.model_dump(mode="json"),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"experiment-{_hash_text(payload)[:32]}"


def _hash_text(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _messages_json(messages: list[ModelMessage], redactor: EvidenceRedactor) -> str:
    payload = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    return _json_evidence(payload, redactor)


def _response_evidence(
    response: ModelResponse,
    effective_model: ModelIdentity,
    redactor: EvidenceRedactor,
) -> ModelResponseEvidence:
    return ModelResponseEvidence(
        response_json=_messages_json([response], redactor),
        provider_response_id=_redacted_optional(
            response.provider_response_id, redactor
        ),
        provider=_redacted_optional(response.provider_name, redactor),
        model=_redacted_optional(response.model_name, redactor),
        effective_model=effective_model,
        usage=_usage_evidence(response.usage, requests=1, redactor=redactor),
    )


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
    usage: object,
    *,
    requests: int,
    redactor: EvidenceRedactor,
) -> UsageEvidence:
    details = getattr(usage, "details", {})
    return UsageEvidence(
        requests=getattr(usage, "requests", requests),
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_write_tokens=getattr(usage, "cache_write_tokens", 0),
        cache_read_tokens=getattr(usage, "cache_read_tokens", 0),
        details_json=_json_evidence(details, redactor),
    )


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


def _json_evidence(value: object, redactor: EvidenceRedactor) -> str:
    return json.dumps(
        redactor.redact(value),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
