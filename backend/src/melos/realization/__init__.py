"""Deterministic realization of canonical semantic scores.

This outer adapter is the only production seam that knows both the canonical
semantic contract and the existing MIDI-shaped ``Song`` performance model.
It deliberately does not import the MIDI exporter.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from fractions import Fraction
from hashlib import sha256
from itertools import groupby, pairwise
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from melos.domain.models import Note, Section, Song, TimeSignature, Track
from melos.domain.semantic import (
    Beat,
    GuitarBoundaryUse,
    GuitarPart,
    GuitarPatternUse,
    GuitarStrumPattern,
    LyricToken,
    MelodicPart,
    SemanticNote,
    SemanticScore,
    SpelledPitch,
    VocalPart,
    semantic_score_hash,
)

TICKS_PER_BEAT = 480
_STANDARD_TUNING = (40, 45, 50, 55, 59, 64)
_DYNAMIC_VELOCITY = {"pp": 40, "p": 52, "mp": 66, "mf": 80, "f": 96, "ff": 112}
_ARTICULATION_VELOCITY = {"normal": 0, "legato": 0, "staccato": 0, "accent": 10}
_ARTICULATION_DURATION = {
    "normal": Fraction(1),
    "legato": Fraction(1),
    "staccato": Fraction(1, 2),
    "accent": Fraction(1),
}
_GUITAR_DURATION = {
    "open": 480,
    "muted": 120,
    "palm-muted": 240,
    "power-chord": 360,
}
_GUITAR_VELOCITY = {"open": 0, "muted": -8, "palm-muted": -4, "power-chord": 4}
_GUITAR_DIRECTION_VELOCITY = {"down": 0, "up": -8}
_GUITAR_EMPHASIS_VELOCITY = {"none": 0, "secondary": 4, "primary": 12}


class RealizationError(ValueError):
    """The validated score cannot be realized by the selected local recipe."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GuitarAttack(_FrozenModel):
    """Inspectable guitar performance evidence before MIDI serialization."""

    part_id: str
    source_id: str
    canonical_onset: float
    performance_onset: float
    duration: float
    pitch: int
    velocity: int
    string_index: int
    direction: Literal["down", "up"]
    emphasis: Literal["none", "secondary", "primary"]


class RealizationResult(_FrozenModel):
    """Realized performance plus stable evidence identities."""

    song: Song
    attacks: tuple[GuitarAttack, ...]
    score_hash: str
    recipe_hash: str
    song_hash: str


class _TrackRecipe(_FrozenModel):
    instrument: str
    program: int
    is_vocal: bool = False


class _Recipe(_FrozenModel):
    version: str
    string_offset_ticks: int
    attack_velocities: tuple[int, ...]
    instruments: tuple[_TrackRecipe, ...]


_RECIPES: Mapping[str, _Recipe] = MappingProxyType(
    {
        "semantic-realization-v1": _Recipe(
            version="semantic-realization-v1",
            string_offset_ticks=12,
            attack_velocities=(108, 94, 86, 80, 76, 72),
            instruments=(
                _TrackRecipe(instrument="acoustic-guitar", program=25),
                _TrackRecipe(instrument="lead-synth", program=80),
                _TrackRecipe(instrument="voice", program=53, is_vocal=True),
            ),
        )
    }
)


class _RawAttack(_FrozenModel):
    part_id: str
    source_id: str
    canonical_tick: int
    performance_tick: int
    nominal_end_tick: int
    pitch: int
    velocity: int
    string_index: int
    direction: Literal["down", "up"]
    emphasis: Literal["none", "secondary", "primary"]


def realize_score(score: SemanticScore) -> RealizationResult:
    """Realize the complete score through one deterministic, whole-song pass."""
    recipe = _recipe(score.realization.recipe_version)
    _validate_form_grid(score)
    lyric_chunks = _primary_display_chunks(score.lyric_tokens)
    tracks: list[Track] = []
    attacks: list[GuitarAttack] = []

    for part in score.parts:
        track_recipe = _track_recipe(recipe, part.instrument)
        if isinstance(part, GuitarPart):
            if track_recipe.is_vocal:
                raise RealizationError(
                    f"instrument {part.instrument!r} cannot realize a guitar part"
                )
            track, part_attacks = _realize_guitar(score, part, recipe, track_recipe)
            tracks.append(track)
            attacks.extend(part_attacks)
        elif isinstance(part, MelodicPart):
            if track_recipe.is_vocal:
                raise RealizationError(
                    f"instrument {part.instrument!r} cannot realize a melodic part"
                )
            tracks.append(_realize_melodic(part, track_recipe))
        elif isinstance(part, VocalPart):
            if not track_recipe.is_vocal:
                raise RealizationError(
                    f"instrument {part.instrument!r} cannot realize a vocal part"
                )
            tracks.append(_realize_vocal(part, score, lyric_chunks, track_recipe))

    if len(tracks) < 2:
        raise RealizationError("semantic realization requires at least two tracks")
    sections = [
        Section(name=occurrence.label, start_beat=_beat_float(occurrence.start, "form"))
        for occurrence in score.form
    ]
    try:
        song = Song(
            title=score.title,
            tempo_bpm=score.tempo_bpm,
            key=score.key,
            time_signature=TimeSignature(
                numerator=score.meter.numerator,
                denominator=score.meter.denominator,
            ),
            tracks=tracks,
            sections=sections,
        )
    except ValidationError as error:
        raise RealizationError(f"realized Song is invalid: {error}") from error

    return RealizationResult(
        song=song,
        attacks=tuple(attacks),
        score_hash=semantic_score_hash(score),
        recipe_hash=_recipe_hash(recipe),
        song_hash=_json_hash(song.model_dump(mode="json")),
    )


def _recipe(version: str) -> _Recipe:
    try:
        return _RECIPES[version]
    except KeyError as error:
        raise RealizationError(f"unknown realization recipe: {version!r}") from error


def _track_recipe(recipe: _Recipe, instrument: str) -> _TrackRecipe:
    track = next(
        (item for item in recipe.instruments if item.instrument == instrument),
        None,
    )
    if track is None:
        raise RealizationError(f"unmapped semantic instrument: {instrument!r}")
    return track


def _validate_form_grid(score: SemanticScore) -> None:
    for occurrence in score.form:
        _tick(occurrence.start.value, f"form occurrence {occurrence.id!r} start")
        _tick(occurrence.duration.value, f"form occurrence {occurrence.id!r} duration")


def _realize_guitar(
    score: SemanticScore,
    part: GuitarPart,
    recipe: _Recipe,
    track_recipe: _TrackRecipe,
) -> tuple[Track, tuple[GuitarAttack, ...]]:
    patterns = {pattern.id: pattern for pattern in score.patterns}
    intervals = _replacement_intervals(score.boundary_uses, part.id)
    ordinary: list[_RawAttack] = []
    for use in part.pattern_uses:
        ordinary.extend(_expand_pattern(use, patterns[use.pattern_id], part.id, recipe))
    ordinary = [
        attack
        for attack in ordinary
        if not any(start <= attack.canonical_tick < end for start, end in intervals)
    ]

    boundary_attacks: list[_RawAttack] = []
    for boundary in score.boundary_uses:
        if boundary.part_id != part.id:
            continue
        pattern = patterns[boundary.pattern_id]
        duration_ticks = _beat_tick(boundary.duration, f"boundary {boundary.id!r}")
        pattern_ticks = _beat_tick(pattern.duration, f"pattern {pattern.id!r}")
        use = GuitarPatternUse(
            id=boundary.id,
            occurrence_id=boundary.from_occurrence_id,
            pattern_id=boundary.pattern_id,
            start=boundary.start,
            repetitions=duration_ticks // pattern_ticks,
            voicing=boundary.voicing,
        )
        boundary_attacks.extend(_expand_pattern(use, pattern, part.id, recipe))

    bounded = _bound_guitar_attacks((*ordinary, *boundary_attacks))
    notes = [
        Note(
            start=attack.performance_tick / TICKS_PER_BEAT,
            duration=(attack.nominal_end_tick - attack.performance_tick)
            / TICKS_PER_BEAT,
            pitch=attack.pitch,
            velocity=attack.velocity,
        )
        for attack in bounded
    ]
    evidence = tuple(
        GuitarAttack(
            part_id=attack.part_id,
            source_id=attack.source_id,
            canonical_onset=attack.canonical_tick / TICKS_PER_BEAT,
            performance_onset=attack.performance_tick / TICKS_PER_BEAT,
            duration=(attack.nominal_end_tick - attack.performance_tick)
            / TICKS_PER_BEAT,
            pitch=attack.pitch,
            velocity=attack.velocity,
            string_index=attack.string_index,
            direction=attack.direction,
            emphasis=attack.emphasis,
        )
        for attack in bounded
    )
    return (
        Track(name=part.name, program=track_recipe.program, notes=notes),
        evidence,
    )


def _replacement_intervals(
    boundaries: tuple[GuitarBoundaryUse, ...], part_id: str
) -> tuple[tuple[int, int], ...]:
    intervals = sorted(
        (
            _beat_tick(boundary.start, f"boundary {boundary.id!r}"),
            _beat_tick(boundary.start, f"boundary {boundary.id!r}")
            + _beat_tick(boundary.duration, f"boundary {boundary.id!r}"),
        )
        for boundary in boundaries
        if boundary.part_id == part_id
    )
    if any(previous[1] > following[0] for previous, following in pairwise(intervals)):
        raise RealizationError("replacement boundary intervals cannot overlap")
    return tuple(intervals)


def _expand_pattern(
    use: GuitarPatternUse,
    pattern: GuitarStrumPattern,
    part_id: str,
    recipe: _Recipe,
) -> list[_RawAttack]:
    use_tick = _beat_tick(use.start, f"pattern use {use.id!r}")
    pattern_ticks = _beat_tick(pattern.duration, f"pattern {pattern.id!r}")
    voicing = {string.string_index: string.fret for string in use.voicing.strings}
    attacks: list[_RawAttack] = []
    for repetition in range(use.repetitions):
        repetition_tick = use_tick + repetition * pattern_ticks
        for step in pattern.steps:
            canonical_tick = repetition_tick + _beat_tick(
                step.onset, f"pattern {pattern.id!r} step"
            )
            selected = tuple(step.sounding_strings or voicing)
            ordered = (
                selected if step.direction == "down" else tuple(reversed(selected))
            )
            for attack_index, string_index in enumerate(ordered):
                pitch = _STANDARD_TUNING[string_index] + voicing[string_index]
                if not 0 <= pitch <= 127:
                    raise RealizationError(
                        f"guitar pitch outside MIDI performance range: {pitch}"
                    )
                performance_tick = (
                    canonical_tick + attack_index * recipe.string_offset_ticks
                )
                velocity = _clamp_velocity(
                    recipe.attack_velocities[
                        attack_index % len(recipe.attack_velocities)
                    ]
                    + _GUITAR_VELOCITY[step.articulation]
                    + _GUITAR_DIRECTION_VELOCITY[step.direction]
                    + _GUITAR_EMPHASIS_VELOCITY[step.emphasis]
                )
                attacks.append(
                    _RawAttack(
                        part_id=part_id,
                        source_id=use.id,
                        canonical_tick=canonical_tick,
                        performance_tick=performance_tick,
                        nominal_end_tick=performance_tick
                        + _GUITAR_DURATION[step.articulation],
                        pitch=pitch,
                        velocity=velocity,
                        string_index=string_index,
                        direction=step.direction,
                        emphasis=step.emphasis,
                    )
                )
    return attacks


def _bound_guitar_attacks(attacks: tuple[_RawAttack, ...]) -> tuple[_RawAttack, ...]:
    ordered = sorted(
        attacks,
        key=lambda attack: (
            attack.performance_tick,
            attack.pitch,
            attack.canonical_tick,
            attack.source_id,
            attack.string_index,
        ),
    )
    next_attack_by_pitch: dict[int, int] = {}
    next_attack_by_string: dict[int, int] = {}
    bounded: list[_RawAttack] = []
    grouped_by_tick = [
        tuple(group)
        for _, group in groupby(ordered, key=lambda attack: attack.performance_tick)
    ]
    for simultaneous in reversed(grouped_by_tick):
        bounded_simultaneous: list[_RawAttack] = []
        for attack in simultaneous:
            end_tick = min(
                attack.nominal_end_tick,
                next_attack_by_pitch.get(attack.pitch, attack.nominal_end_tick),
                next_attack_by_string.get(attack.string_index, attack.nominal_end_tick),
            )
            if end_tick <= attack.performance_tick:
                raise RealizationError(
                    "retriggered guitar attacks cannot have zero duration"
                )
            bounded_attack = attack.model_copy(update={"nominal_end_tick": end_tick})
            if (
                bounded_simultaneous
                and bounded_simultaneous[-1].pitch == bounded_attack.pitch
            ):
                previous = bounded_simultaneous[-1]
                bounded_simultaneous[-1] = previous.model_copy(
                    update={
                        "nominal_end_tick": max(
                            previous.nominal_end_tick,
                            bounded_attack.nominal_end_tick,
                        ),
                        "velocity": max(previous.velocity, bounded_attack.velocity),
                    }
                )
            else:
                bounded_simultaneous.append(bounded_attack)

        bounded.extend(bounded_simultaneous)
        for attack in simultaneous:
            next_attack_by_pitch[attack.pitch] = attack.performance_tick
            next_attack_by_string[attack.string_index] = attack.performance_tick

    return tuple(
        sorted(
            bounded,
            key=lambda attack: (
                attack.performance_tick,
                attack.pitch,
                attack.canonical_tick,
                attack.source_id,
                attack.string_index,
            ),
        )
    )


def _realize_melodic(part: MelodicPart, recipe: _TrackRecipe) -> Track:
    notes = [
        _performance_note(phrase.start, note)
        for phrase in part.phrases
        for note in phrase.notes
    ]
    return Track(name=part.name, program=recipe.program, notes=notes)


def _realize_vocal(
    part: VocalPart,
    score: SemanticScore,
    lyric_chunks: Mapping[str, str],
    recipe: _TrackRecipe,
) -> Track:
    tokens = {token.id: token for token in score.lyric_tokens}
    notes: list[Note] = []
    for phrase in part.phrases:
        lyrics_by_index: dict[int, str] = {}
        for assignment in phrase.lyric_assignments:
            first_index = min(
                index
                for syllable in assignment.syllables
                for index in syllable.note_indexes
            )
            token = tokens[assignment.token_id]
            lyrics_by_index[first_index] = (
                lyric_chunks[token.id]
                if assignment.role == "primary"
                else token.display_text
            )
        notes.extend(
            _performance_note(phrase.start, note, lyric=lyrics_by_index.get(index))
            for index, note in enumerate(phrase.notes)
        )
    return Track(
        name=part.name,
        program=recipe.program,
        is_vocal=True,
        notes=notes,
    )


def _performance_note(
    phrase_start: Beat,
    note: SemanticNote,
    *,
    lyric: str | None = None,
) -> Note:
    start_tick = _beat_tick(phrase_start, "phrase start") + _beat_tick(
        note.onset, "note onset"
    )
    canonical_duration = _beat_tick(note.duration, "note duration")
    scaled_duration = canonical_duration * _ARTICULATION_DURATION[note.articulation]
    if scaled_duration.denominator != 1:
        raise RealizationError(
            f"{note.articulation} articulation duration does not align to the "
            f"{TICKS_PER_BEAT}-tick beat grid"
        )
    duration_tick = max(
        1,
        scaled_duration.numerator,
    )
    velocity = _clamp_velocity(
        _DYNAMIC_VELOCITY[note.dynamic] + _ARTICULATION_VELOCITY[note.articulation]
    )
    return Note(
        start=start_tick / TICKS_PER_BEAT,
        duration=duration_tick / TICKS_PER_BEAT,
        pitch=_pitch(note.pitch),
        velocity=velocity,
        lyric=lyric,
    )


def _pitch(pitch: SpelledPitch) -> int:
    semitone = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[pitch.step]
    midi_pitch = (pitch.octave + 1) * 12 + semitone + pitch.accidental
    if not 0 <= midi_pitch <= 127:
        raise RealizationError(
            f"spelled pitch is outside MIDI performance range: {pitch}"
        )
    return midi_pitch


def _primary_display_chunks(tokens: tuple[LyricToken, ...]) -> dict[str, str]:
    chunks = {token.id: token.display_text for token in tokens if token.is_singable}
    by_occurrence: dict[str, list[LyricToken]] = defaultdict(list)
    for token in tokens:
        by_occurrence[token.occurrence_id].append(token)
    for occurrence_tokens in by_occurrence.values():
        for index, token in enumerate(occurrence_tokens):
            if token.is_singable:
                continue
            previous = next(
                (
                    candidate
                    for candidate in reversed(occurrence_tokens[:index])
                    if candidate.is_singable
                ),
                None,
            )
            if previous is not None:
                chunks[previous.id] += token.display_text
                continue
            following = next(
                (
                    candidate
                    for candidate in occurrence_tokens[index + 1 :]
                    if candidate.is_singable
                ),
                None,
            )
            if following is None:
                raise RealizationError(
                    "a lyric occurrence cannot contain only non-singable tokens"
                )
            chunks[following.id] = token.display_text + chunks[following.id]
    return chunks


def _beat_tick(beat: Beat, label: str) -> int:
    return _tick(beat.value, label)


def _beat_float(beat: Beat, label: str) -> float:
    return _beat_tick(beat, label) / TICKS_PER_BEAT


def _tick(value: Fraction, label: str) -> int:
    scaled = value * TICKS_PER_BEAT
    if scaled.denominator != 1:
        raise RealizationError(
            f"{label} does not align to the {TICKS_PER_BEAT}-tick beat grid"
        )
    return scaled.numerator


def _clamp_velocity(velocity: int) -> int:
    return min(127, max(1, velocity))


def _recipe_hash(recipe: _Recipe) -> str:
    payload = {
        "version": recipe.version,
        "ticks_per_beat": TICKS_PER_BEAT,
        "string_offset_ticks": recipe.string_offset_ticks,
        "attack_velocities": recipe.attack_velocities,
        "instruments": {
            track.instrument: {
                "program": track.program,
                "is_vocal": track.is_vocal,
            }
            for track in recipe.instruments
        },
        "dynamic_velocity": _DYNAMIC_VELOCITY,
        "articulation_velocity": _ARTICULATION_VELOCITY,
        "articulation_duration": {
            key: str(value) for key, value in _ARTICULATION_DURATION.items()
        },
        "guitar_duration": _GUITAR_DURATION,
        "guitar_velocity": _GUITAR_VELOCITY,
        "guitar_direction_velocity": _GUITAR_DIRECTION_VELOCITY,
        "guitar_emphasis_velocity": _GUITAR_EMPHASIS_VELOCITY,
    }
    return _json_hash(payload)


def _json_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(encoded).hexdigest()
