"""Canonical whole-song semantic composition contract.

This module owns musical intent and exact score time. It deliberately imports
no generation, MIDI, framework, persistence, or renderer implementation. The
live generator does not use this contract until a later approved slice.
"""

from __future__ import annotations

import json
from collections import Counter
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from math import gcd
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
    ),
]
StringIndex = Annotated[int, Field(ge=0, le=5)]
NoteIndex = Annotated[int, Field(ge=0)]

_MAX_RATIONAL_COMPONENT = 10_000_000
_MAX_COLLECTION = 256
_MAX_LYRIC_TOKENS = 10_000


class SemanticModel(BaseModel):
    """Closed, immutable base for canonical semantic data."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class Identified(Protocol):
    """Structural type for records held in an ID-addressed registry."""

    @property
    def id(self) -> str: ...


class Beat(SemanticModel):
    """An exact, reduced number of quarter-note beats.

    The JSON aliases keep repeated timing values compact while the Python names
    remain explicit. Durations use the same value object and are required to be
    positive by their owning model.
    """

    numerator: int = Field(
        alias="n",
        ge=0,
        le=_MAX_RATIONAL_COMPONENT,
        description="Non-negative numerator of a reduced beat fraction",
    )
    denominator: int = Field(
        alias="d",
        gt=0,
        le=_MAX_RATIONAL_COMPONENT,
        description="Positive denominator of a reduced beat fraction",
    )

    @model_validator(mode="after")
    def require_reduced_fraction(self) -> Self:
        if gcd(self.numerator, self.denominator) != 1:
            raise ValueError("beat fractions must be reduced")
        return self

    @property
    def value(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    @classmethod
    def from_value(cls, value: Fraction | int) -> Beat:
        fraction = Fraction(value)
        if fraction < 0:
            raise ValueError("beats cannot be negative")
        return cls(n=fraction.numerator, d=fraction.denominator)


class Meter(SemanticModel):
    """Score meter independent of any export format."""

    numerator: int = Field(ge=1, le=32)
    denominator: Literal[1, 2, 4, 8, 16, 32]

    @property
    def beats_per_bar(self) -> Fraction:
        return Fraction(self.numerator * 4, self.denominator)


class FormOccurrence(SemanticModel):
    """One ordered occurrence in the whole-song form."""

    id: EntityId
    label: str = Field(min_length=1, max_length=80)
    start: Beat
    duration: Beat

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.duration.value <= 0:
            raise ValueError("form occurrence duration must be positive")
        return self

    @property
    def end(self) -> Fraction:
        return self.start.value + self.duration.value


class IntentStatement(SemanticModel):
    """A separately attributable user directive or composer enhancement."""

    id: EntityId
    text: str = Field(min_length=1, max_length=1_000)
    occurrence_id: EntityId | None = None


class GuitarStrumStep(SemanticModel):
    """Canonical strum intent; performance offsets are not score time."""

    onset: Beat
    direction: Literal["down", "up"]
    articulation: Literal["open", "muted", "palm-muted", "power-chord"] = "open"
    sounding_strings: tuple[StringIndex, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=6,
    )

    @model_validator(mode="after")
    def require_ordered_unique_strings(self) -> Self:
        if self.sounding_strings is None:
            return self
        if self.sounding_strings != tuple(sorted(set(self.sounding_strings))):
            raise ValueError("sounding strings must be unique and ordered low to high")
        return self


class GuitarStrumPattern(SemanticModel):
    """A reusable guitar technique declared once in the pattern registry."""

    id: EntityId
    family: Literal["guitar-strum"] = "guitar-strum"
    duration: Beat
    steps: tuple[GuitarStrumStep, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_ordered_steps_within_pattern(self) -> Self:
        if self.duration.value <= 0:
            raise ValueError("pattern duration must be positive")
        onsets = tuple(step.onset.value for step in self.steps)
        if onsets != tuple(sorted(set(onsets))):
            raise ValueError("strum steps must have unique, increasing onsets")
        if onsets[-1] >= self.duration.value:
            raise ValueError("strum steps must start before the pattern ends")
        return self


class FrettedString(SemanticModel):
    """One sounding guitar string; omitted strings do not sound."""

    string_index: StringIndex
    fret: int = Field(ge=0, le=24)


class GuitarVoicing(SemanticModel):
    """A chord symbol with an explicit physical-string voicing."""

    chord_symbol: str = Field(min_length=1, max_length=32)
    strings: tuple[FrettedString, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def require_ordered_unique_strings(self) -> Self:
        indexes = tuple(string.string_index for string in self.strings)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("voicing strings must be unique and ordered low to high")
        return self


class GuitarPatternUse(SemanticModel):
    """Apply one registered guitar pattern within a form occurrence."""

    id: EntityId
    occurrence_id: EntityId
    pattern_id: EntityId
    start: Beat
    repetitions: int = Field(default=1, ge=1, le=1_024)
    voicing: GuitarVoicing


class GuitarPart(SemanticModel):
    """A chordal-string part with guitar-specific semantics."""

    family: Literal["guitar"] = "guitar"
    id: EntityId
    name: str = Field(min_length=1, max_length=80)
    tuning: Literal["standard"] = "standard"
    pattern_uses: tuple[GuitarPatternUse, ...] = Field(
        min_length=1, max_length=_MAX_COLLECTION
    )


class SpelledPitch(SemanticModel):
    """A notation-safe pitch that does not encode a MIDI note number."""

    step: Literal["C", "D", "E", "F", "G", "A", "B"]
    accidental: int = Field(default=0, ge=-2, le=2)
    octave: int = Field(ge=-1, le=9)


class SemanticNote(SemanticModel):
    """Exact melodic material that is not usefully represented as a pattern."""

    onset: Beat
    duration: Beat
    pitch: SpelledPitch
    dynamic: Literal["pp", "p", "mp", "mf", "f", "ff"] = "mf"
    articulation: Literal["normal", "legato", "staccato", "accent"] = "normal"

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.duration.value <= 0:
            raise ValueError("note duration must be positive")
        return self


class MelodicPhrase(SemanticModel):
    """An explicit monophonic motif, melody, or solo phrase."""

    id: EntityId
    occurrence_id: EntityId
    start: Beat
    notes: tuple[SemanticNote, ...] = Field(min_length=1, max_length=_MAX_COLLECTION)

    @model_validator(mode="after")
    def require_ordered_monophonic_notes(self) -> Self:
        _require_ordered_monophonic_notes(self.notes)
        return self


class MelodicPart(SemanticModel):
    """An explicit-note part for material that should not be compressed."""

    family: Literal["melodic"] = "melodic"
    id: EntityId
    name: str = Field(min_length=1, max_length=80)
    phrases: tuple[MelodicPhrase, ...] = Field(min_length=1, max_length=_MAX_COLLECTION)


class LyricSyllable(SemanticModel):
    """Performance spelling and note allocation for one displayed token."""

    text: str = Field(min_length=1, max_length=80)
    note_indexes: tuple[NoteIndex, ...] = Field(min_length=1, max_length=64)
    pronunciation: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_ordered_unique_note_indexes(self) -> Self:
        if self.note_indexes != tuple(sorted(set(self.note_indexes))):
            raise ValueError("syllable note indexes must be unique and ordered")
        return self


class LyricAssignment(SemanticModel):
    """Assign a source token to primary or supporting vocal performance."""

    id: EntityId
    token_id: EntityId
    role: Literal["primary", "harmony", "ad-lib"]
    syllables: tuple[LyricSyllable, ...] = Field(min_length=1, max_length=64)


class VocalPhrase(SemanticModel):
    """One monophonic vocal phrase in whole-song score time."""

    id: EntityId
    occurrence_id: EntityId
    start: Beat
    notes: tuple[SemanticNote, ...] = Field(min_length=1, max_length=_MAX_COLLECTION)
    lyric_assignments: tuple[LyricAssignment, ...] = Field(
        default=(), max_length=_MAX_LYRIC_TOKENS
    )

    @model_validator(mode="after")
    def require_ordered_monophonic_notes_and_valid_assignments(self) -> Self:
        _require_ordered_monophonic_notes(self.notes)

        claimed_indexes: list[int] = []
        for assignment in self.lyric_assignments:
            for syllable in assignment.syllables:
                claimed_indexes.extend(syllable.note_indexes)
        if any(index >= len(self.notes) for index in claimed_indexes):
            raise ValueError("lyric assignment references an unknown note index")
        if len(claimed_indexes) != len(set(claimed_indexes)):
            raise ValueError("a vocal note cannot carry multiple lyric assignments")
        return self


class VocalPart(SemanticModel):
    """A vocal part whose phrases reference immutable source lyric tokens."""

    family: Literal["vocal"] = "vocal"
    id: EntityId
    name: str = Field(min_length=1, max_length=80)
    phrases: tuple[VocalPhrase, ...] = Field(min_length=1, max_length=_MAX_COLLECTION)


SemanticPart = Annotated[
    GuitarPart | MelodicPart | VocalPart,
    Field(discriminator="family"),
]


class LyricToken(SemanticModel):
    """Immutable display text in source order."""

    id: EntityId
    occurrence_id: EntityId
    source_index: int = Field(
        ge=0,
        description=(
            "Zero-based position in the whole-song source stream; occurrence scope "
            "does not reset it."
        ),
    )
    display_text: str = Field(min_length=1, max_length=160)
    is_singable: bool = True


class GuitarBoundaryUse(SemanticModel):
    """A guitar pattern application that intentionally crosses a form boundary."""

    id: EntityId
    part_id: EntityId
    pattern_id: EntityId
    from_occurrence_id: EntityId
    to_occurrence_id: EntityId
    start: Beat
    duration: Beat
    voicing: GuitarVoicing

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.duration.value <= 0:
            raise ValueError("boundary use duration must be positive")
        return self


class RealizationIdentity(SemanticModel):
    """Explicit deterministic recipe identity; not canonical timing mutation."""

    recipe_version: str = Field(min_length=1, max_length=80)
    seed: int = 0


class SemanticScore(SemanticModel):
    """The one canonical whole-song composition artifact."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    id: EntityId
    title: str = Field(min_length=1, max_length=200)
    tempo_bpm: float = Field(ge=20, le=400)
    meter: Meter
    form: tuple[FormOccurrence, ...] = Field(min_length=1, max_length=64)
    user_directives: tuple[IntentStatement, ...] = Field(
        default=(), max_length=_MAX_COLLECTION
    )
    composer_enhancements: tuple[IntentStatement, ...] = Field(
        default=(), max_length=_MAX_COLLECTION
    )
    patterns: tuple[GuitarStrumPattern, ...] = Field(
        default=(), max_length=_MAX_COLLECTION
    )
    parts: tuple[SemanticPart, ...] = Field(min_length=1, max_length=64)
    lyric_tokens: tuple[LyricToken, ...] = Field(
        default=(), max_length=_MAX_LYRIC_TOKENS
    )
    boundary_uses: tuple[GuitarBoundaryUse, ...] = Field(
        default=(), max_length=_MAX_COLLECTION
    )
    realization: RealizationIdentity

    @model_validator(mode="after")
    def validate_whole_song_contract(self) -> Self:
        occurrences = self._validate_form()
        patterns = _unique_by_id(self.patterns, "pattern")
        parts = _unique_by_id(self.parts, "part")
        tokens = _unique_by_id(self.lyric_tokens, "lyric token")

        self._validate_intents(occurrences)
        self._validate_parts(occurrences, patterns)
        self._validate_boundaries(occurrences, patterns, parts)
        self._validate_lyrics(occurrences, tokens)
        self._validate_global_ids()
        return self

    def _validate_global_ids(self) -> None:
        ids: list[str] = [self.id]
        ids.extend(item.id for item in self.form)
        ids.extend(item.id for item in self.user_directives)
        ids.extend(item.id for item in self.composer_enhancements)
        ids.extend(item.id for item in self.patterns)
        ids.extend(item.id for item in self.parts)
        ids.extend(item.id for item in self.lyric_tokens)
        ids.extend(item.id for item in self.boundary_uses)
        for part in self.parts:
            if isinstance(part, GuitarPart):
                ids.extend(use.id for use in part.pattern_uses)
            else:
                ids.extend(phrase.id for phrase in part.phrases)
                if isinstance(part, VocalPart):
                    ids.extend(
                        assignment.id
                        for phrase in part.phrases
                        for assignment in phrase.lyric_assignments
                    )
        duplicates = sorted(
            item_id for item_id, count in Counter(ids).items() if count > 1
        )
        if duplicates:
            raise ValueError(f"semantic IDs must be globally unique: {duplicates}")

    def _validate_form(self) -> dict[str, FormOccurrence]:
        occurrences = _unique_by_id(self.form, "form occurrence")
        starts = tuple(occurrence.start.value for occurrence in self.form)
        if starts != tuple(sorted(starts)):
            raise ValueError("form occurrences must be ordered by start")
        if starts[0] != 0:
            raise ValueError("the first form occurrence must start at beat zero")

        beats_per_bar = self.meter.beats_per_bar
        for occurrence in self.form:
            if occurrence.start.value % beats_per_bar != 0:
                raise ValueError("form occurrences must start on bar lines")
            if occurrence.duration.value % beats_per_bar != 0:
                raise ValueError("form occurrence durations must contain whole bars")
        for previous, following in pairwise(self.form):
            if previous.end != following.start.value:
                raise ValueError(
                    "form occurrences must be contiguous and non-overlapping"
                )
        return occurrences

    def _validate_intents(self, occurrences: dict[str, FormOccurrence]) -> None:
        statements = (*self.user_directives, *self.composer_enhancements)
        _unique_by_id(statements, "intent statement")
        for statement in statements:
            if (
                statement.occurrence_id is not None
                and statement.occurrence_id not in occurrences
            ):
                raise ValueError(
                    f"intent statement {statement.id!r} references an unknown"
                    " occurrence"
                )

    def _validate_parts(
        self,
        occurrences: dict[str, FormOccurrence],
        patterns: dict[str, GuitarStrumPattern],
    ) -> None:
        use_ids: set[str] = set()
        phrase_ids: set[str] = set()
        for part in self.parts:
            if isinstance(part, GuitarPart):
                previous_end: Fraction | None = None
                for use in part.pattern_uses:
                    if use.id in use_ids:
                        raise ValueError(f"duplicate pattern use id: {use.id!r}")
                    use_ids.add(use.id)
                    occurrence = _known(occurrences, use.occurrence_id, "occurrence")
                    pattern = _known(patterns, use.pattern_id, "pattern")
                    _validate_pattern_voicing(pattern, use.voicing)
                    end = use.start.value + pattern.duration.value * use.repetitions
                    if use.start.value < occurrence.start.value or end > occurrence.end:
                        raise ValueError(
                            f"pattern use {use.id!r} falls outside its occurrence"
                        )
                    if previous_end is not None and use.start.value < previous_end:
                        raise ValueError(
                            "guitar pattern uses must be ordered and non-overlapping"
                        )
                    previous_end = end
            else:
                previous_phrase_end: Fraction | None = None
                for phrase in part.phrases:
                    if phrase.id in phrase_ids:
                        raise ValueError(f"duplicate phrase id: {phrase.id!r}")
                    phrase_ids.add(phrase.id)
                    occurrence = _known(occurrences, phrase.occurrence_id, "occurrence")
                    phrase_end = phrase.start.value + max(
                        note.onset.value + note.duration.value for note in phrase.notes
                    )
                    if (
                        phrase.start.value < occurrence.start.value
                        or phrase_end > occurrence.end
                    ):
                        raise ValueError(
                            f"phrase {phrase.id!r} falls outside its occurrence"
                        )
                    if (
                        previous_phrase_end is not None
                        and phrase.start.value < previous_phrase_end
                    ):
                        raise ValueError("phrases must be ordered and non-overlapping")
                    previous_phrase_end = phrase_end

    def _validate_boundaries(
        self,
        occurrences: dict[str, FormOccurrence],
        patterns: dict[str, GuitarStrumPattern],
        parts: dict[str, SemanticPart],
    ) -> None:
        _unique_by_id(self.boundary_uses, "boundary use")
        occurrence_indexes = {
            occurrence.id: index for index, occurrence in enumerate(self.form)
        }
        for boundary_use in self.boundary_uses:
            source = _known(
                occurrences, boundary_use.from_occurrence_id, "source occurrence"
            )
            target = _known(
                occurrences, boundary_use.to_occurrence_id, "target occurrence"
            )
            if occurrence_indexes[target.id] != occurrence_indexes[source.id] + 1:
                raise ValueError("boundary uses must reference adjacent occurrences")
            part = _known(parts, boundary_use.part_id, "part")
            if not isinstance(part, GuitarPart):
                raise ValueError("guitar boundary uses must reference a guitar part")
            pattern = _known(patterns, boundary_use.pattern_id, "pattern")
            _validate_pattern_voicing(pattern, boundary_use.voicing)
            boundary = target.start.value
            end = boundary_use.start.value + boundary_use.duration.value
            if not boundary_use.start.value < boundary < end:
                raise ValueError("boundary use must cross the referenced form boundary")
            if boundary_use.start.value < source.start.value or end > target.end:
                raise ValueError(
                    "boundary use must stay within its adjacent occurrences"
                )
            duration_ratio = boundary_use.duration.value / pattern.duration.value
            if duration_ratio.denominator != 1:
                raise ValueError(
                    "boundary use duration must contain complete pattern repetitions"
                )

    def _validate_lyrics(
        self,
        occurrences: dict[str, FormOccurrence],
        tokens: dict[str, LyricToken],
    ) -> None:
        source_indexes = tuple(token.source_index for token in self.lyric_tokens)
        if source_indexes != tuple(range(len(self.lyric_tokens))):
            raise ValueError("lyric tokens must have contiguous source indexes")
        for token in self.lyric_tokens:
            _known(occurrences, token.occurrence_id, "lyric occurrence")

        primary_performances: list[tuple[Fraction, int, str]] = []
        primary_counts: Counter[str] = Counter()
        assignment_ids: set[str] = set()
        for part in self.parts:
            if not isinstance(part, VocalPart):
                continue
            for phrase in part.phrases:
                for assignment in phrase.lyric_assignments:
                    if assignment.id in assignment_ids:
                        raise ValueError(
                            f"duplicate lyric assignment id: {assignment.id!r}"
                        )
                    assignment_ids.add(assignment.id)
                    token = _known(tokens, assignment.token_id, "lyric token")
                    if not token.is_singable:
                        raise ValueError(
                            "non-singable lyric tokens cannot be performed"
                        )
                    if token.occurrence_id != phrase.occurrence_id:
                        raise ValueError(
                            "lyric assignments must remain in their source occurrence"
                        )
                    if assignment.role != "primary":
                        continue
                    primary_counts[token.id] += 1
                    first_note_index = min(
                        index
                        for syllable in assignment.syllables
                        for index in syllable.note_indexes
                    )
                    primary_time = (
                        phrase.start.value + phrase.notes[first_note_index].onset.value
                    )
                    primary_performances.append(
                        (primary_time, token.source_index, token.id)
                    )

        expected_primary = [token for token in self.lyric_tokens if token.is_singable]
        expected_ids = [token.id for token in expected_primary]
        missing_or_duplicate = [
            token_id for token_id in expected_ids if primary_counts[token_id] != 1
        ]
        if missing_or_duplicate:
            raise ValueError(
                "every singable lyric token must have exactly one primary assignment: "
                f"{missing_or_duplicate}"
            )
        ordered_primary = sorted(primary_performances, key=lambda item: item[0])
        if any(
            previous[0] >= following[0]
            for previous, following in pairwise(ordered_primary)
        ):
            raise ValueError("primary lyric assignments need distinct ordered onsets")
        performed_indexes = [source_index for _, source_index, _ in ordered_primary]
        expected_indexes = [token.source_index for token in expected_primary]
        if performed_indexes != expected_indexes:
            raise ValueError("primary lyric assignments must follow source order")

    @property
    def display_lyrics(self) -> str:
        """Reconstruct the immutable user-facing text exactly."""
        return "".join(token.display_text for token in self.lyric_tokens)


def _require_ordered_monophonic_notes(notes: tuple[SemanticNote, ...]) -> None:
    onsets = tuple(note.onset.value for note in notes)
    if onsets != tuple(sorted(onsets)):
        raise ValueError("phrase notes must be ordered by onset")
    for previous, following in pairwise(notes):
        if previous.onset.value + previous.duration.value > following.onset.value:
            raise ValueError("phrase notes must be monophonic")


def _validate_pattern_voicing(
    pattern: GuitarStrumPattern, voicing: GuitarVoicing
) -> None:
    voicing_strings = {string.string_index for string in voicing.strings}
    for step in pattern.steps:
        selected_strings = set(step.sounding_strings or ())
        if selected_strings and not selected_strings.issubset(voicing_strings):
            raise ValueError(
                f"pattern {pattern.id!r} selects strings absent from the voicing"
            )


def _unique_by_id[T: Identified](items: tuple[T, ...], label: str) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for item in items:
        item_id = item.id
        if item_id in indexed:
            raise ValueError(f"duplicate {label} id: {item_id!r}")
        indexed[item_id] = item
    return indexed


def _known[T](items: dict[str, T], item_id: str, label: str) -> T:
    try:
        return items[item_id]
    except KeyError as error:
        raise ValueError(f"unknown {label} id: {item_id!r}") from error


def semantic_score_hash(score: SemanticScore) -> str:
    """Hash the exact canonical JSON form, including compact timing aliases."""
    payload = json.dumps(
        score.model_dump(mode="json", by_alias=True),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(payload).hexdigest()
