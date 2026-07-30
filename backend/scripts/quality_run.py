"""Acceptance quality run: real generations checked against acceptance.md.

Runs the configured generator (default: local Ollama models from settings) on
varied prompts and verifies each output MIDI programmatically — track count,
meta echo, instrument constraints, GM validity, percussion channel, lyric
alignment. Writes the .mid files for the human DAW check.

Usage: uv run python scripts/quality_run.py [--out DIR] [--cases N]
"""

import argparse
import asyncio
import functools
import re
import time
import unicodedata
from io import BytesIO
from pathlib import Path

import mido

from melos.api.app import default_generator
from melos.domain.generator import GenerationRequest
from melos.domain.gm import program_for_name
from melos.domain.lyrics import closest_by_syllables, syllable_key

CASES: list[tuple[str, dict[str, object]]] = [
    (
        "free-rein",
        {"prompt": "an upbeat synthwave track for a night drive"},
    ),
    (
        "fixed-meta-sung",
        {
            "prompt": "a gentle sung folk ballad about a river carrying memories home",
            "tempo_bpm": 84,
            "key": "Em",
            "time_signature": {"numerator": 3, "denominator": 4},
        },
    ),
    (
        "instrument-constraints",
        {
            "prompt": "a bright jazz tune",
            "include_instruments": ["Trumpet", "drums"],
            "exclude_instruments": ["Flute"],
            "tempo_bpm": 132,
        },
    ),
    (
        "no-drums-instrumental",
        {
            "prompt": "a calm ambient instrumental piece, no percussion",
            "exclude_instruments": ["drums"],
            "key": "C",
        },
    ),
    (
        "supplied-lyrics-and-sections",
        {
            "prompt": "a warm acoustic folk song",
            "tempo_bpm": 92,
            "key": "G",
            "lyrics": (
                "[verse 1]\n"
                "{just guitar and voice}\n"
                "Morning light across the kitchen floor\n"
                "The kettle sings a note I know\n"
                "[chorus]\n"
                "{bring in the bass and light drums}\n"
                "Carry me home\n"
                "Carry me home again\n"
            ),
        },
    ),
    (
        "non-latin-lyrics",
        {
            "prompt": "a gentle J-pop ballad",
            "tempo_bpm": 78,
            "lyrics": "[verse 1]\nさくらが咲く\n[chorus]\n君を思う\n",
        },
    ),
    (
        "structure-only-no-lyrics",
        {
            "prompt": "an instrumental post-rock build",
            "tempo_bpm": 100,
            "lyrics": (
                "[intro]\n"
                "{just guitar}\n"
                "[build]\n"
                "{add drums and bass}\n"
                "[climax]\n"
                "{full band}\n"
            ),
        },
    ),
]


def check_case(request: GenerationRequest, data: bytes) -> list[str]:
    failures: list[str] = []
    # charset must match exporter.py's CHARSET ("utf-8"); mido's own default
    # ("latin1") mangles any non-Latin-1 lyric/marker text on read-back.
    midi = mido.MidiFile(file=BytesIO(data), charset="utf-8")
    meta = {msg.type: msg for msg in midi.tracks[0]}
    instrument_tracks = midi.tracks[1:]

    if midi.type != 1 or len(instrument_tracks) < 2:
        failures.append(f"expected multi-track SMF, got {len(instrument_tracks)}")

    if request.tempo_bpm is not None:
        got = round(mido.tempo2bpm(meta["set_tempo"].tempo), 2)
        if abs(got - request.tempo_bpm) > 0.5:  # set_tempo rounds to whole µs
            failures.append(f"tempo {got} != requested {request.tempo_bpm}")
    if request.key is not None and meta["key_signature"].key != request.key:
        failures.append(f"key {meta['key_signature'].key} != requested {request.key}")
    if request.time_signature is not None:
        got_ts = (meta["time_signature"].numerator, meta["time_signature"].denominator)
        want_ts = (request.time_signature.numerator, request.time_signature.denominator)
        if got_ts != want_ts:
            failures.append(f"time signature {got_ts} != requested {want_ts}")

    programs = {
        msg.program
        for track in instrument_tracks
        for msg in track
        if msg.type == "program_change" and msg.channel != 9
    }
    note_channels = {
        msg.channel
        for track in instrument_tracks
        for msg in track
        if msg.type == "note_on"
    }

    for included in request.include_instruments:
        program = program_for_name(included)
        if program is None:  # percussion pseudo-name
            if 9 not in note_channels:
                failures.append("required percussion track missing")
        elif program not in programs:
            failures.append(f"required instrument missing: {included}")
    for excluded in request.exclude_instruments:
        program = program_for_name(excluded)
        if program is None:
            if 9 in note_channels:
                failures.append("percussion present despite exclusion")
        elif program in programs:
            failures.append(f"excluded instrument present: {excluded}")

    if invalid := {p for p in programs if not 0 <= p <= 127}:
        failures.append(f"invalid GM programs: {invalid}")

    spec = request.lyrics_spec
    markers = [msg.text for msg in midi.tracks[0] if msg.type == "marker"]
    if spec.section_names and [name.casefold() for name in markers] != [
        name.casefold() for name in spec.section_names
    ]:
        failures.append(f"markers {markers} != requested {spec.section_names}")
    # Markers with no [tags] requested are deliberately NOT a failure: sections
    # are optional, ai.py's own _section_problems leaves the model free when the
    # user asked for none, and a model that labels Intro/Verse/Chorus unprompted
    # is producing better output, not violating anything.
    if spec.has_lyrics or "sung" in request.prompt:
        _lyrics_aligned(instrument_tracks, failures)
    if spec.has_lyrics:
        sung = _sung_syllables(instrument_tracks, spec.sung_text)
        if syllable_key(sung) != syllable_key(spec.sung_text):
            failures.append(f"sung {sung[:80]!r} != requested {spec.sung_text[:80]!r}")
        sung_boundary = _boundary_key(sung)
        for tag in spec.section_names:
            tag_boundary = _boundary_key(tag)
            if tag_boundary and re.search(
                rf"\b{re.escape(tag_boundary)}\b", sung_boundary
            ):
                failures.append(f"section tag {tag!r} was sung")
    return failures


def _boundary_key(text: str) -> str:
    """Like ``syllable_key``, but keeps word breaks so ``\\b`` matching works.

    ``syllable_key`` strips all whitespace, which turns a "was this section
    tag sung" check into an unbounded substring test (e.g. "verse" would
    match inside "universe"). This keeps spaces so a regex word-boundary
    match only fires on the whole word.
    """
    normalized = unicodedata.normalize("NFC", text).casefold()
    return "".join(
        ch for ch in normalized if not unicodedata.category(ch).startswith("P")
    )


def _sung_syllables(tracks: list[mido.MidiTrack], wanted: str) -> str:
    """Syllables from the track whose text best matches what was requested.

    Multiple vocal tracks may legitimately carry ``lyr`` (harmony parts get
    their own track too, per ``ai.py``'s generation-time rules), so picking
    the "lead" by raw character count can pick a harmony track instead.
    Match by content — mirroring how ``ai.py``'s own ``_lyric_problems``
    identifies the closest singer — rather than by length.
    """
    per_track = [
        "".join(msg.text for msg in track if msg.type == "lyrics") for track in tracks
    ]
    if not per_track:
        return ""
    wanted_key = syllable_key(wanted)
    exact = [sung for sung in per_track if syllable_key(sung) == wanted_key]
    if exact:
        return exact[0]
    return closest_by_syllables(per_track, wanted, text=lambda sung: sung)


def _lyrics_aligned(tracks: list[mido.MidiTrack], failures: list[str]) -> bool:
    lyric_ticks: set[int] = set()
    note_on_ticks: set[int] = set()
    total_lyrics = 0
    for track in tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "lyrics":
                total_lyrics += 1
                lyric_ticks.add(tick)
            elif msg.type == "note_on" and msg.velocity > 0:
                note_on_ticks.add(tick)
    if total_lyrics == 0:
        failures.append("sung prompt produced no lyric events")
        return False
    unaligned = lyric_ticks - note_on_ticks
    if unaligned:
        failures.append(
            f"{len(unaligned)}/{total_lyrics} lyric events not at a note onset"
        )
        return False
    return True


# Live progress even when stdout is redirected to a file.
print = functools.partial(print, flush=True)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("quality_out"))
    parser.add_argument("--cases", type=int, default=len(CASES))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from melos.midi.exporter import export_song

    generator = default_generator()
    failed = 0
    for name, spec in CASES[: args.cases]:
        request = GenerationRequest.model_validate(spec)
        started = time.monotonic()
        try:
            song = await generator.generate(request)
            data = export_song(song)
            (args.out / f"{name}.mid").write_bytes(data)
            problems = check_case(request, data)
        except Exception as error:  # report and continue: a run surveys all cases
            print(
                f"FAIL {name}: error after {time.monotonic() - started:.0f}s: {error}"
            )
            failed += 1
            continue
        elapsed = time.monotonic() - started
        notes = sum(len(track.notes) for track in song.tracks)
        stats = f"{elapsed:.0f}s, {len(song.tracks)} tracks, {notes} notes"
        if problems:
            failed += 1
            print(f"FAIL {name} ({stats})")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"PASS {name} ({stats})")
    total = len(CASES[: args.cases])
    print(f"\n{total - failed}/{total} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
