"""Song domain models — the single source of truth (Pydantic V2).

Times are in beats (quarter notes) from track start. Values mirror what a
Standard MIDI File can express, so a validated ``Song`` always exports cleanly.
"""

from itertools import pairwise
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from melos.domain.music import KeyName

# General MIDI, 0-indexed: programs 120-127 are sound effects (helicopter, ...).
SOUND_EFFECT_PROGRAMS = frozenset(range(120, 128))
PERCUSSION_CHANNEL = 9  # MIDI channel 10, 0-indexed, per GM convention
MAX_MELODIC_TRACKS = 15  # 16 MIDI channels minus the percussion channel

# Beat positions are floats, so equality needs slack. A 480-tick beat means one
# tick is ~0.002 beats; anything under that is below the exporter's resolution.
BEAT_EPSILON = 2e-3


class Note(BaseModel):
    """A single note; ``lyric`` is the syllable sung at this note, if any.

    Known limitation: two notes of the *same pitch* in the same track that
    genuinely overlap (not just touch) are ambiguous in Standard MIDI File
    output — note on/off is keyed only by (channel, pitch), so a synth may
    end the earlier note's sound early. Avoid overlapping same-pitch notes
    within a track if exact duration must be honored.
    """

    model_config = ConfigDict(validate_assignment=True)

    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(default=96, ge=1, le=127)
    lyric: str | None = None


class TimeSignature(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    numerator: int = Field(ge=1, le=32)
    denominator: Literal[1, 2, 4, 8, 16, 32]

    @property
    def beats_per_bar(self) -> float:
        """Bar length in quarter-note beats (6/8 is three beats, not six)."""
        return self.numerator * 4 / self.denominator


class Section(BaseModel):
    """A named span of the arrangement, exported as a MIDI marker.

    Only the start is stored — a section ends where the next one begins. Names
    are free text (``verse 1``, ``chorus``, ``drop``); no vocabulary is policed,
    and repeats are expected, so sections are a sequence and not a set.
    """

    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(min_length=1, max_length=80)
    start_beat: float = Field(ge=0)


class Track(BaseModel):
    """One instrument voice. ``program`` is a 0-indexed GM program number;
    for percussion tracks it selects the drum kit.

    ``is_vocal`` marks **a singable single-voice line** — words optional, but
    one note at a time, because that is what a voice can do. A polyphonic choir
    chord is an instrument track using a choir program, not a vocal track; each
    harmony part gets its own vocal track.

    Caveat: pydantic-core applies assignment before re-running ``model_validator``
    and does not roll back the field on failure, so a rejected mutation (e.g.
    setting ``is_vocal = True`` on a track with overlapping notes) leaves the
    instance holding the new, invalid value rather than the old one. Treat a
    ``Track`` as effectively immutable after construction; do not assign to its
    fields and rely on ``is_vocal`` still meaning "monophonic" if a prior
    assignment raised.
    """

    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(min_length=1)
    program: int = Field(ge=0, le=127)
    is_percussion: bool = False
    is_vocal: bool = False
    notes: list[Note] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_vocal(self) -> Self:
        if not self.is_vocal:
            return self
        if self.is_percussion:
            raise ValueError(f"track {self.name!r} cannot be both vocal and percussion")
        ordered = sorted(self.notes, key=lambda note: note.start)
        for previous, following in pairwise(ordered):
            if following.start < previous.start + previous.duration - BEAT_EPSILON:
                raise ValueError(
                    f"vocal track {self.name!r} is not monophonic: a note at beat"
                    f" {following.start} starts before the note at beat"
                    f" {previous.start} ends (a voice sings one note at a time;"
                    " put each harmony part on its own vocal track)"
                )
        return self


class Song(BaseModel):
    """A complete arrangement. Meta values are required — missing meta is
    resolved upstream, never defaulted here (non-negotiable #4)."""

    model_config = ConfigDict(validate_assignment=True)

    title: str = Field(min_length=1)
    tempo_bpm: float = Field(ge=20, le=400)
    key: KeyName
    time_signature: TimeSignature
    tracks: list[Track] = Field(min_length=2)
    # Optional: an arrangement may be unsectioned. When present, sections start
    # at the top of the song and land on bar lines (see _check_sections).
    sections: list[Section] = Field(default_factory=list)
    # GM sound-effect programs are excluded unless the prompt explicitly asks.
    allow_sound_effects: bool = False

    @property
    def end_beat(self) -> float:
        """Beat at which the last note of the arrangement finishes."""
        return max(note.start + note.duration for t in self.tracks for note in t.notes)

    @model_validator(mode="after")
    def _check_sections(self) -> Self:
        if not self.sections:
            return self
        starts = [section.start_beat for section in self.sections]
        if starts != sorted(starts):
            raise ValueError("sections must be ordered by start_beat")
        if starts[0] > BEAT_EPSILON:
            raise ValueError(
                f"the first section must start at beat 0, not {starts[0]}"
                " (use an intro section if the song opens instrumentally)"
            )
        end = self.end_beat
        if starts[-1] >= end:
            raise ValueError(
                f"section {self.sections[-1].name!r} starts at beat {starts[-1]},"
                f" at or past the end of the song ({end})"
            )
        bar = self.time_signature.beats_per_bar
        misaligned = [
            section.name
            for section in self.sections
            if abs(section.start_beat % bar) > BEAT_EPSILON
            and abs(section.start_beat % bar - bar) > BEAT_EPSILON
        ]
        if misaligned:
            raise ValueError(
                f"sections must start on a bar line ({bar} beats apart for"
                f" {self.time_signature.numerator}/{self.time_signature.denominator});"
                f" misaligned: {misaligned}"
            )
        return self

    @model_validator(mode="after")
    def _check_tracks(self) -> Self:
        melodic = [track for track in self.tracks if not track.is_percussion]
        percussion_count = len(self.tracks) - len(melodic)
        if percussion_count > 1:
            raise ValueError(
                "at most one percussion track is supported (shared MIDI channel 10)"
            )
        if len(melodic) > MAX_MELODIC_TRACKS:
            raise ValueError(
                f"at most {MAX_MELODIC_TRACKS} melodic tracks fit the MIDI channels"
            )
        if not self.allow_sound_effects:
            offenders = [t.name for t in melodic if t.program in SOUND_EFFECT_PROGRAMS]
            if offenders:
                raise ValueError(
                    f"sound-effect programs not allowed for tracks: {offenders}"
                )
        return self
