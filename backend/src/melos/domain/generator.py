"""Generation contracts: the request model and the SongGenerator seam.

``SongGenerator`` is the interface the AI-backed generator implements; a
deterministic stub exists for tests and LLM-free dev. Supplied meta values —
including instrument constraints — are hard constraints on any implementation
(non-negotiable #4).
"""

from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from melos.domain.gm import is_percussion_name, program_for_name
from melos.domain.lyrics import LyricsSpec, parse_lyrics, syllable_key
from melos.domain.models import KeyName, Song, TimeSignature
from melos.domain.progress import ProgressReporter

# Kept in sync by hand with generation/contract.py's _MAX_SECTIONS and
# CompactSection.n's max_length: domain must not import the generation layer
# (Clean Architecture — generation depends on domain, not the reverse), so
# the contract's ceilings are mirrored here rather than imported.
_MAX_LYRIC_SECTIONS = 64
_MAX_SECTION_NAME_LENGTH = 80


class GenerationRequest(BaseModel):
    # extra="forbid": an unsupported constraint must 422 loudly rather than be
    # silently dropped, per non-negotiable #4 ("meta values are hard constraints").
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4000)
    tempo_bpm: float | None = Field(default=None, ge=20, le=400)
    key: KeyName | None = None
    time_signature: TimeSignature | None = None
    # One free-text field: [section] tags, {directives}, and sung lines.
    # Blank means an instrumental (see domain/lyrics.py).
    lyrics: str | None = Field(default=None, max_length=8000)
    # General MIDI instrument names (see domain/gm.py), or "drums" for the
    # percussion track. Case-insensitive.
    include_instruments: list[str] = Field(default_factory=list, max_length=8)
    exclude_instruments: list[str] = Field(default_factory=list, max_length=16)
    # Per-request model override (e.g. a UI model picker). Plain ids here --
    # membership in the model catalog is an API-layer (generation/catalog.py)
    # concern, not a domain one; unset means "use the server's configured
    # default". None if catalog is empty. Blank strings coerce to None so
    # empty means unset consistently (validation uses is-not-None; resolution
    # uses truthiness — without coercion, "" would 422 as an unknown id).
    generation_model: str | None = Field(default=None, max_length=200)
    meta_model: str | None = Field(default=None, max_length=200)

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("generation_model", "meta_model", mode="before")
    @classmethod
    def _blank_model_override_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("include_instruments", "exclude_instruments")
    @classmethod
    def _known_instruments(cls, names: list[str]) -> list[str]:
        unknown = [
            name
            for name in names
            if program_for_name(name) is None and not is_percussion_name(name)
        ]
        if unknown:
            raise ValueError(
                f"unknown instrument name(s): {unknown}; use General MIDI"
                " instrument names or 'drums'"
            )
        return names

    @property
    def lyrics_spec(self) -> LyricsSpec:
        return parse_lyrics(self.lyrics)

    @model_validator(mode="after")
    def _include_exclude_disjoint(self) -> Self:
        # is_percussion_name() treats "drums"/"drum kit"/"percussion" as the
        # same pseudo-instrument (domain/gm.py); canonicalize on that key so
        # e.g. include=["Drums"], exclude=["percussion"] is caught as an
        # overlap rather than sailing through as two different raw strings.
        def _key(name: str) -> str:
            return "percussion" if is_percussion_name(name) else name.strip().lower()

        included = {_key(name): name for name in self.include_instruments}
        excluded = {_key(name): name for name in self.exclude_instruments}
        overlap = included.keys() & excluded.keys()
        if overlap:
            names = {included[key] for key in overlap}
            raise ValueError(f"instruments both included and excluded: {names}")
        return self

    @model_validator(mode="after")
    def _lyrics_are_satisfiable(self) -> Self:
        # Catch requests no generation attempt could ever satisfy, before any
        # LLM call: punctuation-only lyrics collapse to an empty comparison
        # key (any real sung output would then be flagged as wrong forever),
        # and a lyrics field asking for more/longer sections than the compact
        # contract allows can never be matched by any valid output. Both
        # would otherwise exhaust the 3 output retries and surface as a 502.
        spec = self.lyrics_spec
        if spec.has_lyrics and not syllable_key(spec.sung_text):
            raise ValueError("lyrics must contain sung words, not just punctuation")
        if len(spec.section_names) > _MAX_LYRIC_SECTIONS:
            raise ValueError(
                f"{len(spec.section_names)} sections requested; at most"
                f" {_MAX_LYRIC_SECTIONS} fit the generation contract"
            )
        too_long = [
            name for name in spec.section_names if len(name) > _MAX_SECTION_NAME_LENGTH
        ]
        if too_long:
            raise ValueError(f"section name(s) too long: {too_long}")
        return self


class SongGenerator(Protocol):
    async def generate(
        self,
        request: GenerationRequest,
        *,
        progress: ProgressReporter | None = None,
    ) -> Song: ...
