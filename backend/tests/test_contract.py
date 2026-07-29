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
        {"title": "x" * 201},  # trust-boundary size caps
        {"tracks": [MELODY_TRACK] * 17},
    ],
)
def test_invalid_compact_payloads_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(**bad))


def test_extra_keys_rejected_at_every_level() -> None:
    smuggled_channel = {**MELODY_TRACK, "channel": 3}
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[smuggled_channel, DRUMS_TRACK]))

    smuggled_note_field = {
        **MELODY_TRACK,
        "notes": [{"s": 0, "d": 1, "p": 64, "chan": 3}],
    }
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[smuggled_note_field, DRUMS_TRACK]))


def test_note_beat_positions_are_bounded() -> None:
    runaway = {**MELODY_TRACK, "notes": [{"s": 1e9, "d": 1, "p": 60}]}
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[runaway, DRUMS_TRACK]))


def test_note_end_position_is_bounded_even_when_s_and_d_are_individually_valid() -> (
    None
):
    doubled_end = {**MELODY_TRACK, "notes": [{"s": 10_000, "d": 10_000, "p": 60}]}
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[doubled_end, DRUMS_TRACK]))


def test_note_count_per_track_is_bounded() -> None:
    flood = {
        **MELODY_TRACK,
        "notes": [{"s": i * 0.1, "d": 0.1, "p": 60} for i in range(5_001)],
    }
    with pytest.raises(ValidationError):
        CompactSong.model_validate(payload(tracks=[flood, DRUMS_TRACK]))


def test_allow_sound_effects_is_not_a_schema_field() -> None:
    with pytest.raises(ValidationError, match="allow_sound_effects"):
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


def test_melodic_track_count_over_domain_cap_rejected_by_to_song() -> None:
    # schema allows 16 tracks, domain caps melodic tracks at 15
    all_melodic = payload(tracks=[MELODY_TRACK] * 16)
    with pytest.raises(ValidationError):
        to_song(CompactSong.model_validate(all_melodic))


def test_time_signature_numerator_out_of_domain_range_rejected_by_to_song() -> None:
    out_of_range = payload(ts="0/4")  # passes the regex, fails TimeSignature's ge=1
    with pytest.raises(ValidationError):
        to_song(CompactSong.model_validate(out_of_range))
