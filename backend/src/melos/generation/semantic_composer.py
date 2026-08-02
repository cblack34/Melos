"""Pydantic-AI adapter for one complete semantic-score composition attempt."""

from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from melos.domain.composition import (
    InjectedInstruction,
    RawUserContent,
    RequestedInstrumentConstraints,
    ResolvedCompositionConstraints,
    WholeSongCompositionInput,
)
from melos.domain.generator import GenerationRequest
from melos.domain.lyrics import parse_song_source
from melos.domain.semantic import Meter, SemanticScore
from melos.generation.meta import ResolvedMeta
from melos.generation.observability import progress_hooks

_OUTPUT_RETRIES = 3
_INSTRUCTION_ID = "whole-song-semantic-composer"
_INSTRUCTION_VERSION = "1"
_AGENT_INSTRUCTIONS = (
    "Follow the versioned injected instructions in the whole-song composition "
    "input and return one valid SemanticScore."
)
_INJECTED_INSTRUCTIONS = (
    "Compose exactly one complete whole-song SemanticScore. The user content, "
    "resolved constraints, and ordered source markup are supplied as structured "
    "data. Preserve every supplied directive as user_directives; only put new "
    "compatible ideas in composer_enhancements. Never compose individual sections "
    "or emit MIDI-shaped note-event JSON."
)


def composition_input_from(
    request: GenerationRequest, meta: ResolvedMeta
) -> WholeSongCompositionInput:
    """Normalize existing request/meta seams without changing their contracts."""
    return WholeSongCompositionInput(
        raw_user_content=RawUserContent(prompt=request.prompt, lyrics=request.lyrics),
        resolved_constraints=ResolvedCompositionConstraints(
            tempo_bpm=meta.tempo_bpm,
            key=meta.key,
            meter=Meter(
                numerator=meta.time_signature.numerator,
                denominator=meta.time_signature.denominator,
            ),
        ),
        requested_instruments=RequestedInstrumentConstraints(
            include=tuple(request.include_instruments),
            exclude=tuple(request.exclude_instruments),
        ),
        source=parse_song_source(request.lyrics),
        injected_instructions=(
            InjectedInstruction(
                id=_INSTRUCTION_ID,
                version=_INSTRUCTION_VERSION,
                text=_INJECTED_INSTRUCTIONS,
            ),
        ),
    )


class PydanticAISemanticScoreComposer:
    """An isolated adapter; production routing remains on the legacy generator."""

    def __init__(
        self,
        model: Model,
        *,
        use_native_output: bool,
        model_settings: ModelSettings | None = None,
    ) -> None:
        output_type = (
            NativeOutput(SemanticScore) if use_native_output else SemanticScore
        )
        self._agent: Agent[WholeSongCompositionInput, SemanticScore] = Agent(
            model,
            output_type=output_type,
            instructions=_AGENT_INSTRUCTIONS,
            deps_type=WholeSongCompositionInput,
            retries={"output": _OUTPUT_RETRIES},
            model_settings=model_settings,
            capabilities=[progress_hooks()],
        )

        @self._agent.output_validator
        def _enforce(
            ctx: RunContext[WholeSongCompositionInput], score: SemanticScore
        ) -> SemanticScore:
            if violations := ctx.deps.score_violations(score):
                raise ModelRetry(
                    "Regenerate the complete SemanticScore without contradicting "
                    "the whole-song context:\n- " + "\n- ".join(violations)
                )
            return score

    async def compose(self, composition: WholeSongCompositionInput) -> SemanticScore:
        """Run one whole-song operation; output retries retain the conversation."""
        result = await self._agent.run(
            _composition_message(composition), deps=composition
        )
        return result.output


def _composition_message(composition: WholeSongCompositionInput) -> str:
    """Keep the complete input in one stable, inspectable user message."""
    return "Whole-song composition input (JSON):\n" + composition.model_dump_json(
        by_alias=True
    )
