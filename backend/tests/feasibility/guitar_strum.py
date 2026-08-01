"""Pure, deliberately small evidence model for the guitar-strum feasibility gate.

This experiment does not propose a production semantic-score API.  It records
only the intent that the acceptance fixture needs and expands that intent into
Note-compatible performance data without importing Melos production modules.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StringIndex = Literal[0, 1, 2, 3, 4, 5]  # 0 is low E, 5 is high E.
StrumDirection = Literal["down", "up"]


class ExperimentalModel(BaseModel):
    """Immutable and closed input/output records for repeatable evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class StringPitch(ExperimentalModel):
    """One standard-tuned guitar string, including its fretboard decision."""

    string_index: StringIndex
    fret: int = Field(ge=0, le=24)
    pitch: int = Field(ge=0, le=127)


class GuitarVoicing(ExperimentalModel):
    """Explicit sounding strings for one chord; omitted strings are absent."""

    chord_symbol: Literal["G", "C", "Am", "D"]
    strings: tuple[StringPitch, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def require_low_to_high_unique_strings(self) -> GuitarVoicing:
        indexes = tuple(string.string_index for string in self.strings)
        if indexes != tuple(sorted(indexes)) or len(set(indexes)) != len(indexes):
            raise ValueError("voicing strings must be unique and ordered low to high")
        return self


class StrumStep(ExperimentalModel):
    """A canonical chord beat and its intentional strum-direction technique."""

    onset_in_bar: float = Field(ge=0, lt=4)
    direction: StrumDirection


class StrumPattern(ExperimentalModel):
    """Reusable D/D/U/U/D/U pattern in a four-quarter-note bar."""

    name: str = Field(min_length=1)
    steps: tuple[StrumStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_strictly_ordered_unique_steps(self) -> StrumPattern:
        onsets = tuple(step.onset_in_bar for step in self.steps)
        if onsets != tuple(sorted(set(onsets))):
            raise ValueError("strum steps must have unique, increasing onsets")
        return self


class PerformanceRecipe(ExperimentalModel):
    """Declared, deterministic offsets and velocity contour; never randomness."""

    version: str = Field(min_length=1)
    seed: int = 0
    per_string_offset_beats: float = Field(gt=0, lt=0.1)
    attack_velocities: tuple[int, ...] = Field(min_length=1, max_length=6)
    note_duration_beats: float = Field(gt=0)

    @model_validator(mode="after")
    def require_valid_attack_velocities(self) -> PerformanceRecipe:
        if any(velocity < 1 or velocity > 127 for velocity in self.attack_velocities):
            raise ValueError("attack velocities must be valid MIDI velocities")
        return self


class BarOccurrence(ExperimentalModel):
    """A bar in the whole-context fixture, retaining its canonical chord onset."""

    section_id: str = Field(min_length=1)
    bar_start: float = Field(ge=0)
    voicing: GuitarVoicing


class GuitarFixture(ExperimentalModel):
    """Enough whole-song context to demonstrate normal and boundary expansion."""

    pattern: StrumPattern
    recipe: PerformanceRecipe
    bars: tuple[BarOccurrence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_ordered_bar_aligned_context(self) -> GuitarFixture:
        starts = tuple(bar.bar_start for bar in self.bars)
        if starts != tuple(sorted(starts)) or len(set(starts)) != len(starts):
            raise ValueError("bar starts must be unique and ordered")
        if any(start % 4 != 0 for start in starts):
            raise ValueError("fixture bars must start on four-beat bar lines")
        return self


class PerformanceEvent(ExperimentalModel):
    """The narrow Note-compatible event shape produced by this experiment."""

    canonical_chord_onset: float = Field(ge=0)
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    string_index: StringIndex
    direction: StrumDirection


def expand_guitar_fixture(fixture: GuitarFixture) -> tuple[PerformanceEvent, ...]:
    """Expand every bar with context retained in its one fixture input."""
    events: list[PerformanceEvent] = []
    for bar in fixture.bars:
        for step in fixture.pattern.steps:
            ordered_strings = bar.voicing.strings
            if step.direction == "up":
                ordered_strings = tuple(reversed(ordered_strings))
            canonical_onset = bar.bar_start + step.onset_in_bar
            for attack_index, string in enumerate(ordered_strings):
                events.append(
                    PerformanceEvent(
                        canonical_chord_onset=canonical_onset,
                        start=canonical_onset
                        + attack_index * fixture.recipe.per_string_offset_beats,
                        duration=fixture.recipe.note_duration_beats,
                        pitch=string.pitch,
                        velocity=fixture.recipe.attack_velocities[
                            attack_index % len(fixture.recipe.attack_velocities)
                        ],
                        string_index=string.string_index,
                        direction=step.direction,
                    )
                )
    return _end_strings_at_next_attack(events)


def _end_strings_at_next_attack(
    events: list[PerformanceEvent],
) -> tuple[PerformanceEvent, ...]:
    """Let a string ring until its next attack, including across section markers."""
    ordered_events = sorted(
        events,
        key=lambda event: (
            event.start,
            event.canonical_chord_onset,
            event.string_index,
            event.pitch,
        ),
    )
    next_attack_by_string: dict[StringIndex, float] = {}
    bounded_events: list[PerformanceEvent] = []
    for event in reversed(ordered_events):
        next_attack = next_attack_by_string.get(event.string_index)
        duration = event.duration
        if next_attack is not None:
            duration = min(duration, next_attack - event.start)
        event_data = event.model_dump()
        event_data["duration"] = duration
        bounded_events.append(PerformanceEvent.model_validate(event_data))
        next_attack_by_string[event.string_index] = event.start
    return tuple(reversed(bounded_events))


def event_hash(events: tuple[PerformanceEvent, ...]) -> str:
    """Stable evidence hash of the exact expanded performance data."""
    payload = [event.model_dump(mode="json") for event in events]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def serialized_size(value: BaseModel | tuple[PerformanceEvent, ...]) -> int:
    """Return deterministic UTF-8 JSON size for feasibility comparisons."""
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else [event.model_dump(mode="json") for event in value]
    )
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def standard_gcad_fixture() -> GuitarFixture:
    """Four bars of standard G, C, Am, D voicings with the shared strum."""
    return GuitarFixture(
        pattern=StrumPattern(
            name="dduudu",
            steps=(
                StrumStep(onset_in_bar=0.0, direction="down"),
                StrumStep(onset_in_bar=1.0, direction="down"),
                StrumStep(onset_in_bar=1.5, direction="up"),
                StrumStep(onset_in_bar=2.5, direction="up"),
                StrumStep(onset_in_bar=3.0, direction="down"),
                StrumStep(onset_in_bar=3.5, direction="up"),
            ),
        ),
        recipe=PerformanceRecipe(
            version="guitar-feasibility-v1",
            per_string_offset_beats=0.0125,
            attack_velocities=(96, 91, 86, 81, 76, 71),
            # The final up-strum deliberately rings over the next section marker.
            note_duration_beats=1.0,
        ),
        bars=(
            BarOccurrence(
                section_id="verse-1",
                bar_start=0,
                voicing=GuitarVoicing(
                    chord_symbol="G",
                    strings=(
                        StringPitch(string_index=0, fret=3, pitch=43),
                        StringPitch(string_index=1, fret=2, pitch=47),
                        StringPitch(string_index=2, fret=0, pitch=50),
                        StringPitch(string_index=3, fret=0, pitch=55),
                        StringPitch(string_index=4, fret=0, pitch=59),
                        StringPitch(string_index=5, fret=3, pitch=67),
                    ),
                ),
            ),
            BarOccurrence(
                section_id="verse-1",
                bar_start=4,
                voicing=GuitarVoicing(
                    chord_symbol="C",
                    strings=(
                        StringPitch(string_index=1, fret=3, pitch=48),
                        StringPitch(string_index=2, fret=2, pitch=52),
                        StringPitch(string_index=3, fret=0, pitch=55),
                        StringPitch(string_index=4, fret=1, pitch=60),
                        StringPitch(string_index=5, fret=0, pitch=64),
                    ),
                ),
            ),
            BarOccurrence(
                section_id="chorus-1",
                bar_start=8,
                voicing=GuitarVoicing(
                    chord_symbol="Am",
                    strings=(
                        StringPitch(string_index=1, fret=0, pitch=45),
                        StringPitch(string_index=2, fret=2, pitch=52),
                        StringPitch(string_index=3, fret=2, pitch=57),
                        StringPitch(string_index=4, fret=1, pitch=60),
                        StringPitch(string_index=5, fret=0, pitch=64),
                    ),
                ),
            ),
            BarOccurrence(
                section_id="chorus-1",
                bar_start=12,
                voicing=GuitarVoicing(
                    chord_symbol="D",
                    strings=(
                        StringPitch(string_index=2, fret=0, pitch=50),
                        StringPitch(string_index=3, fret=2, pitch=57),
                        StringPitch(string_index=4, fret=3, pitch=62),
                        StringPitch(string_index=5, fret=2, pitch=66),
                    ),
                ),
            ),
        ),
    )
