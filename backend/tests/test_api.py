from collections.abc import Mapping
from io import BytesIO

import mido
import pytest
from fastapi.testclient import TestClient
from mido import MidiFile

from melos.api.app import create_app
from melos.generation.stub import StubSongGenerator

client = TestClient(create_app(StubSongGenerator()))


def generate(payload: Mapping[str, object]) -> bytes:
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"
    disposition = response.headers["content-disposition"]
    # The stub's title is deterministic ("Melos Sketch"), so the filename is
    # knowable exactly rather than just checked for a ".mid" suffix.
    assert disposition == 'attachment; filename="melos-sketch.mid"'
    return response.content


def test_generate_returns_multi_track_midi() -> None:
    midi = MidiFile(file=BytesIO(generate({"prompt": "a happy tune"})))
    assert midi.type == 1
    assert len(midi.tracks) == 4  # meta + melody + bass + drums
    names = [msg.name for t in midi.tracks[1:] for msg in t if msg.type == "track_name"]
    assert names == ["Melody", "Bass", "Drums"]
    melody_lyrics = [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"]
    assert melody_lyrics  # lyrics specifically on the melody track
    other_lyrics = [
        msg.text for t in midi.tracks[2:] for msg in t if msg.type == "lyrics"
    ]
    assert not other_lyrics  # bass/drums carry no lyrics


def test_generate_honors_request_meta() -> None:
    payload = {
        "prompt": "waltz please",
        "tempo_bpm": 97,
        "key": "D",
        "time_signature": {"numerator": 3, "denominator": 4},
    }
    midi = MidiFile(file=BytesIO(generate(payload)))
    meta = {msg.type: msg for msg in midi.tracks[0]}
    assert meta["set_tempo"].tempo == mido.bpm2tempo(97)
    assert meta["key_signature"].key == "D"
    assert (meta["time_signature"].numerator, meta["time_signature"].denominator) == (
        3,
        4,
    )


def test_empty_prompt_rejected() -> None:
    assert client.post("/api/generate", json={"prompt": ""}).status_code == 422


def test_whitespace_only_prompt_rejected() -> None:
    assert client.post("/api/generate", json={"prompt": "   "}).status_code == 422


def test_out_of_range_tempo_rejected() -> None:
    payload = {"prompt": "x", "tempo_bpm": 999}
    assert client.post("/api/generate", json=payload).status_code == 422


@pytest.mark.parametrize("tempo_bpm", [20, 400])
def test_tempo_at_valid_boundary_accepted(tempo_bpm: float) -> None:
    payload = {"prompt": "x", "tempo_bpm": tempo_bpm}
    assert client.post("/api/generate", json=payload).status_code == 200


@pytest.mark.parametrize("tempo_bpm", [19.99, 400.01])
def test_tempo_just_outside_boundary_rejected(tempo_bpm: float) -> None:
    payload = {"prompt": "x", "tempo_bpm": tempo_bpm}
    assert client.post("/api/generate", json=payload).status_code == 422


def test_unknown_field_rejected() -> None:
    """GenerationRequest uses extra="forbid": an unsupported constraint must
    fail loudly rather than being silently ignored (non-negotiable #4)."""
    payload = {"prompt": "x", "mood": "happy"}
    assert client.post("/api/generate", json=payload).status_code == 422


def test_instrument_constraints_honored_by_stub() -> None:
    payload = {
        "prompt": "trumpet tune, no drums",
        "include_instruments": ["Trumpet"],
        "exclude_instruments": ["drums", "Flute"],
    }
    midi = MidiFile(file=BytesIO(generate(payload)))
    programs = {
        msg.program
        for track in midi.tracks
        for msg in track
        if msg.type == "program_change" and msg.channel != 9
    }
    channels = {
        msg.channel for track in midi.tracks for msg in track if msg.type == "note_on"
    }
    assert 56 in programs  # Trumpet present
    assert 73 not in programs  # Flute excluded
    assert 9 not in channels  # no percussion


def test_unknown_instrument_name_rejected() -> None:
    payload = {"prompt": "x", "include_instruments": ["Keytar of Destiny"]}
    assert client.post("/api/generate", json=payload).status_code == 422


def test_include_exclude_overlap_rejected() -> None:
    payload = {
        "prompt": "x",
        "include_instruments": ["Flute"],
        "exclude_instruments": ["flute"],
    }
    assert client.post("/api/generate", json=payload).status_code == 422


def test_percussion_synonym_overlap_rejected() -> None:
    """ "Drums" and "percussion" are the same pseudo-instrument
    (domain/gm.py's ``is_percussion_name``); requiring one while forbidding
    the other must 422, not silently drop the percussion track (stub) or
    generate an unsatisfiable constraint pair (AI backend)."""
    payload = {
        "prompt": "x",
        "include_instruments": ["drums"],
        "exclude_instruments": ["percussion"],
    }
    assert client.post("/api/generate", json=payload).status_code == 422


def test_prompt_too_long_rejected() -> None:
    payload = {"prompt": "x" * 4001}
    assert client.post("/api/generate", json=payload).status_code == 422


def test_included_instrument_colliding_with_default_program_gets_renamed() -> None:
    """Flute is the stub's default melody program (73); requesting it must
    still produce a track named "Flute", not leave it named "Melody"."""
    payload = {"prompt": "x", "include_instruments": ["Flute"]}
    midi = MidiFile(file=BytesIO(generate(payload)))
    names = [msg.name for t in midi.tracks[1:] for msg in t if msg.type == "track_name"]
    assert "Flute" in names
    assert "Melody" not in names


def test_stub_sings_requested_lyrics() -> None:
    """The stub previously ignored ``lyrics`` entirely and always sang its
    canned syllables; it must now reflect the user's actual words so a
    developer using MELOS_GENERATION_BACKEND=stub sees the lyrics UI work."""
    payload = {"prompt": "x", "lyrics": "hello world"}
    midi = MidiFile(file=BytesIO(generate(payload)))
    melody_lyrics = [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"]
    assert melody_lyrics == ["hello", "world"]


def test_stub_emits_sections_matching_lyric_tags() -> None:
    payload = {"prompt": "x", "lyrics": "[verse 1]\nhello\n[chorus]\nworld"}
    midi = MidiFile(file=BytesIO(generate(payload)))
    markers = [msg.text for msg in midi.tracks[0] if msg.type == "marker"]
    assert markers == ["verse 1", "chorus"]


def test_included_sound_effect_does_not_crash_stub() -> None:
    """Sound-effect programs (GM 120-127) are melodic-track-illegal unless
    Song.allow_sound_effects is set; the stub must set it when the request
    explicitly asks for one, not 500 on an unset default."""
    payload = {"prompt": "x", "include_instruments": ["Gunshot"]}
    midi = MidiFile(file=BytesIO(generate(payload)))
    programs = {
        msg.program
        for track in midi.tracks
        for msg in track
        if msg.type == "program_change"
    }
    assert 127 in programs
