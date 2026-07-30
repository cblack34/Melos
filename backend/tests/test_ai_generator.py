import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.domain.generator import GenerationRequest
from melos.domain.models import Song
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.meta import MetaResolver

GOOD_TRACKS: list[dict[str, object]] = [
    {
        "name": "Flute",
        "prog": 73,
        "voc": True,  # carries lyr, so it must be a vocal track
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

REQUEST: dict[str, object] = {
    "prompt": "a gentle waltz",
    "tempo_bpm": 97,
    "key": "D",
    "time_signature": {"numerator": 3, "denominator": 4},
    "include_instruments": ["Flute"],
    "exclude_instruments": ["Trumpet"],
}


def meta_resolver() -> MetaResolver:
    def explode(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("meta LLM must not be called: all meta is supplied")

    return MetaResolver(FunctionModel(explode), use_native_output=False)


def generator_returning(
    payloads: list[dict[str, object]], calls: list[str] | None = None
) -> PydanticAISongGenerator:
    """A generator whose model answers payloads[0], payloads[1], ... per call."""
    remaining = list(payloads)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if calls is not None:
            request = messages[0]
            assert isinstance(request, ModelRequest)
            part = request.parts[-1]
            assert isinstance(part, UserPromptPart)
            assert isinstance(part.content, str)
            calls.append(part.content)
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, payload)])

    return PydanticAISongGenerator(
        FunctionModel(respond), meta_resolver(), use_native_output=False
    )


async def generate(generator: PydanticAISongGenerator) -> Song:
    return await generator.generate(GenerationRequest.model_validate(REQUEST))


@pytest.mark.anyio
async def test_valid_output_becomes_domain_song() -> None:
    song = await generate(generator_returning([GOOD_COMPACT]))
    assert song.tempo_bpm == 97
    assert song.key == "D"
    assert {track.program for track in song.tracks} == {73, 33}
    assert song.tracks[0].notes[0].lyric == "La"


@pytest.mark.anyio
async def test_constraint_violation_is_retried_until_fixed() -> None:
    wrong_tempo: dict[str, object] = {**GOOD_COMPACT, "bpm": 120.0}
    calls: list[str] = []
    song = await generate(generator_returning([wrong_tempo, GOOD_COMPACT], calls))
    assert song.tempo_bpm == 97
    assert len(calls) == 2  # first answer rejected by the output validator


@pytest.mark.anyio
async def test_persistent_violation_exhausts_retries() -> None:
    forbidden: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            {"name": "Trumpet", "prog": 56, "notes": [{"s": 0, "d": 1, "p": 60}]},
            *GOOD_TRACKS,
        ],
    }
    with pytest.raises(UnexpectedModelBehavior):
        await generate(generator_returning([forbidden]))


@pytest.mark.anyio
async def test_retry_exhaustion_names_the_failing_constraint() -> None:
    # "Exceeded maximum output retries (3)" alone is unactionable: it says
    # nothing about which constraint the model kept missing, so a user report
    # of it cannot be diagnosed without re-running by hand.
    wrong_tempo: dict[str, object] = {**GOOD_COMPACT, "bpm": 120.0}
    with pytest.raises(UnexpectedModelBehavior, match="bpm must be exactly 97"):
        await generate(generator_returning([wrong_tempo]))


@pytest.mark.anyio
async def test_retry_exhaustion_reports_domain_validation_failures_too() -> None:
    # Domain errors (raised by to_song inside the validator) must surface the
    # same way as constraint violations, not vanish behind the generic message.
    overlapping: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            {
                "name": "Lead",
                "prog": 53,
                "voc": True,
                "notes": [
                    {"s": 0, "d": 2, "p": 62, "lyr": "La"},
                    {"s": 1, "d": 1, "p": 64, "lyr": " la"},  # overlaps
                ],
            },
            *GOOD_TRACKS,
        ],
    }
    with pytest.raises(UnexpectedModelBehavior, match="not monophonic"):
        await generate(generator_returning([overlapping]))


@pytest.mark.anyio
async def test_retry_exhaustion_names_the_attempt_the_rejection_came_from() -> None:
    # pydantic-ai's output-retry budget is shared with retry paths that never
    # reach our output validator (e.g. a tool-call payload that fails
    # CompactSong schema validation before _enforce runs). If the exhausting
    # attempt takes one of those paths, last_rejection can hold a stale value
    # from an earlier attempt — the message must say which attempt it is from
    # rather than implying it explains the exhaustion.
    wrong_tempo: dict[str, object] = {**GOOD_COMPACT, "bpm": 120.0}
    malformed: dict[str, object] = {"title": "incomplete"}
    with pytest.raises(
        UnexpectedModelBehavior, match=r"attempt 1\): bpm must be exactly 97"
    ):
        await generate(generator_returning([wrong_tempo, malformed]))


@pytest.mark.anyio
async def test_retry_exhaustion_formats_domain_validation_loc_readably() -> None:
    # err["loc"] is a tuple; every other error path in this codebase surfaces
    # human-readable text, so this must not leak a raw Python tuple repr.
    overlapping: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            {
                "name": "Lead",
                "prog": 53,
                "voc": True,
                "notes": [
                    {"s": 0, "d": 2, "p": 62, "lyr": "La"},
                    {"s": 1, "d": 1, "p": 64, "lyr": " la"},  # overlaps
                ],
            },
            *GOOD_TRACKS,
        ],
    }
    with pytest.raises(UnexpectedModelBehavior) as excinfo:
        await generate(generator_returning([overlapping]))
    message = str(excinfo.value)
    assert "song: Value error, vocal track 'Lead' is not monophonic" in message
    assert "()" not in message


@pytest.mark.anyio
async def test_included_sound_effect_is_allowed() -> None:
    request = GenerationRequest.model_validate(
        {**REQUEST, "include_instruments": ["Gunshot"], "exclude_instruments": []}
    )
    compact: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            {"name": "Gunshot", "prog": 127, "notes": [{"s": 0, "d": 1, "p": 60}]},
            *GOOD_TRACKS,
        ],
    }
    generator = generator_returning([compact])
    song = await generator.generate(request)
    assert song.allow_sound_effects
    assert 127 in {track.program for track in song.tracks}


@pytest.mark.anyio
async def test_user_message_states_all_hard_constraints() -> None:
    calls: list[str] = []
    await generate(generator_returning([GOOD_COMPACT], calls))
    message = calls[0]
    assert "Song prompt: a gentle waltz" in message
    assert "bpm = 97" in message
    assert "key = D" in message
    assert "ts = 3/4" in message
    assert "required instrument track: Flute (prog=73)" in message
    assert "forbidden program: 56 (Trumpet)" in message


@pytest.mark.anyio
async def test_forbidden_percussion_is_retried_until_removed() -> None:
    """Constraints.violations()'s forbid_percussion branch: a response with
    a percussion track must be rejected and retried when the request
    excludes drums."""
    request = GenerationRequest.model_validate(
        {**REQUEST, "include_instruments": [], "exclude_instruments": ["drums"]}
    )
    with_drums: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            *GOOD_TRACKS,
            {
                "name": "Drums",
                "prog": 0,
                "perc": True,
                "notes": [{"s": 0, "d": 1, "p": 36}],
            },
        ],
    }
    generator = generator_returning([with_drums, GOOD_COMPACT])
    song = await generator.generate(request)
    assert not any(track.is_percussion for track in song.tracks)


@pytest.mark.anyio
async def test_required_percussion_is_retried_until_present() -> None:
    """Constraints.violations()'s require_percussion branch: a response with
    no percussion track must be rejected and retried when the request
    requires drums."""
    request = GenerationRequest.model_validate(
        {
            **REQUEST,
            "include_instruments": ["Flute", "drums"],
            "exclude_instruments": [],
        }
    )
    with_drums: dict[str, object] = {
        **GOOD_COMPACT,
        "tracks": [
            *GOOD_TRACKS,
            {
                "name": "Drums",
                "prog": 0,
                "perc": True,
                "notes": [{"s": 0, "d": 1, "p": 36}],
            },
        ],
    }
    generator = generator_returning([GOOD_COMPACT, with_drums])
    song = await generator.generate(request)
    assert any(track.is_percussion for track in song.tracks)
