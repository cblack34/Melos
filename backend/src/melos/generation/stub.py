"""Deterministic stand-in for the AI generator (walking skeleton).

Returns a canned three-track arrangement; request meta (tempo, key, time
signature) overrides the defaults so the hard-constraint plumbing is real
end-to-end before any LLM exists.
"""

from melos.domain.generator import GenerationRequest
from melos.domain.models import Note, Song, TimeSignature, Track

_LYRIC_SYLLABLES = ["Me", "los", "sings", "a", "lit", "tle", "song", "now"]
_MELODY_PITCHES = [60, 62, 64, 65, 67, 65, 64, 60]  # C major run
_BASS_PITCHES = [36, 43, 41, 36]  # C G F C
_KICK, _SNARE = 36, 38  # GM percussion


class StubSongGenerator:
    async def generate(self, request: GenerationRequest) -> Song:
        melody = Track(
            name="Melody",
            program=73,  # flute
            notes=[
                Note(start=float(i), duration=1.0, pitch=pitch, lyric=syllable)
                for i, (pitch, syllable) in enumerate(
                    zip(_MELODY_PITCHES, _LYRIC_SYLLABLES, strict=True)
                )
            ],
        )
        bass = Track(
            name="Bass",
            program=33,  # fingered electric bass
            notes=[
                Note(start=i * 2.0, duration=2.0, pitch=pitch, velocity=80)
                for i, pitch in enumerate(_BASS_PITCHES)
            ],
        )
        drums = Track(
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
        return Song(
            # ponytail: prompt text stays out of the title until the exporter's
            # Latin-1 folding handles arbitrary user input end-to-end (slice 2).
            title="Melos Sketch",
            tempo_bpm=request.tempo_bpm or 100,
            key=request.key or "C",
            time_signature=request.time_signature
            or TimeSignature(numerator=4, denominator=4),
            tracks=[melody, bass, drums],
        )
