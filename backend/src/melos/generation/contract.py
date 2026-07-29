"""Compact JSON contract for the MIDI-generation LLM call.

This is the **public contract** the generation model emits (non-negotiable #1:
structured data only, never MIDI binary). Short keys keep token cost down;
every model forbids extra properties so strict json_schema enforcement works
across providers. Changes here are a STOP-and-flag item (AGENTS.md).

The LLM cannot self-authorize GM sound effects: ``allow_sound_effects`` is a
policy decision passed in by the caller (derived from the user's request), not
a field the model can emit.
"""

from pydantic import BaseModel, ConfigDict, Field

from melos.domain.models import KeyName, Note, Song, TimeSignature, Track

# Only SMF-valid denominators; a schema-enforcing provider can't emit "4/3".
_TIME_SIGNATURE_REGEX = r"^\d{1,2}/(1|2|4|8|16|32)$"


class CompactNote(BaseModel):
    """One note: s(tart beat), d(uration beats), p(itch), v(elocity), lyr(ic)."""

    model_config = ConfigDict(extra="forbid")

    s: float = Field(ge=0)
    d: float = Field(gt=0)
    p: int = Field(ge=0, le=127)
    v: int = Field(default=96, ge=1, le=127)
    lyr: str | None = None


class CompactTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    prog: int = Field(ge=0, le=127, description="General MIDI program, 0-indexed")
    perc: bool = False
    notes: list[CompactNote] = Field(min_length=1)


class CompactSong(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    bpm: float = Field(ge=20, le=400)
    key: KeyName
    ts: str = Field(pattern=_TIME_SIGNATURE_REGEX, description='e.g. "4/4"')
    tracks: list[CompactTrack] = Field(min_length=2)


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
