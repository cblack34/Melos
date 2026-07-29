from collections.abc import Mapping
from io import BytesIO

import mido
from fastapi.testclient import TestClient
from mido import MidiFile

from melos.api.app import create_app

client = TestClient(create_app())


def generate(payload: Mapping[str, object]) -> bytes:
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;") and '.mid"' in disposition
    return response.content


def test_generate_returns_multi_track_midi() -> None:
    midi = MidiFile(file=BytesIO(generate({"prompt": "a happy tune"})))
    assert midi.type == 1
    assert len(midi.tracks) == 4  # meta + melody + bass + drums
    lyrics = [msg for track in midi.tracks for msg in track if msg.type == "lyrics"]
    assert lyrics


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


def test_out_of_range_tempo_rejected() -> None:
    payload = {"prompt": "x", "tempo_bpm": 999}
    assert client.post("/api/generate", json=payload).status_code == 422
