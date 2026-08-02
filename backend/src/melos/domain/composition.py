"""Framework-free inputs and port for one whole-song composition attempt."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from melos.domain.lyrics import SongSource
from melos.domain.music import KeyName
from melos.domain.semantic import Meter, SemanticScore


class CompositionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawUserContent(CompositionModel):
    """User-authored prompt and lyric markup, excluding request constraints."""

    prompt: str = Field(min_length=1, max_length=4_000)
    lyrics: str | None = Field(default=None, max_length=8_000)


class ResolvedCompositionConstraints(CompositionModel):
    """Machine-checkable constraints the current score can represent."""

    tempo_bpm: float = Field(ge=20, le=400)
    key: KeyName
    meter: Meter


class RequestedInstrumentConstraints(CompositionModel):
    """Exact requested lists, visible to the composer without GM enforcement."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


class InjectedInstruction(CompositionModel):
    """A versioned non-user prompt component supplied to the composer."""

    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=8_000)


class WholeSongCompositionInput(CompositionModel):
    """All and only the context for one complete semantic-score attempt."""

    raw_user_content: RawUserContent
    resolved_constraints: ResolvedCompositionConstraints
    requested_instruments: RequestedInstrumentConstraints
    source: SongSource
    injected_instructions: tuple[InjectedInstruction, ...] = ()

    def score_violations(self, score: SemanticScore) -> list[str]:
        """Return only contradictions checkable in the current score schema."""
        violations: list[str] = []
        constraints = self.resolved_constraints
        if score.tempo_bpm != constraints.tempo_bpm:
            violations.append(
                "tempo_bpm must exactly match the resolved constraint: "
                f"expected {constraints.tempo_bpm}, got {score.tempo_bpm}"
            )
        if score.key != constraints.key:
            violations.append(
                "key must exactly match the resolved constraint: "
                f"expected {constraints.key!r}, got {score.key!r}"
            )
        if score.meter != constraints.meter:
            expected_meter = (
                f"{constraints.meter.numerator}/{constraints.meter.denominator}"
            )
            actual_meter = f"{score.meter.numerator}/{score.meter.denominator}"
            violations.append(
                "meter must exactly match the resolved time signature: "
                f"expected {expected_meter}, got {actual_meter}"
            )

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

        if score.display_lyrics != self.source.sung_text:
            violations.append(
                "lyric_tokens must reconstruct the supplied lyrics exactly; "
                f"expected {self.source.sung_text!r}, got {score.display_lyrics!r}"
            )
        return violations


class SemanticScoreComposer(Protocol):
    """The internal port for one complete, validated song composition."""

    async def compose(
        self, composition: WholeSongCompositionInput
    ) -> SemanticScore: ...
