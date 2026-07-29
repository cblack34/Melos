from io import BytesIO

import mido
import pytest
from mido import MidiFile
from pydantic import ValidationError

from melos.generation.contract import CompactSong, to_song
from melos.midi.exporter import export_song

MELODY_TRACK: dict[str, object] = {
    "name": "Melody",
    "prog": 73,
    "notes": [
        {"s": 0, "d": 1, "p": 64, "lyr": "Hum"},
        {"s": 1, "d": 2, "p": 67, "v": 70, "lyr": "ming"},
    ],
}
DRUMS_TRACK: dict[str, object] = {
    "name": "Drums",
    "prog": 0,
    "perc": True,
    "notes": [{"s": 0, "d": 0.5, "p": 36}],
}
COMPACT_PAYLOAD: dict[str, object] = {
    "title": "Contract Trip",
    "bpm": 91,
    "key": "Em",
    "ts": "6/8",
    "tracks": [MELODY_TRACK, DRUMS_TRACK],
}


def payload(**overrides: object) -> dict[str, object]:
    return {**COMPACT_PAYLOAD, **overrides}


def test_compact_json_round_trips_to_parseable_midi() -> None:
    song = to_song(CompactSong.model_validate(payload()))
    midi = MidiFile(file=BytesIO(export_song(song)))

    assert midi.type == 1 and len(midi.tracks) == 3
    meta = {msg.type: msg for msg in midi.tracks[0]}
    assert meta["set_tempo"].tempo == mido.bpm2tempo(91)
    assert meta["key_signature"].key == "Em"
    assert (meta["time_signature"].numerator, meta["time_signature"].denominator) == (
        6,
        8,
    )
    assert [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"] == [
        "Hum",
        "ming",
    ]


def test_defaults_applied() -> None:
    song = to_song(CompactSong.model_validate(payload()))
    first_note = song.tracks[0].notes[0]
    assert first_note.velocity == 96  # compact default
    assert song.tracks[1].is_percussion


@pytest.mark.parametrize(
    "bad",
    [
        {"ts": "4/3"},  # non-power-of-two denominator blocked at the schema
        {"ts": "waltz"},
        {"bpm": 500},
        {"key": "H"},
        {"tracks": []},
        {"unexpected": 1},  # extra="forbid"
    ],
)
def test_invalid_compact_payloads_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(**bad))


def test_extra_keys_rejected_at_every_level() -> None:
    smuggled_channel = {**MELODY_TRACK, "channel": 3}
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[smuggled_channel, DRUMS_TRACK]))


def test_llm_cannot_authorize_sound_effects() -> None:
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(allow_sound_effects=True))


def test_sound_effect_program_rejected_unless_caller_allows() -> None:
    gunshot = payload(
        tracks=[
            {"name": "FX", "prog": 127, "notes": [{"s": 0, "d": 1, "p": 60}]},
            DRUMS_TRACK,
        ]
    )
    compact = CompactSong.model_validate(gunshot)
    with pytest.raises(ValidationError, match="sound-effect"):
        to_song(compact)
    assert to_song(compact, allow_sound_effects=True)


def test_domain_rules_still_gate_mapped_songs() -> None:
    two_drums = payload(tracks=[DRUMS_TRACK, DRUMS_TRACK])
    with pytest.raises(ValidationError):
        to_song(CompactSong.model_validate(two_drums))
