"""Supplied lyrics and sections are hard constraints on the generated song."""

from io import BytesIO

import pytest
from mido import MidiFile
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
from melos.domain.models import Song, TimeSignature
from melos.generation import ai
from melos.generation.ai import (
    ENFORCE_LYRIC_COMPLETENESS,
    Constraints,
    PydanticAISongGenerator,
)
from melos.generation.contract import CompactSong
from melos.generation.meta import MetaResolver, ResolvedMeta
from melos.midi.exporter import CHARSET, export_song

LYRICS = "[verse 1]\nCarry me home\n[chorus]\nInto the light"

REQUEST: dict[str, object] = {
    "prompt": "a folk ballad",
    "tempo_bpm": 100,
    "key": "C",
    "time_signature": {"numerator": 4, "denominator": 4},
    "lyrics": LYRICS,
}

VOCAL_NOTES: list[dict[str, object]] = [
    {"s": 0, "d": 1, "p": 60, "lyr": "Car"},
    {"s": 1, "d": 1, "p": 62, "lyr": "ry"},
    {"s": 2, "d": 1, "p": 64, "lyr": " me"},
    {"s": 3, "d": 1, "p": 65, "lyr": " home"},
    {"s": 4, "d": 1, "p": 64, "lyr": " In"},
    {"s": 5, "d": 1, "p": 62, "lyr": "to"},
    {"s": 6, "d": 1, "p": 60, "lyr": " the"},
    {"s": 7, "d": 1, "p": 59, "lyr": " light"},
]


def compact(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "Carry Me Home",
        "bpm": 100.0,
        "key": "C",
        "ts": "4/4",
        "tracks": [
            {"name": "Lead Vocal", "prog": 53, "voc": True, "notes": VOCAL_NOTES},
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ],
        "sections": [{"n": "verse 1", "s": 0}, {"n": "chorus", "s": 4}],
    }
    return base | overrides


def generator(
    payloads: list[dict[str, object]], calls: list[str] | None = None
) -> PydanticAISongGenerator:
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
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    def no_meta_call(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("meta LLM must not be called: all meta is supplied")

    return PydanticAISongGenerator(
        FunctionModel(respond),
        MetaResolver(FunctionModel(no_meta_call), use_native_output=False),
        use_native_output=False,
    )


async def generate(
    payloads: list[dict[str, object]],
    calls: list[str] | None = None,
    **request_overrides: object,
) -> Song:
    request = GenerationRequest.model_validate(REQUEST | request_overrides)
    return await generator(payloads, calls).generate(request)


@pytest.mark.anyio
async def test_supplied_lyrics_reach_the_midi_as_lyric_events() -> None:
    song = await generate([compact()])
    midi = MidiFile(file=BytesIO(export_song(song)), charset=CHARSET)
    vocal = midi.tracks[1]
    assert [msg.text for msg in vocal if msg.type == "lyrics"] == [
        note["lyr"] for note in VOCAL_NOTES
    ]
    # Every lyric event sits on a note onset.
    ticks: dict[str, list[int]] = {"lyrics": [], "note_on": []}
    tick = 0
    for msg in vocal:
        tick += msg.time
        if msg.type in ticks:
            ticks[msg.type].append(tick)
    assert set(ticks["lyrics"]) <= set(ticks["note_on"])


@pytest.mark.anyio
async def test_section_tags_become_markers_and_are_never_sung() -> None:
    song = await generate([compact()])
    midi = MidiFile(file=BytesIO(export_song(song)), charset=CHARSET)
    assert [m.text for m in midi.tracks[0] if m.type == "marker"] == [
        "verse 1",
        "chorus",
    ]
    sung = [m.text for track in midi.tracks for m in track if m.type == "lyrics"]
    assert not any("verse" in text or "chorus" in text for text in sung)


@pytest.mark.anyio
async def test_lyrics_on_a_non_vocal_track_are_retried() -> None:
    stray = compact(
        tracks=[
            {"name": "Lead Vocal", "prog": 53, "voc": True, "notes": VOCAL_NOTES},
            {
                "name": "Bass",
                "prog": 33,
                "notes": [{"s": 0, "d": 8, "p": 40, "lyr": "oops"}],
            },
        ]
    )
    calls: list[str] = []
    song = await generate([stray, compact()], calls)
    assert len(calls) == 2
    assert not any(
        note.lyric
        for track in song.tracks
        if not track.is_vocal
        for note in track.notes
    )


@pytest.mark.anyio
async def test_missing_vocal_track_is_retried() -> None:
    instrumental = compact(
        tracks=[
            {"name": "Piano", "prog": 0, "notes": [{"s": 0, "d": 8, "p": 60}]},
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ]
    )
    calls: list[str] = []
    await generate([instrumental, compact()], calls)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_incomplete_words_are_currently_accepted() -> None:
    """Completeness is DEFERRED to per-section generation (issue #39).

    One-shot generation cannot reproduce a real song's lyrics — measured 72% of
    404 words — so ``ENFORCE_LYRIC_COMPLETENESS`` is off and partial lyrics pass
    through unflagged. Invert this test (back to "retried until fixed") when
    per-section generation turns the flag on.
    """
    wrong = compact(
        tracks=[
            {
                "name": "Lead Vocal",
                "prog": 53,
                "voc": True,
                "notes": [{"s": 0, "d": 1, "p": 60, "lyr": "something else"}],
            },
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ]
    )
    calls: list[str] = []
    song = await generate([wrong], calls)
    assert not ENFORCE_LYRIC_COMPLETENESS
    assert len(calls) == 1  # accepted first time, no retry
    assert song.tracks[0].notes[0].lyric == "something else"


@pytest.mark.anyio
async def test_wrong_words_are_retried_once_completeness_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The completeness machinery still works — only the flag is off.

    Keeps the M3 behavior covered so re-enabling is a one-line change rather
    than a rediscovery of what the check was supposed to do.
    """
    monkeypatch.setattr(ai, "ENFORCE_LYRIC_COMPLETENESS", True)
    wrong = compact(
        tracks=[
            {
                "name": "Lead Vocal",
                "prog": 53,
                "voc": True,
                "notes": [{"s": 0, "d": 1, "p": 60, "lyr": "something else"}],
            },
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ]
    )
    calls: list[str] = []
    song = await generate([wrong, compact()], calls)
    assert len(calls) == 2  # rejected, then corrected
    assert song.tracks[0].notes[0].lyric == "Car"


@pytest.mark.anyio
async def test_persistently_wrong_words_exhaust_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The 502 path this produced for a full song is exactly why completeness is
    # deferred (issue #39); pinned under the flag so M3 inherits the coverage.
    monkeypatch.setattr(ai, "ENFORCE_LYRIC_COMPLETENESS", True)
    wrong = compact(
        tracks=[
            {
                "name": "Lead Vocal",
                "prog": 53,
                "voc": True,
                "notes": [{"s": 0, "d": 1, "p": 60, "lyr": "nope"}],
            },
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ]
    )
    with pytest.raises(UnexpectedModelBehavior):
        await generate([wrong])


@pytest.mark.anyio
async def test_melisma_and_split_syllables_accepted() -> None:
    # Same words, split differently, with a lyric-less note held mid-word.
    melisma: list[dict[str, object]] = [
        {"s": 0, "d": 1, "p": 60, "lyr": "Car"},
        {"s": 1, "d": 1, "p": 61},  # held, no syllable
        {"s": 2, "d": 1, "p": 62, "lyr": "ry-"},
        {"s": 3, "d": 1, "p": 64, "lyr": " me home"},
        {"s": 4, "d": 4, "p": 65, "lyr": " Into the light"},
    ]
    song = await generate(
        [
            compact(
                tracks=[
                    {"name": "Lead", "prog": 53, "voc": True, "notes": melisma},
                    {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
                ]
            )
        ]
    )
    assert song.tracks[0].is_vocal


@pytest.mark.anyio
async def test_backing_vocals_allowed_alongside_the_lead() -> None:
    backing: list[dict[str, object]] = [
        {"s": 4, "d": 2, "p": 67, "lyr": " In"},
        {"s": 6, "d": 2, "p": 69, "lyr": "to"},
    ]
    song = await generate(
        [
            compact(
                tracks=[
                    {"name": "Lead", "prog": 53, "voc": True, "notes": VOCAL_NOTES},
                    {"name": "Harmony", "prog": 53, "voc": True, "notes": backing},
                    {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
                ]
            )
        ]
    )
    assert sum(1 for track in song.tracks if track.is_vocal) == 2


@pytest.mark.anyio
async def test_unsingable_range_is_retried() -> None:
    too_low = [dict(note, p=30) for note in VOCAL_NOTES]
    calls: list[str] = []
    await generate(
        [
            compact(
                tracks=[
                    {"name": "Lead", "prog": 53, "voc": True, "notes": too_low},
                    {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
                ]
            ),
            compact(),
        ],
        calls,
    )
    assert len(calls) == 2


@pytest.mark.anyio
async def test_wrong_section_order_is_retried() -> None:
    swapped = compact(sections=[{"n": "chorus", "s": 0}, {"n": "verse 1", "s": 4}])
    calls: list[str] = []
    await generate([swapped, compact()], calls)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_instrumental_request_needs_no_vocals() -> None:
    instrumental = compact(
        tracks=[
            {"name": "Piano", "prog": 0, "notes": [{"s": 0, "d": 8, "p": 60}]},
            {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
        ],
        sections=[],
    )
    song = await generate([instrumental], lyrics=None)
    assert not any(track.is_vocal for track in song.tracks)


def test_closest_singer_is_picked_by_similarity_not_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry feedback must name the track that's actually closest to the
    wanted lyrics, not whichever vocal track happens to have more characters.

    Under the completeness flag (deferred — issue #39), so the feedback quality
    stays covered for when per-section generation switches it on.
    """
    monkeypatch.setattr(ai, "ENFORCE_LYRIC_COMPLETENESS", True)
    request = GenerationRequest.model_validate(
        {"prompt": "a song", "lyrics": "Carry me home tonight"}
    )
    meta = ResolvedMeta(
        tempo_bpm=100, key="C", time_signature=TimeSignature(numerator=4, denominator=4)
    )
    constraints = Constraints.from_request(request, meta)
    compact_song = CompactSong.model_validate(
        {
            "title": "T",
            "bpm": 100.0,
            "key": "C",
            "ts": "4/4",
            "tracks": [
                {  # genuinely closest: the same words, one short
                    "name": "Lead Vocal",
                    "prog": 53,
                    "voc": True,
                    "notes": [
                        {"s": 0, "d": 1, "p": 60, "lyr": "Carry"},
                        {"s": 1, "d": 1, "p": 62, "lyr": " me"},
                        {"s": 2, "d": 1, "p": 64, "lyr": " home"},
                    ],
                },
                {  # unrelated text, but longer once flattened
                    "name": "Harmony",
                    "prog": 53,
                    "voc": True,
                    "notes": [{"s": 0, "d": 1, "p": 60, "lyr": "zzzqqqqqqqqqq"}],
                },
                {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 8, "p": 40}]},
            ],
        }
    )
    problems = constraints.violations(compact_song)
    assert any("'Lead Vocal'" in problem for problem in problems)
    assert not any("'Harmony'" in problem for problem in problems)


@pytest.mark.anyio
async def test_lyrics_and_directives_reach_the_model_message() -> None:
    calls: list[str] = []
    await generate(
        [compact()],
        calls,
        lyrics=f"{LYRICS}\n{{soft brushed drums}}",
    )
    message = calls[0]
    assert "sections, in this exact order: ['verse 1', 'chorus']" in message
    assert "one voc=true track sings the lyrics" in message
    assert "soft brushed drums" in message  # directive, as guidance
    assert "Carry me home" in message  # full field, tags included
    assert "[verse 1]" in message
