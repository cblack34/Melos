"""Framework-free inputs and port for one whole-song composition attempt."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from melos.domain.lyrics import SongSource
from melos.domain.music import KeyName
from melos.domain.semantic import Meter, SemanticScore


class CompositionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawUserContent(CompositionModel):
    """Untouched user-authored fields, apart from all derived data."""

    prompt: str = Field(min_length=1, max_length=4_000)
    lyrics: str | None = Field(default=None, max_length=8_000)


class ResolvedCompositionConstraints(CompositionModel):
    """Machine-checkable constraints the current score can represent."""

    tempo_bpm: float = Field(ge=20, le=400)
    key: KeyName
    meter: Meter


class InjectedInstruction(CompositionModel):
    """A versioned non-user prompt component supplied to the composer."""

    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=8_000)


class WholeSongCompositionInput(CompositionModel):
    """All and only the context for one complete semantic-score attempt."""

    raw_user_content: RawUserContent
    resolved_constraints: ResolvedCompositionConstraints
    source: SongSource
    injected_instructions: tuple[InjectedInstruction, ...] = ()

    def score_violations(self, score: SemanticScore) -> list[str]:
        """Return only contradictions checkable in the current score schema."""
        violations: list[str] = []
        constraints = self.resolved_constraints
        if score.tempo_bpm != constraints.tempo_bpm:
            violations.append(f"tempo_bpm must be exactly {constraints.tempo_bpm}")
        if score.key != constraints.key:
            violations.append(f"key must be exactly {constraints.key!r}")
        if score.meter != constraints.meter:
            violations.append("meter must exactly match the resolved time signature")

        requested_sections = [item.name.casefold() for item in self.source.sections]
        if requested_sections:
            actual_sections = [occurrence.label.casefold() for occurrence in score.form]
            if actual_sections != requested_sections:
                violations.append(
                    "form occurrences must match the requested section tags in order: "
                    f"expected {requested_sections}, got {actual_sections}"
                )

        requested_directives = sorted(item.text for item in self.source.directives)
        actual_directives = sorted(item.text for item in score.user_directives)
        if actual_directives != requested_directives:
            violations.append(
                "user_directives must preserve exactly the supplied directive text; "
                f"expected {requested_directives}, got {actual_directives}"
            )
        return violations


class SemanticScoreComposer(Protocol):
    """The internal port for one complete, validated song composition."""

    async def compose(
        self, composition: WholeSongCompositionInput
    ) -> SemanticScore: ...
