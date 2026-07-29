"""Generation contracts: the request model and the SongGenerator seam.

``SongGenerator`` is the interface the AI-backed generator will implement;
the walking skeleton wires in a deterministic stub. Supplied meta values are
hard constraints on any implementation (non-negotiable #4).
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from melos.domain.models import KeyName, Song, TimeSignature


class GenerationRequest(BaseModel):
    # extra="forbid": an unsupported constraint (e.g. an instrument
    # include/exclude filter — deliberately deferred to the LLM-generator
    # milestone, see issue #3) must 422 loudly rather than being silently
    # dropped, per non-negotiable #4 ("meta values are hard constraints").
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    tempo_bpm: float | None = Field(default=None, ge=20, le=400)
    key: KeyName | None = None
    time_signature: TimeSignature | None = None

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class SongGenerator(Protocol):
    async def generate(self, request: GenerationRequest) -> Song: ...
