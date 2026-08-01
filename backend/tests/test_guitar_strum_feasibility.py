from io import BytesIO
from itertools import pairwise
from pathlib import Path

import mido
import pytest
from feasibility.guitar_midi_fixture import (
    guitar_fixture_song,
    note_compatible_events,
    write_guitar_fixture_midi,
)
from feasibility.guitar_strum import (
    GuitarFixture,
    PerformanceEvent,
    PerformanceRecipe,
    StrumPattern,
    StrumStep,
    event_hash,
    expand_guitar_fixture,
    serialized_size,
    standard_gcad_fixture,
)

from melos.midi.exporter import export_song


def test_standard_fixture_preserves_voicings_and_strum_directions() -> None:
    fixture = standard_gcad_fixture()
    assert [bar.voicing.chord_symbol for bar in fixture.bars] == ["G", "C", "Am", "D"]
    string_orders = [
        [string.string_index for string in bar.voicing.strings] for bar in fixture.bars
    ]
    assert string_orders == [
        [0, 1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5],
        [2, 3, 4, 5],
    ]
    assert [step.direction for step in fixture.pattern.steps] == [
        "down",
        "down",
        "up",
        "up",
        "down",
        "up",
    ]
    assert [step.onset_in_bar for step in fixture.pattern.steps] == [
        0,
        1,
        1.5,
        2.5,
        3,
        3.5,
    ]


def test_strum_steps_must_be_unique_and_ordered() -> None:
    with pytest.raises(ValueError, match="unique, increasing onsets"):
        StrumPattern(
            name="invalid",
            steps=(
                StrumStep(onset_in_bar=1, direction="down"),
                StrumStep(onset_in_bar=1, direction="up"),
            ),
        )


def test_down_and_up_strums_use_opposite_sounding_string_order() -> None:
    fixture = standard_gcad_fixture()
    events = expand_guitar_fixture(fixture)
    down = [event for event in events if event.canonical_chord_onset == 0]
    up = [event for event in events if event.canonical_chord_onset == 1.5]
    assert [event.string_index for event in down] == [0, 1, 2, 3, 4, 5]
    assert [event.string_index for event in up] == [5, 4, 3, 2, 1, 0]
    assert [event.start for event in down] == pytest.approx(
        [0, 0.0125, 0.025, 0.0375, 0.05, 0.0625]
    )
    assert [event.velocity for event in down] == [96, 91, 86, 81, 76, 71]


def test_canonical_chord_onsets_are_separate_from_per_string_offsets() -> None:
    fixture = standard_gcad_fixture()
    events = expand_guitar_fixture(fixture)
    first_down = [event for event in events if event.canonical_chord_onset == 4]
    assert {event.canonical_chord_onset for event in first_down} == {4}
    offsets = sorted(event.start - event.canonical_chord_onset for event in first_down)
    assert offsets == pytest.approx([0, 0.0125, 0.025, 0.0375, 0.05])


def test_overlapping_strum_spreads_are_bounded_in_chronological_order() -> None:
    standard = standard_gcad_fixture()
    fixture = GuitarFixture(
        pattern=StrumPattern(
            name="close-strokes",
            steps=(
                StrumStep(onset_in_bar=0, direction="down"),
                StrumStep(onset_in_bar=0.01, direction="up"),
            ),
        ),
        recipe=PerformanceRecipe(
            version="close-strokes-v1",
            per_string_offset_beats=0.09,
            attack_velocities=(96,),
            note_duration_beats=1,
        ),
        bars=(standard.bars[0],),
    )

    events = expand_guitar_fixture(fixture)

    assert [event.start for event in events] == sorted(event.start for event in events)
    assert all(event.duration > 0 for event in events)
    _assert_no_same_string_overlaps(events)


def test_identical_fixture_has_identical_events_and_hash() -> None:
    fixture = standard_gcad_fixture()
    assert GuitarFixture.model_validate_json(fixture.model_dump_json()) == fixture
    first = expand_guitar_fixture(fixture)
    second = expand_guitar_fixture(standard_gcad_fixture())
    assert first == second
    assert event_hash(first) == event_hash(second)
    assert serialized_size(standard_gcad_fixture()) < serialized_size(first)


def test_section_boundary_context_has_continuous_tail_and_one_next_attack() -> None:
    events = expand_guitar_fixture(standard_gcad_fixture())
    before_boundary = [event for event in events if event.canonical_chord_onset == 7.5]
    at_boundary = [event for event in events if event.canonical_chord_onset == 8]
    assert max(event.start + event.duration for event in before_boundary) > 8
    assert len(at_boundary) == 5
    assert len({event.string_index for event in at_boundary}) == 5
    assert min(event.start for event in at_boundary) == 8
    _assert_no_same_string_overlaps(events)
    _assert_boundary_note_off_precedes_retrigger()


def _assert_no_same_string_overlaps(events: tuple[PerformanceEvent, ...]) -> None:
    string_events = sorted(events, key=lambda event: (event.string_index, event.start))
    for previous, following in pairwise(string_events):
        if previous.string_index != following.string_index:
            continue
        assert previous.start + previous.duration <= following.start


def _assert_boundary_note_off_precedes_retrigger() -> None:
    midi = mido.MidiFile(file=BytesIO(export_song(guitar_fixture_song())))
    guitar_track = midi.tracks[1]
    absolute_tick = 0
    messages_at_retrigger_tick = []
    for message in guitar_track:
        absolute_tick += message.time
        if absolute_tick == round(8.05 * midi.ticks_per_beat):
            messages_at_retrigger_tick.append(message)
    assert [(message.type, message.note) for message in messages_at_retrigger_tick] == [
        ("note_off", 64),
        ("note_on", 64),
    ]


def test_narrow_song_midi_conversion_and_explicit_writer(tmp_path: Path) -> None:
    events = expand_guitar_fixture(standard_gcad_fixture())
    notes = note_compatible_events(events)
    assert [note.model_dump(exclude={"lyric"}) for note in notes] == [
        event.model_dump(include={"start", "duration", "pitch", "velocity"})
        for event in events
    ]
    song = guitar_fixture_song()
    assert len(export_song(song)) > 0
    destination = tmp_path / "guitar-feasibility.mid"
    assert write_guitar_fixture_midi(destination) == destination
    assert destination.read_bytes() == export_song(song)
