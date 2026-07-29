"""Generation contracts: the request model and the SongGenerator seam.

``SongGenerator`` is the interface the AI-backed generator will implement;
the walking skeleton wires in a deterministic stub. Supplied meta values are
hard constraints on any implementation (non-negotiable #4).
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from melos.domain.models import KeyName, Song, TimeSignature


class GenerationRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    prompt: str = Field(min_length=1)
    tempo_bpm: float | None = Field(default=None, ge=20, le=400)
    key: KeyName | None = None
    time_signature: TimeSignature | None = None


class SongGenerator(Protocol):
    async def generate(self, request: GenerationRequest) -> Song: ...
