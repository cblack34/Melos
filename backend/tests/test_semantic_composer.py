"""Behavioral tests for the isolated whole-song semantic composer boundary."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.domain.generator import GenerationRequest
from melos.domain.semantic import SemanticScore
from melos.generation.meta import ResolvedMeta
from melos.generation.semantic_composer import (
    PydanticAISemanticScoreComposer,
    composition_input_from,
)
from melos.realization import realize_score


def beat(numerator: int, denominator: int = 1) -> dict[str, int]:
    return {"n": numerator, "d": denominator}


def score_data(**overrides: object) -> dict[str, object]:
    note = {
        "onset": beat(0),
        "duration": beat(1),
        "pitch": {"step": "C", "octave": 4},
    }
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
        ],
        "realization": {"recipe_version": "semantic-realization-v1"},
    }
    score.update(overrides)
    return score


def composition() -> tuple[GenerationRequest, ResolvedMeta]:
    request = GenerationRequest.model_validate(
        {
            "prompt": "a warm folk song",
            "tempo_bpm": 96,
            "key": "G",
            "time_signature": {"numerator": 4, "denominator": 4},
            "include_instruments": ["Flute"],
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


def composer_returning(
    payloads: list[dict[str, object]], histories: list[list[str]]
) -> PydanticAISemanticScoreComposer:
    remaining = list(payloads)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        histories.append(text_parts(messages))
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    return PydanticAISemanticScoreComposer(
        FunctionModel(respond), use_native_output=False
    )


@pytest.mark.anyio
async def test_complete_ordered_context_reaches_one_whole_song_composer() -> None:
    request, meta = composition()
    input_data = composition_input_from(request, meta)
    histories: list[list[str]] = []

    result = await composer_returning([score_data()], histories).compose(input_data)

    assert isinstance(result, SemanticScore)
    assert len(histories) == 1
    prompt = histories[0][-1]
    assert '"raw_user_content":{"prompt":"a warm folk song"' in prompt
    assert '"resolved_constraints":{"tempo_bpm":96.0,"key":"G"' in prompt
    assert '"line_number":1,"kind":"section","name":"Verse"' in prompt
    assert '"line_number":4,"kind":"section","name":"Chorus"' in prompt
    assert (
        '"line_number":3,"kind":"directive","text":"Keep the chorus restrained."'
        in prompt
    )
    assert '"injected_instructions"' in prompt


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
        complete_context = history[0]
        assert '"name":"Verse"' in complete_context
        assert '"name":"Chorus"' in complete_context
        assert '"text":"Keep the chorus restrained."' in complete_context
        assert "section composition input" not in complete_context
    assert any("tempo_bpm must be exactly 96.0" in prompt for prompt in histories[1])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.__setitem__("key", "C"), "key must be exactly 'G'"),
        (
            lambda data: data.__setitem__("user_directives", []),
            "user_directives must preserve exactly",
        ),
        (
            lambda data: data["form"][1].__setitem__("label", "Bridge"),
            "form occurrences must match",
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
    assert [track.name for track in realized.song.tracks] == ["Melody", "Counterline"]
