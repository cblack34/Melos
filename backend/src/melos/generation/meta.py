"""Meta resolution: fill missing tempo/key/time-signature before generation.

Non-negotiable #4: user-supplied values are hard constraints and pass through
untouched; only the gaps are resolved (by a small LLM call). The generation
call downstream always receives a complete package. If nothing is missing, no
LLM call happens at all.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from melos.domain.generator import GenerationRequest
from melos.domain.models import KeyName, TimeSignature

_INSTRUCTIONS = (
    "You pick musical metadata for a song that will be generated from a user "
    "prompt. Choose a tempo (BPM), key, and time signature that fit the "
    "prompt's genre and mood. Some values may already be fixed by the user; "
    "they are stated in the message. Choose the remaining values to be "
    "musically coherent with the fixed ones."
)


class ResolvedMeta(BaseModel):
    """The complete meta package the generation call requires."""

    model_config = ConfigDict(extra="forbid")

    tempo_bpm: float = Field(ge=20, le=400)
    key: KeyName
    time_signature: TimeSignature


class MetaResolver:
    def __init__(
        self,
        model: Model,
        *,
        use_native_output: bool,
        model_settings: ModelSettings | None = None,
    ) -> None:
        # Ollama (local) enforces json_schema natively; ToolOutput is the
        # portable default elsewhere (see docs/tech-stack.md).
        output_type = NativeOutput(ResolvedMeta) if use_native_output else ResolvedMeta
        self._agent = Agent(
            model,
            output_type=output_type,
            instructions=_INSTRUCTIONS,
            retries={"output": 2},
            model_settings=model_settings,
        )

    async def resolve(self, request: GenerationRequest) -> ResolvedMeta:
        """Resolve the complete meta package.

        Raises whatever the underlying pydantic-ai ``Agent.run`` call raises,
        e.g. ``UnexpectedModelBehavior`` once output-validation retries are
        exhausted, or ``ModelHTTPError``/``ModelAPIError`` on transport failure.
        """
        supplied = self._supplied(request)
        if supplied is not None:
            return supplied
        result = await self._agent.run(self._prompt(request))
        return self._overlay(request, result.output)

    @staticmethod
    def _supplied(request: GenerationRequest) -> ResolvedMeta | None:
        """The complete package, if the user supplied everything."""
        if (
            request.tempo_bpm is not None
            and request.key is not None
            and request.time_signature is not None
        ):
            return ResolvedMeta(
                tempo_bpm=request.tempo_bpm,
                key=request.key,
                time_signature=request.time_signature,
            )
        return None

    @staticmethod
    def _prompt(request: GenerationRequest) -> str:
        signature = request.time_signature
        fixed = [
            f"{name} = {value}"
            for name, value in (
                ("tempo_bpm", request.tempo_bpm),
                ("key", request.key),
                (
                    "time_signature",
                    signature and f"{signature.numerator}/{signature.denominator}",
                ),
            )
            if value is not None
        ]
        fixed_lines = (
            "Fixed by the user (repeat these values exactly):\n" + "\n".join(fixed)
            if fixed
            else "No values are fixed; choose all of them."
        )
        return f"Song prompt: {request.prompt}\n\n{fixed_lines}"

    @staticmethod
    def _overlay(request: GenerationRequest, resolved: ResolvedMeta) -> ResolvedMeta:
        """User values always win, whatever the model answered."""
        return ResolvedMeta(
            tempo_bpm=request.tempo_bpm
            if request.tempo_bpm is not None
            else resolved.tempo_bpm,
            key=request.key if request.key is not None else resolved.key,
            time_signature=request.time_signature
            if request.time_signature is not None
            else resolved.time_signature,
        )
