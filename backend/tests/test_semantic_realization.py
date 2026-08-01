"""Public behavioral contract for semantic-score deterministic realization."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from typing import Any

import mido
import pytest

from melos.domain.semantic import SemanticScore
from melos.midi.exporter import TICKS_PER_BEAT, export_song
from melos.realization import (
    RealizationError,
    _bound_guitar_attacks,
    _RawAttack,
    realize_score,
)


def beat(numerator: int, denominator: int = 1) -> dict[str, int]:
    return {"n": numerator, "d": denominator}


def representative_score_data() -> dict[str, Any]:
    """One whole-song G-C-Am-D score with melody and distributed vocals."""
    voicings = {
        "G": [(0, 3), (1, 2), (2, 0), (3, 0), (4, 0), (5, 3)],
        "C": [(1, 3), (2, 2), (3, 0), (4, 1), (5, 0)],
        "Am": [(1, 0), (2, 2), (3, 2), (4, 1), (5, 0)],
        "D": [(2, 0), (3, 2), (4, 3), (5, 2)],
    }

    def voicing(chord: str) -> dict[str, object]:
        return {
            "chord_symbol": chord,
            "strings": [
                {"string_index": string_index, "fret": fret}
                for string_index, fret in voicings[chord]
            ],
        }

    note = {
        "onset": beat(0),
        "duration": beat(1),
        "pitch": {"step": "G", "octave": 4},
    }
    return {
        "schema_version": "0.2.0",
        "id": "realization-fixture",
        "title": "Realization Fixture",
        "tempo_bpm": 120,
        "key": "G",
        "meter": {"numerator": 4, "denominator": 4},
        "form": [
            {"id": "verse", "label": "Verse", "start": beat(0), "duration": beat(8)},
            {"id": "chorus", "label": "Chorus", "start": beat(8), "duration": beat(8)},
        ],
        "patterns": [
            {
                "id": "dduudu",
                "duration": beat(4),
                "steps": [
                    {
                        "onset": beat(0),
                        "direction": "down",
                        "emphasis": "secondary",
                    },
                    {
                        "onset": beat(1),
                        "direction": "down",
                        "emphasis": "primary",
                    },
                    {"onset": beat(3, 2), "direction": "up"},
                    {"onset": beat(5, 2), "direction": "up"},
                    {
                        "onset": beat(3),
                        "direction": "down",
                        "emphasis": "primary",
                    },
                    {"onset": beat(7, 2), "direction": "up"},
                ],
            }
        ],
        "parts": [
            {
                "family": "guitar",
                "id": "guitar",
                "name": "Acoustic guitar",
                "instrument": "acoustic-guitar",
                "pattern_uses": [
                    {
                        "id": f"{chord.lower()}-use",
                        "occurrence_id": "verse" if index < 2 else "chorus",
                        "pattern_id": "dduudu",
                        "start": beat(index * 4),
                        "voicing": voicing(chord),
                    }
                    for index, chord in enumerate(("G", "C", "Am", "D"))
                ],
            },
            {
                "family": "melodic",
                "id": "melody",
                "name": "Melody",
                "instrument": "lead-synth",
                "phrases": [
                    {
                        "id": "melody-verse",
                        "occurrence_id": "verse",
                        "start": beat(0),
                        "notes": [
                            {**note, "duration": beat(1, 3)},
                            {
                                **note,
                                "onset": beat(1, 3),
                                "duration": beat(1, 3),
                                "pitch": {"step": "A", "octave": 4},
                            },
                            {
                                **note,
                                "onset": beat(2, 3),
                                "duration": beat(1, 3),
                                "pitch": {"step": "B", "octave": 4},
                            },
                        ],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "lead",
                "name": "Lead",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "lead-phrase",
                        "occurrence_id": "chorus",
                        "start": beat(8),
                        "notes": [note],
                        "lyric_assignments": [
                            {
                                "id": "primary-we",
                                "token_id": "token-we",
                                "role": "primary",
                                "syllables": [
                                    {
                                        "text": "We",
                                        "pronunciation": "wi",
                                        "note_indexes": [0],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "answer",
                "name": "Answer",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "answer-phrase",
                        "occurrence_id": "chorus",
                        "start": beat(10),
                        "notes": [note],
                        "lyric_assignments": [
                            {
                                "id": "primary-rise",
                                "token_id": "token-rise",
                                "role": "primary",
                                "syllables": [{"text": "rise", "note_indexes": [0]}],
                            }
                        ],
                    }
                ],
            },
        ],
        "lyric_tokens": [
            {
                "id": "token-we",
                "occurrence_id": "chorus",
                "source_index": 0,
                "display_text": "We",
            },
            {
                "id": "token-rise",
                "occurrence_id": "chorus",
                "source_index": 1,
                "display_text": " rise",
            },
        ],
        "boundary_uses": [
            {
                "id": "boundary-strum",
                "operation": "replace",
                "part_id": "guitar",
                "pattern_id": "dduudu",
                "from_occurrence_id": "verse",
                "to_occurrence_id": "chorus",
                "start": beat(7),
                "duration": beat(4),
                "voicing": voicing("Am"),
            }
        ],
        "realization": {"recipe_version": "semantic-realization-v1", "seed": 7},
    }


def representative_score() -> SemanticScore:
    return SemanticScore.model_validate(representative_score_data())


def test_realization_preserves_exact_grid_tuplets_and_semantic_midi_evidence() -> None:
    realized = realize_score(representative_score())
    song = realized.song
    melody = next(track for track in song.tracks if track.name == "Melody")

    assert TICKS_PER_BEAT == 480
    assert [(note.start, note.duration, note.pitch) for note in melody.notes] == [
        (0, 1 / 3, 67),
        (1 / 3, 1 / 3, 69),
        (2 / 3, 1 / 3, 71),
    ]
    assert all((note.start * TICKS_PER_BEAT).is_integer() for note in melody.notes)
    assert all((note.duration * TICKS_PER_BEAT).is_integer() for note in melody.notes)
    assert song.key == "G"
    assert song.time_signature.numerator == 4
    assert song.time_signature.denominator == 4
    assert [(section.name, section.start_beat) for section in song.sections] == [
        ("Verse", 0),
        ("Chorus", 8),
    ]


def test_guitar_recipe_has_standard_tuning_direction_offsets_and_velocity_contour() -> (
    None
):
    realized = realize_score(representative_score())
    attacks = [attack for attack in realized.attacks if attack.part_id == "guitar"]
    first_down = [attack for attack in attacks if attack.canonical_onset == 0]
    accented_down = [attack for attack in attacks if attack.canonical_onset == 1]
    first_up = [attack for attack in attacks if attack.canonical_onset == 1.5]

    assert [attack.pitch for attack in first_down] == [43, 47, 50, 55, 59, 67]
    assert [attack.string_index for attack in first_down] == [0, 1, 2, 3, 4, 5]
    assert [attack.string_index for attack in first_up] == [5, 4, 3, 2, 1, 0]
    assert [
        attack.performance_onset - attack.canonical_onset for attack in first_down
    ] == pytest.approx([0, 0.025, 0.05, 0.075, 0.1, 0.125])
    assert [attack.velocity for attack in first_down] == [112, 98, 90, 84, 80, 76]
    assert [attack.velocity for attack in accented_down] == [120, 106, 98, 92, 88, 84]
    assert [attack.velocity for attack in first_up] == [100, 86, 78, 72, 68, 64]
    assert {attack.emphasis for attack in accented_down} == {"primary"}


def test_boundary_replaces_ordinary_attacks_and_bounds_equal_pitches_by_pitch() -> None:
    realized = realize_score(representative_score())
    guitar = next(
        track for track in realized.song.tracks if track.name == "Acoustic guitar"
    )
    at_boundary = [
        attack
        for attack in realized.attacks
        if attack.part_id == "guitar" and attack.canonical_onset == 8
    ]

    assert len(at_boundary) == len(
        {(attack.performance_onset, attack.pitch) for attack in at_boundary}
    )
    assert (
        len(at_boundary) == 5
    )  # Boundary Am replaces ordinary attacks inside its interval.
    by_pitch = sorted(
        (note for note in guitar.notes if note.pitch == 64), key=lambda note: note.start
    )
    assert all(
        previous.start + previous.duration <= following.start
        for previous, following in pairwise(by_pitch)
    )


def test_exact_simultaneous_same_pitch_attacks_coalesce_deterministically() -> None:
    common = {
        "part_id": "guitar",
        "canonical_tick": 480,
        "performance_tick": 486,
        "pitch": 64,
        "direction": "down",
        "emphasis": "none",
    }
    bounded = _bound_guitar_attacks(
        (
            _RawAttack(
                **common,
                source_id="first",
                nominal_end_tick=720,
                velocity=81,
                string_index=3,
            ),
            _RawAttack(
                **common,
                source_id="second",
                nominal_end_tick=760,
                velocity=96,
                string_index=4,
            ),
        )
    )

    assert len(bounded) == 1
    assert bounded[0].source_id == "first"
    assert bounded[0].velocity == 96
    assert bounded[0].nominal_end_tick == 760


def test_realization_is_deterministic_and_exports_display_lyrics() -> None:
    first = realize_score(representative_score())
    second = realize_score(representative_score())

    assert first.song == second.song
    assert first.score_hash == second.score_hash
    assert first.recipe_hash == second.recipe_hash
    assert first.song_hash == second.song_hash
    assert first.score_hash == (
        "79f640f083755e3381986ce9349d8ffa86c98b1d5f2a076b47cf508465a25342"
    )
    assert first.recipe_hash == (
        "95c568d151f428c7a16f1a5a9bb3d2a91df92dffce7fc4fd432a7a073b068138"
    )
    assert first.song_hash == (
        "d2d973514b5647ab2d0efc4b52a7e3f9cc8d285c3af3f7784e18a445faf9ee3d"
    )
    midi_bytes = export_song(first.song)
    assert midi_bytes == export_song(second.song)
    assert hashlib.sha256(midi_bytes).hexdigest() == (
        "624c8f09d0d3874a65c58f41ad7af9f44a6afd9cd77abdbecd6c48c112126af9"
    )
    midi = mido.MidiFile(file=BytesIO(midi_bytes))
    lyric_events = [
        message.text
        for track in midi.tracks
        for message in track
        if message.type == "lyrics"
    ]
    assert lyric_events == ["We", " rise"]
    assert "".join(lyric_events) == "We rise"
    vocals = [track for track in first.song.tracks if track.is_vocal]
    assert [track.program for track in vocals] == [53, 53]
    assert all(track.is_vocal for track in vocals)
    meta = midi.tracks[0]
    assert (
        next(message.key for message in meta if message.type == "key_signature") == "G"
    )
    assert [message.text for message in meta if message.type == "marker"] == [
        "Verse",
        "Chorus",
    ]
    programs = [
        next(message.program for message in track if message.type == "program_change")
        for track in midi.tracks[1:]
    ]
    assert programs == [25, 80, 53, 53]


def test_realization_is_the_only_semantic_to_performance_dependency_seam() -> None:
    source = Path(__file__).parents[1] / "src" / "melos" / "realization" / "__init__.py"
    text = source.read_text()

    assert "melos.domain.semantic" in text
    assert "melos.domain.models" in text
    assert "melos.midi" not in text


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda data: data["parts"][0].update(instrument="unmapped-guitar"),
            "instrument",
        ),
        (
            lambda data: data["realization"].update(recipe_version="missing-recipe"),
            "recipe",
        ),
    ],
)
def test_realization_reports_precise_unmapped_instrument_and_recipe_errors(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    data = representative_score_data()
    mutate(data)
    with pytest.raises(RealizationError, match=message):
        realize_score(SemanticScore.model_validate(data))


def test_realization_rejects_non_grid_score_time_without_rounding() -> None:
    data = representative_score_data()
    melody = data["parts"][1]["phrases"][0]["notes"][2]
    melody["onset"] = beat(5, 7)
    melody["duration"] = beat(1, 7)

    with pytest.raises(RealizationError, match=r"480.*grid"):
        realize_score(SemanticScore.model_validate(data))


def test_realization_rejects_articulation_that_creates_a_fractional_tick() -> None:
    data = representative_score_data()
    melody = data["parts"][1]["phrases"][0]["notes"][2]
    melody["duration"] = beat(1, 480)
    melody["articulation"] = "staccato"

    with pytest.raises(RealizationError, match=r"staccato.*480.*grid"):
        realize_score(SemanticScore.model_validate(data))
