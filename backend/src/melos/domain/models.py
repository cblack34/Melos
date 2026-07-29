"""Song domain models — the single source of truth (Pydantic V2).

Times are in beats (quarter notes) from track start. Values mirror what a
Standard MIDI File can express, so a validated ``Song`` always exports cleanly.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The 30 key signatures a Standard MIDI File can carry (15 major + 15 minor).
KeyName = Literal[
    "Cb",
    "Gb",
    "Db",
    "Ab",
    "Eb",
    "Bb",
    "F",
    "C",
    "G",
    "D",
    "A",
    "E",
    "B",
    "F#",
    "C#",
    "Abm",
    "Ebm",
    "Bbm",
    "Fm",
    "Cm",
    "Gm",
    "Dm",
    "Am",
    "Em",
    "Bm",
    "F#m",
    "C#m",
    "G#m",
    "D#m",
    "A#m",
]

# General MIDI, 0-indexed: programs 120-127 are sound effects (helicopter, ...).
SOUND_EFFECT_PROGRAMS = frozenset(range(120, 128))
PERCUSSION_CHANNEL = 9  # MIDI channel 10, 0-indexed, per GM convention
MAX_MELODIC_TRACKS = 15  # 16 MIDI channels minus the percussion channel


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


class Track(BaseModel):
    """One instrument voice. ``program`` is a 0-indexed GM program number;
    for percussion tracks it selects the drum kit."""

    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(min_length=1)
    program: int = Field(ge=0, le=127)
    is_percussion: bool = False
    notes: list[Note] = Field(min_length=1)


class Song(BaseModel):
    """A complete arrangement. Meta values are required — missing meta is
    resolved upstream, never defaulted here (non-negotiable #4)."""

    model_config = ConfigDict(validate_assignment=True)

    title: str = Field(min_length=1)
    tempo_bpm: float = Field(ge=20, le=400)
    key: KeyName
    time_signature: TimeSignature
    tracks: list[Track] = Field(min_length=2)
    # GM sound-effect programs are excluded unless the prompt explicitly asks.
    allow_sound_effects: bool = False

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
