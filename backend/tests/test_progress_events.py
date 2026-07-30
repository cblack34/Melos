"""Progress events from the generate pipeline (story #44)."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.domain.generator import GenerationRequest
from melos.domain.progress import ListProgressReporter, ProgressEvent
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.meta import MetaResolver
from melos.generation.stub import StubSongGenerator

GOOD_TRACKS: list[dict[str, object]] = [
    {
        "name": "Flute",
        "prog": 73,
        "voc": True,
        "notes": [{"s": 0, "d": 1, "p": 62, "lyr": "La"}],
    },
    {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 2, "p": 38}]},
]

GOOD_COMPACT: dict[str, object] = {
    "title": "Test Tune",
    "bpm": 97.0,
    "key": "D",
    "ts": "3/4",
    "tracks": GOOD_TRACKS,
}

FULL_META_REQUEST: dict[str, object] = {
    "prompt": "a gentle waltz",
    "tempo_bpm": 97,
    "key": "D",
    "time_signature": {"numerator": 3, "denominator": 4},
    "include_instruments": ["Flute"],
    "exclude_instruments": ["Trumpet"],
}

PARTIAL_META_REQUEST: dict[str, object] = {
    "prompt": "a gentle waltz",
    "tempo_bpm": 97,
    # key + time_signature left for the meta resolver
    "include_instruments": ["Flute"],
}


def _meta_resolver_fixed() -> MetaResolver:
    def explode(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("meta LLM must not be called: all meta is supplied")

    return MetaResolver(FunctionModel(explode), use_native_output=False)


def _meta_resolver_fills_gaps() -> MetaResolver:
    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        payload = {
            "tempo_bpm": 120.0,
            "key": "C",
            "time_signature": {"numerator": 4, "denominator": 4},
        }
        return ModelResponse(parts=[ToolCallPart(tool.name, payload)])

    return MetaResolver(FunctionModel(respond), use_native_output=False)


def _generator(
    payloads: list[dict[str, object]],
    *,
    meta: MetaResolver | None = None,
) -> PydanticAISongGenerator:
    remaining = list(payloads)

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, payload)])

    return PydanticAISongGenerator(
        FunctionModel(respond),
        meta if meta is not None else _meta_resolver_fixed(),
        use_native_output=False,
    )


def _phases(events: list[ProgressEvent]) -> list[str]:
    return [event.phase for event in events]


@pytest.mark.anyio
async def test_success_with_supplied_meta_skips_meta_llm_and_reports_phases() -> None:
    reporter = ListProgressReporter()
    await _generator([GOOD_COMPACT]).generate(
        GenerationRequest.model_validate(FULL_META_REQUEST),
        progress=reporter,
    )
    assert _phases(reporter.events) == [
        "request_received",
        "meta_skipped",
        "generation_started",
        "generation_completed",
    ]


@pytest.mark.anyio
async def test_missing_meta_emits_meta_started_and_completed() -> None:
    # Compact must echo resolved meta (overlay keeps user tempo 97).
    compact = {**GOOD_COMPACT, "bpm": 97.0, "key": "C", "ts": "4/4"}
    reporter = ListProgressReporter()
    await _generator([compact], meta=_meta_resolver_fills_gaps()).generate(
        GenerationRequest.model_validate(PARTIAL_META_REQUEST),
        progress=reporter,
    )
    assert _phases(reporter.events) == [
        "request_received",
        "meta_started",
        "meta_completed",
        "generation_started",
        "generation_completed",
    ]
    meta_done = next(e for e in reporter.events if e.phase == "meta_completed")
    assert meta_done.message is not None
    assert "97" in meta_done.message
    assert "C" in meta_done.message


@pytest.mark.anyio
async def test_constraint_retry_emits_validation_retry_with_reason() -> None:
    wrong_tempo: dict[str, object] = {**GOOD_COMPACT, "bpm": 120.0}
    reporter = ListProgressReporter()
    await _generator([wrong_tempo, GOOD_COMPACT]).generate(
        GenerationRequest.model_validate(FULL_META_REQUEST),
        progress=reporter,
    )
    assert _phases(reporter.events) == [
        "request_received",
        "meta_skipped",
        "generation_started",
        "validation_retry",
        "generation_completed",
    ]
    retry = next(e for e in reporter.events if e.phase == "validation_retry")
    assert retry.attempt == 1
    assert retry.max_attempts == 3
    assert any("bpm" in reason for reason in retry.reasons)


@pytest.mark.anyio
async def test_exhausted_retries_end_with_failed_event() -> None:
    wrong_tempo: dict[str, object] = {**GOOD_COMPACT, "bpm": 120.0}
    reporter = ListProgressReporter()
    with pytest.raises(UnexpectedModelBehavior):
        await _generator([wrong_tempo]).generate(
            GenerationRequest.model_validate(FULL_META_REQUEST),
            progress=reporter,
        )
    assert reporter.events[0].phase == "request_received"
    assert reporter.events[-1].phase == "failed"
    assert any(e.phase == "validation_retry" for e in reporter.events)
    assert reporter.events[-1].message


@pytest.mark.anyio
async def test_no_reporter_is_a_silent_no_op() -> None:
    # Default path used by existing callers must not require a progress sink.
    song = await _generator([GOOD_COMPACT]).generate(
        GenerationRequest.model_validate(FULL_META_REQUEST)
    )
    assert song.tempo_bpm == 97


@pytest.mark.anyio
async def test_stub_generator_emits_minimal_phase_sequence() -> None:
    reporter = ListProgressReporter()
    await StubSongGenerator().generate(
        GenerationRequest.model_validate({"prompt": "sketch"}),
        progress=reporter,
    )
    assert _phases(reporter.events) == [
        "request_received",
        "meta_skipped",
        "generation_started",
        "generation_completed",
    ]


def test_progress_event_is_json_serializable_for_future_sse() -> None:
    event = ProgressEvent(
        phase="validation_retry",
        message="Constraint check failed; regenerating",
        attempt=1,
        max_attempts=3,
        reasons=["bpm must be exactly 97"],
    )
    payload = event.model_dump(mode="json")
    assert payload["phase"] == "validation_retry"
    assert payload["reasons"] == ["bpm must be exactly 97"]
