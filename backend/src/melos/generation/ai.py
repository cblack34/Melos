"""AI-backed SongGenerator: prompt -> compact JSON -> validated domain Song.

The agent emits only the compact contract (non-negotiable #1). Hard
constraints (resolved meta + instrument include/exclude) are enforced twice:
stated in the run message, then verified deterministically by an output
validator that sends precise violations back to the model as retries
(non-negotiable #4). Domain validation via ``to_song`` is the final gate.
"""

from typing import Self

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from melos.domain.generator import GenerationRequest
from melos.domain.gm import GM_PROGRAM_NAMES, is_percussion_name, program_for_name
from melos.domain.models import SOUND_EFFECT_PROGRAMS, Song
from melos.generation.contract import CompactSong, to_song
from melos.generation.meta import MetaResolver, ResolvedMeta

_INSTRUCTIONS = (
    "You are Melos, a music composer. Compose an original multi-track song and "
    "emit it only as data matching the schema. Note fields: s = start beat from "
    "track start, d = duration in beats, p = MIDI pitch 0-127, v = velocity, "
    "lyr = sung syllable. prog is a 0-indexed General MIDI program number; set "
    "perc=true on the single percussion track (its p values are GM percussion "
    "notes, e.g. 36 kick, 38 snare, 42 closed hat). "
    "The message lists hard constraints: repeat bpm, key, and ts EXACTLY as "
    "given; give every required instrument its own track with the exact program "
    "number stated; never use forbidden programs. "
    "Compose coherent music: melody plus supporting parts (bass, chords, drums "
    "where fitting), typically 32-128 beats. For sung prompts put lyr syllables "
    "on melody notes; instrumentals carry no lyr."
)


def _programs(names: list[str]) -> dict[int, str]:
    """GM program -> display name for the non-percussion names in the list."""
    programs: dict[int, str] = {}
    for name in names:
        if is_percussion_name(name):
            continue
        program = program_for_name(name)
        if program is not None:  # unknown names already rejected by the request
            programs[program] = GM_PROGRAM_NAMES[program]
    return programs


class Constraints(BaseModel):
    """Deterministically checkable constraints for one generation run."""

    meta: ResolvedMeta
    include_programs: dict[int, str]  # program -> display name
    exclude_programs: dict[int, str]
    require_percussion: bool
    forbid_percussion: bool
    allow_sound_effects: bool

    @classmethod
    def from_request(cls, request: GenerationRequest, meta: ResolvedMeta) -> Self:
        include_programs = _programs(request.include_instruments)
        return cls(
            meta=meta,
            include_programs=include_programs,
            exclude_programs=_programs(request.exclude_instruments),
            require_percussion=any(
                is_percussion_name(n) for n in request.include_instruments
            ),
            forbid_percussion=any(
                is_percussion_name(n) for n in request.exclude_instruments
            ),
            allow_sound_effects=any(
                program in SOUND_EFFECT_PROGRAMS for program in include_programs
            ),
        )

    @property
    def expected_ts(self) -> str:
        ts = self.meta.time_signature
        return f"{ts.numerator}/{ts.denominator}"

    def violations(self, compact: CompactSong) -> list[str]:
        problems: list[str] = []
        if compact.bpm != self.meta.tempo_bpm:
            problems.append(f"bpm must be exactly {self.meta.tempo_bpm}")
        if compact.key != self.meta.key:
            problems.append(f"key must be exactly {self.meta.key!r}")
        if compact.ts != self.expected_ts:
            problems.append(f"ts must be exactly {self.expected_ts!r}")

        melodic_programs = {t.prog for t in compact.tracks if not t.perc}
        has_percussion = any(t.perc for t in compact.tracks)
        for program, name in self.include_programs.items():
            if program not in melodic_programs:
                problems.append(f"missing required instrument: {name} (prog={program})")
        for program, name in self.exclude_programs.items():
            if program in melodic_programs:
                problems.append(f"forbidden instrument used: {name} (prog={program})")
        if self.require_percussion and not has_percussion:
            problems.append("a percussion track (perc=true) is required")
        if self.forbid_percussion and has_percussion:
            problems.append("percussion tracks are forbidden for this song")
        return problems


class PydanticAISongGenerator:
    def __init__(
        self,
        model: Model,
        meta_resolver: MetaResolver,
        *,
        use_native_output: bool,
        model_settings: ModelSettings | None = None,
    ) -> None:
        output_type = NativeOutput(CompactSong) if use_native_output else CompactSong
        self._agent: Agent[Constraints, CompactSong] = Agent(
            model,
            output_type=output_type,
            instructions=_INSTRUCTIONS,
            deps_type=Constraints,
            retries={"output": 3},
            model_settings=model_settings,
        )
        self._meta_resolver = meta_resolver

        @self._agent.output_validator
        async def _enforce(
            ctx: RunContext[Constraints], compact: CompactSong
        ) -> CompactSong:
            problems = ctx.deps.violations(compact)
            if problems:
                raise ModelRetry(
                    "Regenerate the complete song fixing these violations:\n- "
                    + "\n- ".join(problems)
                )
            try:
                to_song(compact, allow_sound_effects=ctx.deps.allow_sound_effects)
            except ValidationError as error:
                raise ModelRetry(
                    f"Regenerate the complete song; it failed validation:\n{error}"
                ) from error
            return compact

    async def generate(self, request: GenerationRequest) -> Song:
        meta = await self._meta_resolver.resolve(request)
        constraints = Constraints.from_request(request, meta)
        result = await self._agent.run(
            _user_message(request, constraints), deps=constraints
        )
        return to_song(
            result.output, allow_sound_effects=constraints.allow_sound_effects
        )


def _user_message(request: GenerationRequest, constraints: Constraints) -> str:
    lines = [
        f"bpm = {constraints.meta.tempo_bpm}",
        f"key = {constraints.meta.key}",
        f"ts = {constraints.expected_ts}",
    ]
    for program, name in constraints.include_programs.items():
        lines.append(f"required instrument track: {name} (prog={program})")
    for program, name in constraints.exclude_programs.items():
        lines.append(f"forbidden program: {program} ({name})")
    if constraints.require_percussion:
        lines.append("a percussion track (perc=true) is required")
    if constraints.forbid_percussion:
        lines.append("no percussion track allowed")
    constraint_block = "\n".join(f"- {line}" for line in lines)
    return f"Song prompt: {request.prompt}\n\nHard constraints:\n{constraint_block}"
