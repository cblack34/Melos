"""AI-backed SongGenerator: prompt -> compact JSON -> validated domain Song.

The agent emits only the compact contract (non-negotiable #1). Hard
constraints (resolved meta + instrument include/exclude) are enforced twice:
stated in the run message, then verified deterministically by an output
validator that sends precise violations back to the model as retries
(non-negotiable #4). Domain validation via ``to_song`` is the final gate.
"""

from typing import Self

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from melos.domain.generator import GenerationRequest
from melos.domain.gm import GM_PROGRAM_NAMES, is_percussion_name, program_for_name
from melos.domain.lyrics import LyricsSpec, closest_by_syllables, syllable_key
from melos.domain.models import SOUND_EFFECT_PROGRAMS, Song
from melos.domain.progress import (
    ProgressEvent,
    ProgressReporter,
    bind_progress,
    report_progress,
    reset_progress,
)
from melos.generation.contract import CompactSong, CompactTrack, to_song
from melos.generation.meta import MetaResolver, ResolvedMeta

# Shared with progress events (attempt / max_attempts on validation_retry).
_OUTPUT_RETRIES = 3

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
    "where fitting), typically 32-128 beats. "
    "Vocals: set voc=true on a sung line and put one lyr syllable per note. A "
    "vocal track is ONE voice, so its notes must never overlap; put each harmony "
    "part on its own voc track. Prefix the first syllable of each new word with "
    "a space; a syllable held across several notes carries lyr on the first only. "
    "Keep sung pitches in a singable range (MIDI 48-81) and inside about two "
    "octaves. Never put lyr on a non-vocal track, and never sing section names. "
    "When lyrics are supplied: concatenating every lyr on the vocal track in "
    "note order must reproduce the supplied text EXACTLY ONCE. Never repeat a "
    "word or fragment — a word spread over notes gets consecutive pieces "
    "('Mor' then 'ning'), never the whole word followed by part of it again. "
    "Reproduce the characters as written: never transliterate, romanize, "
    "translate, or respell (keep Japanese kanji as kanji, not kana). "
    "Sections: when the message lists them, emit one entry per section in the "
    "same order, each starting on a bar line, the first at beat 0."
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


# A sung line should sit where a human voice lives. Generous on purpose: wide
# enough for any real lead vocal, tight enough to catch a "melody" written for
# a synth and then labelled as singing.
_MIN_SUNG_PITCH, _MAX_SUNG_PITCH = 48, 81  # C3-A5
_MAX_SUNG_SPAN = 24  # two octaves

# DEFERRED TO PER-SECTION GENERATION — see issue #39. Flip back to True there.
#
# "One vocal track sings the supplied lyrics complete and in order" cannot be
# met one-shot for a real song: measured on a 404-word request, the model
# emitted 10/10 correct sections but sang only 72% of the words (it thins
# repeated choruses rather than truncating), burning 61k output tokens. The
# check then rejected it three times and the user got a 502 costing ~$2.70.
#
# The fix is generating one section per call, where each check covers ~40 words
# and is reliable. Until then the completeness comparison is skipped, which is
# a real loss: supplied lyrics come back *incomplete and unflagged*, at odds
# with non-negotiable #4. Everything else about lyrics stays enforced — they
# may only appear on vocal tracks, a vocal track is still required when lyrics
# are supplied, sung range is still checked, and requested sections must still
# match. `scripts/quality_run.py` also still verifies completeness end to end,
# so it stays the canary for when this can be turned back on.
ENFORCE_LYRIC_COMPLETENESS = False


class Constraints(BaseModel):
    """Deterministically checkable constraints for one generation run."""

    meta: ResolvedMeta
    include_programs: dict[int, str]  # program -> display name
    exclude_programs: dict[int, str]
    require_percussion: bool
    forbid_percussion: bool
    allow_sound_effects: bool
    lyrics: LyricsSpec
    # Why the last attempt *we saw* was rejected. A Constraints is built per
    # request, so this is per-run scratch space, and it is the only record of
    # *which* constraint the model kept missing once retries run out —
    # pydantic-ai's UnexpectedModelBehavior says only "exceeded maximum output
    # retries". last_rejection_attempt records which retry this came from,
    # because pydantic-ai's output-retry budget is shared with retry paths
    # (malformed tool args, etc.) that never reach `_enforce` — so the attempt
    # that exhausts the budget is not necessarily the one that set
    # last_rejection, and the message must not imply otherwise.
    last_rejection: list[str] = Field(default_factory=list)
    last_rejection_attempt: int = -1

    @classmethod
    def from_request(cls, request: GenerationRequest, meta: ResolvedMeta) -> Self:
        include_programs = _programs(request.include_instruments)
        return cls(
            meta=meta,
            lyrics=request.lyrics_spec,
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
        problems.extend(self._lyric_problems(compact))
        problems.extend(self._section_problems(compact))
        return problems

    def _lyric_problems(self, compact: CompactSong) -> list[str]:
        """Lyrics live on vocal tracks, and the lead sings what the user wrote."""
        problems: list[str] = []
        stray = [t.name for t in compact.tracks if not t.voc and _has_lyrics(t)]
        if stray:
            problems.append(
                f"only vocal tracks (voc=true) may carry lyr; remove it from: {stray}"
            )
        for track in (t for t in compact.tracks if t.voc):
            problems.extend(_range_problems(track))

        if not self.lyrics.has_lyrics:
            return problems

        singers = [t for t in compact.tracks if t.voc and _has_lyrics(t)]
        if not singers:
            problems.append(
                "the request supplies lyrics, so one vocal track (voc=true) must"
                " sing them as lyr syllables"
            )
            return problems
        if not ENFORCE_LYRIC_COMPLETENESS:
            return problems
        wanted = syllable_key(self.lyrics.sung_text)
        if not any(syllable_key(_performed_text(track)) == wanted for track in singers):
            closest = closest_by_syllables(
                singers, self.lyrics.sung_text, text=_performed_text
            )
            problems.append(
                "one vocal track must sing the supplied lyrics complete and in"
                f" order; track {closest.name!r} sang"
                f" {_performed_text(closest)[:120]!r} but the lyrics are"
                f" {self.lyrics.sung_text[:200]!r}"
            )
        return problems

    def _section_problems(self, compact: CompactSong) -> list[str]:
        wanted = self.lyrics.section_names
        if not wanted:
            return []
        got = [section.n for section in compact.sections]
        if [name.casefold() for name in got] != [name.casefold() for name in wanted]:
            return [
                f"sections must match the [tags] in the lyrics exactly: expected"
                f" {wanted}, got {got}"
            ]
        return []


def _has_lyrics(track: CompactTrack) -> bool:
    return any(note.lyr for note in track.notes)


def _performed_text(track: CompactTrack) -> str:
    """Syllables in performance order — melisma notes carry no lyr and are skipped.

    Named distinctly from ``LyricsSpec.sung_text`` (domain/lyrics.py): that one
    joins raw request lines with spaces, this one concatenates note-level
    syllables relying on the model's leading-space word-boundary convention.
    The two are only safe to compare after both pass through ``syllable_key``.
    """
    ordered = sorted(track.notes, key=lambda note: note.s)
    return "".join(note.lyr for note in ordered if note.lyr)


def _range_problems(track: CompactTrack) -> list[str]:
    pitches = [note.p for note in track.notes]
    low, high = min(pitches), max(pitches)
    problems: list[str] = []
    if low < _MIN_SUNG_PITCH or high > _MAX_SUNG_PITCH:
        problems.append(
            f"sung track {track.name!r} spans MIDI {low}-{high}; keep sung pitches"
            f" within {_MIN_SUNG_PITCH}-{_MAX_SUNG_PITCH} so a voice can reach them"
        )
    if high - low > _MAX_SUNG_SPAN:
        problems.append(
            f"sung track {track.name!r} covers {high - low} semitones; keep a vocal"
            f" line within {_MAX_SUNG_SPAN}"
        )
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
            retries={"output": _OUTPUT_RETRIES},
            model_settings=model_settings,
        )
        self._meta_resolver = meta_resolver

        @self._agent.output_validator
        async def _enforce(
            ctx: RunContext[Constraints], compact: CompactSong
        ) -> CompactSong:
            problems = ctx.deps.violations(compact)
            if problems:
                ctx.deps.last_rejection = problems
                ctx.deps.last_rejection_attempt = ctx.retry
                await report_progress(
                    ProgressEvent(
                        phase="validation_retry",
                        message="Constraint check failed; regenerating",
                        attempt=ctx.retry + 1,
                        max_attempts=_OUTPUT_RETRIES,
                        reasons=list(problems),
                    )
                )
                raise ModelRetry(
                    "Regenerate the complete song fixing these violations:\n- "
                    + "\n- ".join(problems)
                )
            try:
                to_song(compact, allow_sound_effects=ctx.deps.allow_sound_effects)
            except ValidationError as error:
                reasons = [
                    f"{'.'.join(str(p) for p in err['loc']) or 'song'}: {err['msg']}"
                    for err in error.errors()
                ]
                ctx.deps.last_rejection = reasons
                ctx.deps.last_rejection_attempt = ctx.retry
                await report_progress(
                    ProgressEvent(
                        phase="validation_retry",
                        message="Domain validation failed; regenerating",
                        attempt=ctx.retry + 1,
                        max_attempts=_OUTPUT_RETRIES,
                        reasons=reasons,
                    )
                )
                raise ModelRetry(
                    f"Regenerate the complete song; it failed validation:\n{error}"
                ) from error
            ctx.deps.last_rejection = []
            return compact

    async def generate(
        self,
        request: GenerationRequest,
        *,
        progress: ProgressReporter | None = None,
    ) -> Song:
        token = bind_progress(progress)
        try:
            return await self._generate(request)
        finally:
            reset_progress(token)

    async def _generate(self, request: GenerationRequest) -> Song:
        await report_progress(
            ProgressEvent(
                phase="request_received",
                message="Generation request accepted",
            )
        )
        try:
            meta = await self._resolve_meta(request)
            constraints = Constraints.from_request(request, meta)
            await report_progress(
                ProgressEvent(
                    phase="generation_started",
                    message="Composing multi-track arrangement",
                )
            )
            try:
                result = await self._agent.run(
                    _user_message(request, constraints), deps=constraints
                )
            except UnexpectedModelBehavior as error:
                # Say what the model kept getting wrong. Without this the user sees
                # only "exceeded maximum output retries", which is unactionable —
                # for them and for anyone debugging a report of it. The attempt
                # number is included because the retry budget is shared with
                # non-validator retry paths, so this rejection is not guaranteed
                # to be from the attempt that actually exhausted the budget.
                if constraints.last_rejection:
                    attempt = constraints.last_rejection_attempt + 1
                    note = f"Last rejection (attempt {attempt}): " + "; ".join(
                        constraints.last_rejection
                    )
                    raise UnexpectedModelBehavior(f"{error} {note}") from error
                raise
            song = to_song(
                result.output, allow_sound_effects=constraints.allow_sound_effects
            )
            await report_progress(
                ProgressEvent(
                    phase="generation_completed",
                    message="Arrangement validated",
                )
            )
            return song
        except Exception as error:
            await report_progress(ProgressEvent(phase="failed", message=str(error)))
            raise

    async def _resolve_meta(self, request: GenerationRequest) -> ResolvedMeta:
        user_complete = (
            request.tempo_bpm is not None
            and request.key is not None
            and request.time_signature is not None
        )
        if user_complete:
            await report_progress(
                ProgressEvent(
                    phase="meta_skipped",
                    message="Using supplied tempo, key, and time signature",
                )
            )
            return await self._meta_resolver.resolve(request)

        await report_progress(
            ProgressEvent(
                phase="meta_started",
                message="Resolving tempo, key, and time signature",
            )
        )
        meta = await self._meta_resolver.resolve(request)
        ts = meta.time_signature
        sig = f"{ts.numerator}/{ts.denominator}"
        await report_progress(
            ProgressEvent(
                phase="meta_completed",
                message=f"{meta.tempo_bpm:g} BPM, {meta.key}, {sig}",
            )
        )
        return meta


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
    spec = constraints.lyrics
    if spec.section_names:
        lines.append(f"sections, in this exact order: {spec.section_names}")
    if spec.has_lyrics:
        lines.append(
            "one voc=true track sings the lyrics below complete and in order,"
            " one lyr syllable per note"
        )
    constraint_block = "\n".join(f"- {line}" for line in lines)
    message = f"Song prompt: {request.prompt}\n\nHard constraints:\n{constraint_block}"
    if spec.directives:
        # Guidance, not verified: mapping prose onto programs and silent spans
        # needs its own AI call (roadmap).
        directives = "\n".join(f"- {directive}" for directive in spec.directives)
        message += f"\n\nArrangement notes (follow where musical):\n{directives}"
    if request.lyrics and request.lyrics.strip():
        # The full field, tags included, so the model can place words in sections.
        message += f"\n\nLyrics:\n{request.lyrics.strip()}"
    return message
