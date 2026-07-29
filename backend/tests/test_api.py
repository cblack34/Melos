from collections.abc import Mapping
from io import BytesIO

import mido
import pytest
from fastapi.testclient import TestClient
from mido import MidiFile

from melos.api.app import create_app

client = TestClient(create_app())


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
    """GenerationRequest uses extra="forbid": an unsupported constraint (e.g.
    an instrument include/exclude filter, deferred to the LLM-generator
    milestone in issue #3) must fail loudly rather than being silently
    ignored (non-negotiable #4)."""
    payload = {"prompt": "x", "must_include_instruments": ["piano"]}
    assert client.post("/api/generate", json=payload).status_code == 422
