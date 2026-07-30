"""Sections, vocal-track rules, and their MIDI representation."""

from io import BytesIO

import pytest
from mido import MidiFile
from pydantic import ValidationError

from melos.domain.models import Note, Section, Song, TimeSignature, Track
from melos.generation.contract import CompactSong, to_song
from melos.midi.exporter import CHARSET, export_song


def melody(**overrides: object) -> Track:
    defaults: dict[str, object] = {
        "name": "Lead Vocal",
        "program": 53,
        "is_vocal": True,
        "notes": [
            Note(start=0.0, duration=1.0, pitch=64, lyric="Sing"),
            Note(start=1.0, duration=1.0, pitch=67, lyric=" it"),
        ],
    }
    return Track.model_validate(defaults | overrides)


def backing() -> Track:
    return Track(
        name="Bass",
        program=33,
        notes=[Note(start=0.0, duration=2.0, pitch=40)],
    )


def song(**overrides: object) -> Song:
    defaults: dict[str, object] = {
        "title": "Sectioned",
        "tempo_bpm": 100,
        "key": "C",
        "time_signature": TimeSignature(numerator=4, denominator=4),
        "tracks": [melody(), backing()],
    }
    return Song.model_validate(defaults | overrides)


def parse(data: bytes) -> MidiFile:
    return MidiFile(file=BytesIO(data), charset=CHARSET)


# --- vocal tracks ----------------------------------------------------------


def test_vocal_track_may_not_be_percussion() -> None:
    with pytest.raises(ValidationError, match="both vocal and percussion"):
        melody(is_percussion=True)


def test_overlapping_notes_rejected_on_vocal_track() -> None:
    overlapping = [
        Note(start=0.0, duration=2.0, pitch=64),
        Note(start=1.0, duration=1.0, pitch=67),  # starts before the first ends
    ]
    with pytest.raises(ValidationError, match="not monophonic"):
        melody(notes=overlapping)


def test_touching_notes_allowed_on_vocal_track() -> None:
    touching = [
        Note(start=0.0, duration=1.0, pitch=64),
        Note(start=1.0, duration=1.0, pitch=67),
    ]
    assert melody(notes=touching)


def test_sub_tick_overlap_allowed_on_vocal_track() -> None:
    # 480 ticks/beat means one tick is ~0.0021 beats; an overlap smaller than
    # that is below the exporter's resolution and must not be rejected as
    # non-monophonic (see BEAT_EPSILON in domain/models.py).
    sub_tick_overlap = [
        Note(start=0.0, duration=1.0005, pitch=64),
        Note(start=1.0, duration=1.0, pitch=67),
    ]
    assert melody(notes=sub_tick_overlap)


def test_unordered_notes_still_checked_for_overlap() -> None:
    # Overlap must be detected regardless of the order notes arrive in.
    with pytest.raises(ValidationError, match="not monophonic"):
        melody(
            notes=[
                Note(start=1.0, duration=1.0, pitch=67),
                Note(start=0.0, duration=2.0, pitch=64),
            ]
        )


def test_non_vocal_tracks_may_be_polyphonic() -> None:
    chord = [
        Note(start=0.0, duration=2.0, pitch=60),
        Note(start=0.0, duration=2.0, pitch=64),
        Note(start=0.0, duration=2.0, pitch=67),
    ]
    assert Track(name="Choir Pad", program=52, notes=chord)


# --- sections --------------------------------------------------------------


def test_sections_export_as_markers_at_the_right_ticks() -> None:
    long_melody = melody(
        notes=[Note(start=float(i), duration=1.0, pitch=64) for i in range(16)]
    )
    sectioned = song(
        tracks=[long_melody, backing()],
        sections=[
            Section(name="verse 1", start_beat=0),
            Section(name="chorus", start_beat=4),
            Section(name="verse 2", start_beat=8),
            Section(name="chorus", start_beat=12),  # repeats are expected
        ],
    )
    meta = parse(export_song(sectioned)).tracks[0]

    markers = [(msg.text, msg.time) for msg in meta if msg.type == "marker"]
    assert [name for name, _ in markers] == ["verse 1", "chorus", "verse 2", "chorus"]
    # Deltas: first at tick 0, then one bar (4 beats * 480) apart.
    assert [delta for _, delta in markers] == [0, 1920, 1920, 1920]


def test_marker_text_survives_non_latin_script() -> None:
    sectioned = song(sections=[Section(name="サビ", start_beat=0)])
    meta = parse(export_song(sectioned)).tracks[0]
    assert [msg.text for msg in meta if msg.type == "marker"] == ["サビ"]


def test_song_without_sections_has_no_markers() -> None:
    meta = parse(export_song(song())).tracks[0]
    assert not [msg for msg in meta if msg.type == "marker"]


def test_sections_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="ordered by start_beat"):
        song(
            sections=[
                Section(name="chorus", start_beat=4),
                Section(name="verse", start_beat=0),
            ]
        )


def test_first_section_must_start_at_zero() -> None:
    with pytest.raises(ValidationError, match="must start at beat 0"):
        song(sections=[Section(name="verse", start_beat=4)])


def test_section_past_the_end_of_the_song_rejected() -> None:
    with pytest.raises(ValidationError, match="past the end"):
        song(
            sections=[
                Section(name="verse", start_beat=0),
                Section(name="outro", start_beat=64),  # song is 2 beats long
            ]
        )


def test_sections_must_land_on_bar_lines() -> None:
    long_melody = melody(
        notes=[Note(start=float(i), duration=1.0, pitch=64) for i in range(8)]
    )
    with pytest.raises(ValidationError, match="bar line"):
        song(
            tracks=[long_melody, backing()],
            sections=[
                Section(name="verse", start_beat=0),
                Section(name="chorus", start_beat=5.5),
            ],
        )


def test_bar_alignment_follows_the_time_signature() -> None:
    # 6/8 is three quarter-note beats per bar, so beat 3 is a bar line.
    long_melody = melody(
        notes=[Note(start=float(i), duration=1.0, pitch=64) for i in range(8)]
    )
    assert song(
        time_signature=TimeSignature(numerator=6, denominator=8),
        tracks=[long_melody, backing()],
        sections=[
            Section(name="verse", start_beat=0),
            Section(name="chorus", start_beat=3),
        ],
    )
    with pytest.raises(ValidationError, match="bar line"):
        song(
            time_signature=TimeSignature(numerator=6, denominator=8),
            tracks=[long_melody, backing()],
            sections=[
                Section(name="verse", start_beat=0),
                Section(name="chorus", start_beat=4),  # a bar line in 4/4, not 6/8
            ],
        )


# --- compact contract ------------------------------------------------------

COMPACT: dict[str, object] = {
    "title": "Compact Sections",
    "bpm": 100,
    "key": "C",
    "ts": "4/4",
    "tracks": [
        {
            "name": "Lead Vocal",
            "prog": 53,
            "voc": True,
            "notes": [
                {"s": 0, "d": 1, "p": 64, "lyr": "Sing"},
                {"s": 4, "d": 1, "p": 67, "lyr": " it"},
            ],
        },
        {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 4, "p": 40}]},
    ],
    "sections": [{"n": "verse 1", "s": 0}, {"n": "chorus", "s": 4}],
}


def test_compact_sections_and_vocal_flag_map_to_domain() -> None:
    mapped = to_song(CompactSong.model_validate(COMPACT))
    assert [(s.name, s.start_beat) for s in mapped.sections] == [
        ("verse 1", 0),
        ("chorus", 4),
    ]
    assert mapped.tracks[0].is_vocal
    assert not mapped.tracks[1].is_vocal


def test_compact_defaults_to_unsectioned_non_vocal() -> None:
    bare = {key: value for key, value in COMPACT.items() if key != "sections"}
    bare["tracks"] = [
        {"name": "Piano", "prog": 0, "notes": [{"s": 0, "d": 1, "p": 60}]},
        {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 4, "p": 40}]},
    ]
    mapped = to_song(CompactSong.model_validate(bare))
    assert mapped.sections == []
    assert not any(track.is_vocal for track in mapped.tracks)


def test_domain_section_rules_gate_compact_payloads() -> None:
    misaligned = COMPACT | {
        "sections": [{"n": "verse", "s": 0}, {"n": "chorus", "s": 3}]
    }
    with pytest.raises(ValidationError, match="bar line"):
        to_song(CompactSong.model_validate(misaligned))
