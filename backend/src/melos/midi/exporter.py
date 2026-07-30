"""Deterministic ``Song`` → Standard MIDI File bytes.

Format-1 SMF: track 0 carries song meta (tempo, time signature, key), then one
MIDI track per domain track. Lyric syllables become ``lyrics`` meta events at
their note's start tick.
"""

from io import BytesIO
from operator import itemgetter

import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack

from melos.domain.models import PERCUSSION_CHANNEL, Song, Track

TICKS_PER_BEAT = 480

# The SMF spec predates Unicode and names no encoding for meta text; mido
# defaults to Latin-1, which cannot hold Japanese, Korean, or Cyrillic lyrics.
# UTF-8 is what modern tooling assumes, so lyrics in any script survive export.
CHARSET = "utf-8"

# At the same tick: lyric before note_off before note_on (avoids retriggering).
_LYRIC, _NOTE_OFF, _NOTE_ON = 0, 1, 2

# Files are written UTF-8 (see CHARSET) so lyrics in any script survive. Smart
# punctuation is still normalized to ASCII: LLM-generated text is full of curly
# quotes and em dashes, and plain equivalents render more predictably across
# DAWs than the typographic originals.
_SMART_PUNCTUATION = {
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2026": "...",  # horizontal ellipsis
}


def _to_smf_text(text: str) -> str:
    for smart, plain in _SMART_PUNCTUATION.items():
        text = text.replace(smart, plain)
    return text


def export_song(song: Song) -> bytes:
    midi = MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT, charset=CHARSET)
    midi.tracks.append(_meta_track(song))
    for track, channel in zip(song.tracks, _channels(song.tracks), strict=True):
        midi.tracks.append(_midi_track(track, channel))
    buffer = BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()


def _channels(tracks: list[Track]) -> list[int]:
    melodic = (ch for ch in range(16) if ch != PERCUSSION_CHANNEL)
    return [
        PERCUSSION_CHANNEL if track.is_percussion else next(melodic) for track in tracks
    ]


def _meta_track(song: Song) -> MidiTrack:
    track = MidiTrack(
        [
            MetaMessage("track_name", name=_to_smf_text(song.title), time=0),
            # tempo_bpm is quarter-note BPM; do not pass song.time_signature here —
            # mido would rescale it by denominator/4, which is not the intended
            # semantics (bpm2tempo's default (4, 4) is exactly what we want).
            MetaMessage("set_tempo", tempo=mido.bpm2tempo(song.tempo_bpm), time=0),
            MetaMessage(
                "time_signature",
                numerator=song.time_signature.numerator,
                denominator=song.time_signature.denominator,
                time=0,
            ),
            MetaMessage("key_signature", key=song.key, time=0),
        ]
    )
    # Section markers are the only timed events here, and Song guarantees they
    # are ordered, so deltas accumulate from the tick-0 meta above.
    previous_tick = 0
    for section in song.sections:
        tick = _tick(section.start_beat)
        track.append(
            MetaMessage(
                "marker", text=_to_smf_text(section.name), time=tick - previous_tick
            )
        )
        previous_tick = tick
    return track


def _midi_track(track: Track, channel: int) -> MidiTrack:
    events: list[tuple[int, int, Message | MetaMessage]] = []
    for note in track.notes:
        on_tick = _tick(note.start)
        off_tick = max(_tick(note.start + note.duration), on_tick + 1)
        if note.lyric:
            events.append(
                (on_tick, _LYRIC, MetaMessage("lyrics", text=_to_smf_text(note.lyric)))
            )
        events.append(
            (
                on_tick,
                _NOTE_ON,
                Message(
                    "note_on", channel=channel, note=note.pitch, velocity=note.velocity
                ),
            )
        )
        events.append(
            (
                off_tick,
                _NOTE_OFF,
                Message("note_off", channel=channel, note=note.pitch, velocity=0),
            )
        )
    events.sort(key=itemgetter(0, 1))

    midi_track = MidiTrack(
        [
            MetaMessage("track_name", name=_to_smf_text(track.name), time=0),
            Message("program_change", channel=channel, program=track.program, time=0),
        ]
    )
    previous_tick = 0
    for tick, _, message in events:
        midi_track.append(message.copy(time=tick - previous_tick))
        previous_tick = tick
    return midi_track


def _tick(beats: float) -> int:
    return round(beats * TICKS_PER_BEAT)
