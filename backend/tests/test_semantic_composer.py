"""Behavioral tests for the isolated whole-song semantic composer boundary."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from melos.domain.generator import GenerationRequest
from melos.domain.provenance import (
    DuplicateExperimentRunError,
    ExperimentRepository,
    ExperimentRun,
)
from melos.domain.semantic import Meter, SemanticScore
from melos.generation.experiments import (
    EvidenceRedactor,
    InMemoryExperimentRepository,
    JsonExperimentRepository,
)
from melos.generation.meta import ResolvedMeta
from melos.generation.semantic_composer import (
    ProvenancePersistenceError,
    PydanticAISemanticScoreComposer,
    composition_input_from,
)
from melos.realization import realize_score

_COMPOSITION_INPUT_PREFIX = "Whole-song composition input (JSON):\n"


def beat(numerator: int, denominator: int = 1) -> dict[str, int]:
    return {"n": numerator, "d": denominator}


def score_data(**overrides: object) -> dict[str, object]:
    note = {
        "onset": beat(0),
        "duration": beat(1),
        "pitch": {"step": "C", "octave": 4},
    }
    vocal_notes = [
        {**note, "onset": beat(0)},
        {**note, "onset": beat(1), "pitch": {"step": "D", "octave": 4}},
    ]
    score: dict[str, object] = {
        "id": "whole-song",
        "title": "Whole Song",
        "tempo_bpm": 96,
        "key": "G",
        "meter": {"numerator": 4, "denominator": 4},
        "form": [
            {"id": "verse", "label": "Verse", "start": beat(0), "duration": beat(4)},
            {"id": "chorus", "label": "Chorus", "start": beat(4), "duration": beat(4)},
        ],
        "user_directives": [
            {"id": "user-restraint", "text": "Keep the chorus restrained."}
        ],
        "composer_enhancements": [
            {"id": "composer-detail", "text": "Use a sparse pickup."}
        ],
        "parts": [
            {
                "family": "melodic",
                "id": "melody",
                "name": "Melody",
                "instrument": "lead-synth",
                "phrases": [
                    {
                        "id": "melody-phrase",
                        "occurrence_id": "verse",
                        "start": beat(0),
                        "notes": [note],
                    }
                ],
            },
            {
                "family": "melodic",
                "id": "counterline",
                "name": "Counterline",
                "instrument": "lead-synth",
                "phrases": [
                    {
                        "id": "counterline-phrase",
                        "occurrence_id": "chorus",
                        "start": beat(4),
                        "notes": [note],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "lead-vocal",
                "name": "Lead vocal",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "verse-vocal",
                        "occurrence_id": "verse",
                        "start": beat(0),
                        "notes": vocal_notes,
                        "lyric_assignments": [
                            {
                                "id": "first",
                                "token_id": "token-first",
                                "role": "primary",
                                "syllables": [{"text": "First", "note_indexes": [0]}],
                            },
                            {
                                "id": "line-one",
                                "token_id": "token-line-one",
                                "role": "primary",
                                "syllables": [{"text": "line", "note_indexes": [1]}],
                            },
                        ],
                    },
                    {
                        "id": "chorus-vocal",
                        "occurrence_id": "chorus",
                        "start": beat(4),
                        "notes": vocal_notes,
                        "lyric_assignments": [
                            {
                                "id": "second",
                                "token_id": "token-second",
                                "role": "primary",
                                "syllables": [{"text": "Second", "note_indexes": [0]}],
                            },
                            {
                                "id": "line-two",
                                "token_id": "token-line-two",
                                "role": "primary",
                                "syllables": [{"text": "line", "note_indexes": [1]}],
                            },
                        ],
                    },
                ],
            },
        ],
        "lyric_tokens": [
            {
                "id": "token-first",
                "occurrence_id": "verse",
                "source_index": 0,
                "display_text": "First",
            },
            {
                "id": "token-line-one",
                "occurrence_id": "verse",
                "source_index": 1,
                "display_text": " line",
            },
            {
                "id": "token-second",
                "occurrence_id": "chorus",
                "source_index": 2,
                "display_text": " Second",
            },
            {
                "id": "token-line-two",
                "occurrence_id": "chorus",
                "source_index": 3,
                "display_text": " line",
            },
        ],
        "realization": {"recipe_version": "semantic-realization-v1"},
    }
    score.update(overrides)
    return score


def drop_lyrics(data: dict[str, object]) -> None:
    """Keep the score schema-valid while removing the requested display text."""
    data["lyric_tokens"] = []
    parts = data["parts"]
    assert isinstance(parts, list)
    data["parts"] = parts[:2]


def composition() -> tuple[GenerationRequest, ResolvedMeta]:
    request = GenerationRequest.model_validate(
        {
            "prompt": "a warm folk song",
            "tempo_bpm": 96,
            "key": "G",
            "time_signature": {"numerator": 4, "denominator": 4},
            "include_instruments": ["Flute"],
            "exclude_instruments": ["Trumpet"],
            "lyrics": (
                "[Verse]\n"
                "First line\n"
                "{Keep the chorus restrained.}\n"
                "[Chorus]\n"
                "Second line"
            ),
        }
    )
    return (
        request,
        ResolvedMeta(
            tempo_bpm=96,
            key="G",
            time_signature={"numerator": 4, "denominator": 4},
        ),
    )


def text_parts(messages: list[ModelMessage]) -> list[str]:
    contents: list[str] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                contents.append(content)
    return contents


def whole_song_input(messages: list[str]) -> dict[str, Any]:
    payload_messages = [
        message for message in messages if message.startswith(_COMPOSITION_INPUT_PREFIX)
    ]
    assert len(payload_messages) == 1
    payload = json.loads(payload_messages[0].removeprefix(_COMPOSITION_INPUT_PREFIX))
    assert isinstance(payload, dict)
    return payload


def test_redactor_removes_secret_keyed_fields_without_erasing_lyric_tokens() -> None:
    redacted = EvidenceRedactor(["configured-secret"]).redact(
        {
            "Authorization": "Bearer configured-secret",
            "nested": {"api_key": "configured-secret"},
            "lyric_tokens": ["configured-secret"],
        }
    )

    assert redacted == {
        "Authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]"},
        "lyric_tokens": ["[REDACTED]"],
    }


def composer_returning(
    payloads: list[dict[str, object]],
    histories: list[list[str]],
    *,
    repository: ExperimentRepository | None = None,
    redactor: EvidenceRedactor | None = None,
    run_id_factory: Callable[[], str] = lambda: "run-test",
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PydanticAISemanticScoreComposer:
    remaining = list(payloads)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        histories.append(text_parts(messages))
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, payload)],
            model_name="test-semantic-model",
            provider_name="test-provider",
            provider_response_id=f"response-{len(histories)}",
            usage=RequestUsage(input_tokens=10, output_tokens=20),
        )

    return PydanticAISemanticScoreComposer(
        FunctionModel(respond),
        use_native_output=False,
        repository=repository,
        redactor=redactor,
        run_id_factory=run_id_factory,
        clock=clock,
    )


@pytest.mark.anyio
async def test_complete_ordered_context_reaches_one_whole_song_composer() -> None:
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    histories: list[list[str]] = []

    result = await composer_returning([score_data()], histories).compose(input_data)

    assert isinstance(result, SemanticScore)
    assert len(histories) == 1
    assert input_data.requested_instruments.include == ("Flute",)
    assert input_data.requested_instruments.exclude == ("Trumpet",)
    assert input_data.source.sung_text == request.lyrics_spec.sung_text
    payload = whole_song_input(histories[0])
    expected_constraints = input_data.resolved_constraints.model_dump(mode="json")
    expected_instruments = input_data.requested_instruments.model_dump(mode="json")
    assert payload["raw_user_content"] == input_data.raw_user_content.model_dump(
        mode="json"
    )
    assert payload["resolved_constraints"] == expected_constraints
    assert payload["requested_instruments"] == expected_instruments
    assert payload["source"] == input_data.source.model_dump(mode="json")
    assert payload["injected_instructions"] == [
        instruction.model_dump(mode="json")
        for instruction in input_data.injected_instructions
    ]
    assert all(
        "Compose exactly one complete whole-song SemanticScore." not in message
        for message in histories[0]
        if not message.startswith(_COMPOSITION_INPUT_PREFIX)
    )


@pytest.mark.anyio
async def test_retry_keeps_complete_context_and_never_calls_a_section_composer() -> (
    None
):
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    rejected = deepcopy(score_data())
    rejected["tempo_bpm"] = 120
    histories: list[list[str]] = []

    result = await composer_returning([rejected, score_data()], histories).compose(
        input_data
    )

    assert result.tempo_bpm == 96
    assert len(histories) == 2
    for history in histories:
        payload = whole_song_input(history)
        assert payload["raw_user_content"] == input_data.raw_user_content.model_dump(
            mode="json"
        )
        assert payload["source"] == input_data.source.model_dump(mode="json")
        assert all("section composition input" not in message for message in history)
    assert any(
        "tempo_bpm must exactly match the resolved constraint: expected 96.0, got 120.0"
        in prompt
        for prompt in histories[1]
    )


@pytest.mark.anyio
async def test_successful_run_persists_separated_inputs_and_score_evidence() -> None:
    request, meta = composition()
    repository = InMemoryExperimentRepository()
    composer = composer_returning([score_data()], [], repository=repository)

    score = await composer.compose(composition_input_from(request, meta))

    run = repository.get("run-test")
    assert run is not None
    assert run.raw_user_content.prompt == request.prompt
    assert run.requested_meta.tempo_bpm == request.tempo_bpm
    assert run.requested_meta.key == request.key
    assert run.requested_meta.meter == Meter(numerator=4, denominator=4)
    assert run.resolved_constraints.tempo_bpm == meta.tempo_bpm
    assert run.injected_instructions[0].content_hash
    assert run.semantic_score == score
    assert run.semantic_score_hash is not None
    assert run.responses[0].provider_response_id == "response-1"
    assert run.aggregate_usage.input_tokens == 10
    assert run.aggregate_usage.output_tokens == 20
    assert run.terminal_error is None


@pytest.mark.anyio
async def test_retry_run_records_all_responses_and_validator_feedback() -> None:
    request, meta = composition()
    rejected = deepcopy(score_data())
    rejected["tempo_bpm"] = 120
    repository = InMemoryExperimentRepository()
    composer = composer_returning([rejected, score_data()], [], repository=repository)

    await composer.compose(composition_input_from(request, meta))

    run = repository.get("run-test")
    assert run is not None
    assert [response.provider_response_id for response in run.responses] == [
        "response-1",
        "response-2",
    ]
    assert run.aggregate_usage.requests == 2
    assert len(run.validation_failures) == 1
    assert "tempo_bpm must exactly match" in run.validation_failures[0].message
    messages = json.loads(run.final_messages_json)
    assert any(
        part["part_kind"] == "retry-prompt"
        for message in messages
        for part in message["parts"]
    )


@pytest.mark.anyio
async def test_redaction_removes_secret_values_from_persisted_evidence() -> None:
    request, meta = composition()
    request = request.model_copy(update={"prompt": "write with token super-secret"})
    repository = InMemoryExperimentRepository()
    composer = composer_returning(
        [score_data()],
        [],
        repository=repository,
        redactor=EvidenceRedactor(["super-secret"]),
    )

    await composer.compose(composition_input_from(request, meta))

    run = repository.get("run-test")
    assert run is not None
    assert "super-secret" not in run.raw_user_content.prompt
    assert "super-secret" not in run.final_messages_json
    assert "[REDACTED]" in run.final_messages_json


@pytest.mark.anyio
async def test_retry_exhaustion_retains_the_final_untransmitted_failure() -> None:
    request, meta = composition()
    rejected = deepcopy(score_data())
    rejected["tempo_bpm"] = 120
    repository = InMemoryExperimentRepository()
    composer = composer_returning([rejected], [], repository=repository)

    with pytest.raises(UnexpectedModelBehavior):
        await composer.compose(composition_input_from(request, meta))

    run = repository.get("run-test")
    assert run is not None
    assert len(run.responses) == 4
    assert len(run.validation_failures) == 4
    assert run.aggregate_usage.requests == 4
    assert run.terminal_error is not None
    assert "tempo_bpm must exactly match" in run.validation_failures[-1].message


@pytest.mark.anyio
async def test_provider_failure_records_sent_request_and_terminal_error() -> None:
    request, meta = composition()
    repository = InMemoryExperimentRepository()

    def fail(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise RuntimeError("provider unavailable")

    composer = PydanticAISemanticScoreComposer(
        FunctionModel(fail),
        use_native_output=False,
        repository=repository,
        run_id_factory=lambda: "run-provider-failure",
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await composer.compose(composition_input_from(request, meta))

    run = repository.get("run-provider-failure")
    assert run is not None
    assert run.responses == ()
    assert run.terminal_error is not None
    assert run.terminal_error.message == "provider unavailable"
    assert "Whole-song composition input" in run.final_messages_json


@pytest.mark.anyio
async def test_provenance_repository_failure_prevents_unrecorded_success() -> None:
    class FailingRepository:
        def save(self, run: ExperimentRun) -> None:
            del run
            raise OSError("disk unavailable")

        def get(self, run_id: str) -> ExperimentRun | None:
            del run_id
            return None

        def list_group(self, experiment_group_id: str) -> tuple[ExperimentRun, ...]:
            del experiment_group_id
            return ()

    request, meta = composition()
    composer = composer_returning([score_data()], [], repository=FailingRepository())

    with pytest.raises(ProvenancePersistenceError, match="successful") as error:
        await composer.compose(composition_input_from(request, meta))

    assert isinstance(error.value.persistence_error, OSError)


@pytest.mark.anyio
async def test_json_repository_round_trips_immutable_sibling_runs(
    tmp_path: Path,
) -> None:
    request, meta = composition()
    composition_input = composition_input_from(request, meta)
    repository = JsonExperimentRepository(tmp_path)

    def clock() -> datetime:
        return datetime(2026, 8, 1, tzinfo=UTC)

    await composer_returning(
        [score_data()],
        [],
        repository=repository,
        run_id_factory=lambda: "run-b",
        clock=clock,
    ).compose(composition_input)
    await composer_returning(
        [score_data()],
        [],
        repository=repository,
        run_id_factory=lambda: "run-a",
        clock=clock,
    ).compose(composition_input)
    changed_instruction = composition_input.injected_instructions[0].model_copy(
        update={"version": "2", "text": "A distinct, versioned instruction."}
    )
    changed_input = composition_input.model_copy(
        update={"injected_instructions": (changed_instruction,)}
    )
    await composer_returning(
        [score_data()],
        [],
        repository=repository,
        run_id_factory=lambda: "run-c",
        clock=clock,
    ).compose(changed_input)

    first = repository.get("run-b")
    changed = repository.get("run-c")
    assert first is not None
    assert changed is not None
    assert [run.run_id for run in repository.list_group(first.experiment_group_id)] == [
        "run-a",
        "run-b",
    ]
    with pytest.raises(DuplicateExperimentRunError):
        repository.save(first)
    assert changed.experiment_group_id != first.experiment_group_id
    assert changed.raw_user_content == first.raw_user_content


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda data: data.__setitem__("key", "C"),
            "key must exactly match the resolved constraint: expected 'G', got 'C'",
        ),
        (
            lambda data: data.__setitem__("user_directives", []),
            "user_directives must preserve exactly",
        ),
        (
            lambda data: data["form"][1].__setitem__("label", "Bridge"),
            "form occurrences must match",
        ),
        (drop_lyrics, "lyric_tokens must reconstruct the supplied lyrics exactly"),
        (
            lambda data: data["lyric_tokens"][0].__setitem__("display_text", "Changed"),
            "lyric_tokens must reconstruct the supplied lyrics exactly",
        ),
    ],
)
async def test_represented_user_constraints_are_retried(
    mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    rejected = deepcopy(score_data())
    mutate(rejected)
    histories: list[list[str]] = []

    result = await composer_returning([rejected, score_data()], histories).compose(
        input_data
    )

    assert result == SemanticScore.model_validate(score_data())
    assert len(histories) == 2
    assert any(message in prompt for prompt in histories[1])


def test_meta_constraint_feedback_includes_expected_and_actual_values() -> None:
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    score = SemanticScore.model_validate(score_data())
    rejected = score.model_copy(
        update={
            "tempo_bpm": 120,
            "key": "C",
            "meter": Meter(numerator=3, denominator=4),
        }
    )

    assert input_data.score_violations(rejected)[:3] == [
        "tempo_bpm must exactly match the resolved constraint: expected 96.0, got 120",
        "key must exactly match the resolved constraint: expected 'G', got 'C'",
        "meter must exactly match the resolved time signature: expected 4/4, got 3/4",
    ]


@pytest.mark.anyio
async def test_raw_content_instructions_and_composer_enhancements_stay_separate() -> (
    None
):
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    histories: list[list[str]] = []

    score = await composer_returning([score_data()], histories).compose(input_data)

    assert input_data.raw_user_content.prompt == request.prompt
    assert input_data.raw_user_content.lyrics == request.lyrics
    assert input_data.injected_instructions[0].text != request.prompt
    assert [directive.text for directive in score.user_directives] == [
        "Keep the chorus restrained."
    ]
    assert [enhancement.text for enhancement in score.composer_enhancements] == [
        "Use a sparse pickup."
    ]
    assert score.composer_enhancements[0].text not in input_data.raw_user_content.prompt


@pytest.mark.anyio
async def test_validated_composer_output_is_compatible_with_realization() -> None:
    request, meta = composition()
    result = await composer_returning([score_data()], []).compose(
        composition_input_from(request, meta)
    )

    realized = realize_score(result)
    assert [track.name for track in realized.song.tracks] == [
        "Melody",
        "Counterline",
        "Lead vocal",
    ]
