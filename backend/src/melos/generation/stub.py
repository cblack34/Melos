"""Deterministic stand-in for the AI generator (tests and LLM-free dev).

Returns a canned arrangement; request constraints (tempo, key, time signature,
instrument include/exclude) are honored deterministically so the
hard-constraint plumbing stays real even without an LLM.

Lyrics are honored on a best-effort basis, not verified: the melody track
becomes ``is_vocal`` and sings ``request.lyrics``' words in order (one word
per note, extending the canned 8-note figure to fit), and one ``Section`` per
``[tag]`` is emitted, bar-aligned. Unlike the real generator's output
validator (``generation/ai.py``), none of this is checked against the
constraints it's built from — it exists so a developer using
``MELOS_GENERATION_BACKEND=stub`` to work on the lyrics UI sees their input
reflected in the download rather than silently ignored, not to exercise the
lyrics contract itself.
"""

import math

from melos.domain.generator import GenerationRequest
from melos.domain.gm import GM_PROGRAM_NAMES, is_percussion_name, program_for_name
from melos.domain.lyrics import LyricsSpec
from melos.domain.models import (
    SOUND_EFFECT_PROGRAMS,
    Note,
    Section,
    Song,
    TimeSignature,
    Track,
)

_LYRIC_SYLLABLES = ["Me", "los", "sings", "a", "lit", "tle", "song", "now"]
_MELODY_PITCHES = [60, 62, 64, 65, 67, 65, 64, 60]  # C major run
_BASS_PITCHES = [36, 43, 41, 36]  # C G F C
_KICK, _SNARE = 36, 38  # GM percussion
_DEFAULT_MELODY_PROGRAM = 73  # flute
_DEFAULT_BASS_PROGRAM = 33  # fingered electric bass


class StubSongGenerator:
    async def generate(self, request: GenerationRequest) -> Song:
        excluded = {
            program_for_name(name)
            for name in request.exclude_instruments
            if not is_percussion_name(name)
        }
        drums_excluded = any(
            is_percussion_name(name) for name in request.exclude_instruments
        )

        spec = request.lyrics_spec
        time_signature = request.time_signature or TimeSignature(
            numerator=4, denominator=4
        )

        tracks: list[Track] = []
        melody_program = _first_allowed(_DEFAULT_MELODY_PROGRAM, excluded)
        tracks.append(_melody(melody_program, spec, time_signature.beats_per_bar))
        bass_program = _first_allowed(
            _DEFAULT_BASS_PROGRAM, excluded | {melody_program}
        )
        tracks.append(_riff("Bass", bass_program))
        if not drums_excluded:
            tracks.append(_drums())

        # Every must-include instrument gets its own, correctly named track
        # (non-negotiable #4) — even if its program collides with a default
        # melody/bass program, in which case the existing track is renamed
        # rather than skipped.
        for name in request.include_instruments:
            if is_percussion_name(name):
                if drums_excluded:
                    continue  # disjointness is enforced by request validation
                if not any(track.is_percussion for track in tracks):
                    tracks.append(_drums())
                continue
            program = program_for_name(name)
            if program is None:
                continue
            existing = next(
                (t for t in tracks if t.program == program and not t.is_percussion),
                None,
            )
            if existing is not None:
                existing.name = GM_PROGRAM_NAMES[program]
            else:
                tracks.append(_riff(GM_PROGRAM_NAMES[program], program))

        return Song(
            # ponytail: this is the deterministic stub generator (canned output
            # for tests/LLM-free dev, see module docstring) — prompt text isn't
            # threaded into the title because there's no real generation here to
            # derive a title from. Revisit once the real LLM-backed generator
            # lands (slice 2); the exporter itself already handles arbitrary
            # script/user input end-to-end via UTF-8 passthrough.
            title="Melos Sketch",
            tempo_bpm=request.tempo_bpm or 100,
            key=request.key or "C",
            time_signature=time_signature,
            tracks=tracks,
            sections=_sections(spec, time_signature.beats_per_bar),
            allow_sound_effects=any(
                program_for_name(name) in SOUND_EFFECT_PROGRAMS
                for name in request.include_instruments
                if not is_percussion_name(name)
            ),
        )


def _first_allowed(preferred: int, blocked: set[int | None]) -> int:
    if preferred not in blocked:
        return preferred
    return next(program for program in range(120) if program not in blocked)


def _sections(spec: LyricsSpec, bar: float) -> list[Section]:
    """One ``Section`` per ``[tag]``, one bar apart -- always aligned to a bar
    line regardless of time signature, and always ending before the melody
    track's end (``_melody`` sizes itself to guarantee that)."""
    return [
        Section(name=name, start_beat=i * bar)
        for i, name in enumerate(spec.section_names)
    ]


def _melody(program: int, spec: LyricsSpec, bar: float) -> Track:
    """The lead line. Sung words from the request replace the canned
    syllables (one word per note); the note count extends past the canned 8
    to fit every word and every requested section's bar (see ``_sections``),
    reusing the canned pitch contour cyclically for the extra notes.
    """
    words = spec.sung_text.split() if spec.has_lyrics else _LYRIC_SYLLABLES
    min_notes_for_sections = math.ceil(len(spec.section_names) * bar)
    note_count = max(len(_MELODY_PITCHES), len(words), min_notes_for_sections)
    return Track(
        name="Melody",
        program=program,
        is_vocal=True,
        notes=[
            Note(
                start=float(i),
                duration=1.0,
                pitch=_MELODY_PITCHES[i % len(_MELODY_PITCHES)],
                lyric=words[i] if i < len(words) else None,
            )
            for i in range(note_count)
        ],
    )


def _riff(name: str, program: int) -> Track:
    return Track(
        name=name,
        program=program,
        notes=[
            Note(start=i * 2.0, duration=2.0, pitch=pitch, velocity=80)
            for i, pitch in enumerate(_BASS_PITCHES)
        ],
    )


def _drums() -> Track:
    return Track(
        name="Drums",
        program=0,  # standard kit
        is_percussion=True,
        notes=[
            Note(
                start=float(beat),
                duration=0.5,
                pitch=_KICK if beat % 2 == 0 else _SNARE,
                velocity=90,
            )
            for beat in range(8)
        ],
    )
