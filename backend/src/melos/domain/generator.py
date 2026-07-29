"""Generation contracts: the request model and the SongGenerator seam.

``SongGenerator`` is the interface the AI-backed generator implements; a
deterministic stub exists for tests and LLM-free dev. Supplied meta values —
including instrument constraints — are hard constraints on any implementation
(non-negotiable #4).
"""

from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from melos.domain.gm import is_percussion_name, program_for_name
from melos.domain.models import KeyName, Song, TimeSignature


class GenerationRequest(BaseModel):
    # extra="forbid": an unsupported constraint must 422 loudly rather than be
    # silently dropped, per non-negotiable #4 ("meta values are hard constraints").
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    tempo_bpm: float | None = Field(default=None, ge=20, le=400)
    key: KeyName | None = None
    time_signature: TimeSignature | None = None
    # General MIDI instrument names (see domain/gm.py), or "drums" for the
    # percussion track. Case-insensitive.
    include_instruments: list[str] = Field(default_factory=list, max_length=8)
    exclude_instruments: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
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

    @model_validator(mode="after")
    def _include_exclude_disjoint(self) -> Self:
        included = {name.strip().lower() for name in self.include_instruments}
        excluded = {name.strip().lower() for name in self.exclude_instruments}
        overlap = included & excluded
        if overlap:
            raise ValueError(f"instruments both included and excluded: {overlap}")
        return self


class SongGenerator(Protocol):
    async def generate(self, request: GenerationRequest) -> Song: ...
