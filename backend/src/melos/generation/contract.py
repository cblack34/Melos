"""Compact JSON contract for the MIDI-generation LLM call.

This is the **public contract** the generation model emits (non-negotiable #1:
structured data only, never MIDI binary). Short keys keep token cost down;
every model forbids extra properties so strict json_schema enforcement works
across providers. Changes here are a STOP-and-flag item (AGENTS.md).

The LLM cannot self-authorize GM sound effects: ``allow_sound_effects`` is a
policy decision passed in by the caller (derived from the user's request), not
a field the model can emit.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from melos.domain.models import KeyName, Note, Song, TimeSignature, Track

# Only SMF-valid denominators; a schema-enforcing provider can't emit "4/3".
# ASCII digits only ([0-9], not \d) so a fullwidth Unicode digit can't sneak
# through the pattern. Denominators must match TimeSignature.denominator in
# domain/models.py; keep the two lists in sync by hand.
_TIME_SIGNATURE_REGEX = r"^[0-9]{1,2}/(?:1|2|4|8|16|32)$"

# Upper bounds are trust-boundary limits on LLM output, not musical judgments:
# they keep a hallucinating model from emitting unbounded payloads or beat
# positions that overflow MIDI's variable-length delta encoding.
_MAX_BEAT = 10_000.0  # ~83 min (1.4 h) at 120 BPM; far beyond any real song
_MAX_NOTES_PER_TRACK = 5_000
_MAX_TRACKS = 16  # MIDI channel count; domain rules tighten this further


class CompactNote(BaseModel):
    """One note: s(tart beat), d(uration beats), p(itch), v(elocity), lyr(ic)."""

    model_config = ConfigDict(extra="forbid")

    s: float = Field(ge=0, le=_MAX_BEAT)
    d: float = Field(gt=0, le=_MAX_BEAT)
    p: int = Field(ge=0, le=127)
    v: int = Field(default=96, ge=1, le=127)
    lyr: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _check_end_within_bound(self) -> Self:
        end = self.s + self.d
        if end > _MAX_BEAT:
            raise ValueError(f"note end (s+d={end}) exceeds {_MAX_BEAT}")
        return self


class CompactTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    prog: int = Field(ge=0, le=127, description="General MIDI program, 0-indexed")
    perc: bool = False
    notes: list[CompactNote] = Field(min_length=1, max_length=_MAX_NOTES_PER_TRACK)


class CompactSong(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    bpm: float = Field(ge=20, le=400)
    key: KeyName
    ts: str = Field(pattern=_TIME_SIGNATURE_REGEX, description='e.g. "4/4"')
    tracks: list[CompactTrack] = Field(min_length=2, max_length=_MAX_TRACKS)


def to_song(compact: CompactSong, *, allow_sound_effects: bool = False) -> Song:
    """Map the compact contract onto the domain model (the validation gate).

    Raises pydantic.ValidationError when the compact data violates domain
    rules (invalid time signature, sound effects without permission, ...).
    """
    numerator, _, denominator = compact.ts.partition(
        "/"
    )  # form guaranteed by ts pattern
    return Song(
        title=compact.title,
        tempo_bpm=compact.bpm,
        key=compact.key,
        time_signature=TimeSignature.model_validate(
            {"numerator": int(numerator), "denominator": int(denominator)}
        ),
        allow_sound_effects=allow_sound_effects,
        tracks=[
            Track(
                name=track.name,
                program=track.prog,
                is_percussion=track.perc,
                notes=[
                    Note(
                        start=note.s,
                        duration=note.d,
                        pitch=note.p,
                        velocity=note.v,
                        lyric=note.lyr,
                    )
                    for note in track.notes
                ],
            )
            for track in compact.tracks
        ],
    )
