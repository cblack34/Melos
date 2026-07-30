from io import BytesIO

import mido
import pytest
from mido import MidiFile

from melos.domain.models import Note, Song, TimeSignature, Track
from melos.midi.exporter import CHARSET, export_song


def make_song() -> Song:
    melody = Track(
        name="Melody",
        program=73,  # flute
        notes=[
            Note(start=0.0, duration=1.0, pitch=62, lyric="Hel"),
            Note(start=1.0, duration=1.0, pitch=64, lyric="lo"),
        ],
    )
    bass = Track(
        name="Bass",
        program=33,
        notes=[Note(start=0.0, duration=2.0, pitch=38)],
    )
    drums = Track(
        name="Drums",
        program=0,
        is_percussion=True,
        notes=[
            Note(start=0.0, duration=0.5, pitch=36),
            Note(start=1.0, duration=0.5, pitch=38),
        ],
    )
    return Song(
        title="Round Trip",
        tempo_bpm=112,
        key="Dm",
        time_signature=TimeSignature(numerator=3, denominator=4),
        tracks=[melody, bass, drums],
    )


def parse(data: bytes) -> MidiFile:
    return MidiFile(file=BytesIO(data), charset=CHARSET)


def test_round_trip_structure() -> None:
    midi = parse(export_song(make_song()))
    assert midi.type == 1
    assert len(midi.tracks) == 4  # meta track + 3 instrument tracks

    meta = {msg.type: msg for msg in midi.tracks[0]}
    assert meta["set_tempo"].tempo == mido.bpm2tempo(112)
    assert meta["key_signature"].key == "Dm"
    time_signature = meta["time_signature"]
    assert (time_signature.numerator, time_signature.denominator) == (3, 4)


def test_lyrics_become_meta_events_in_note_order() -> None:
    midi = parse(export_song(make_song()))
    lyrics = [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"]
    assert lyrics == ["Hel", "lo"]


def test_song_without_lyrics_has_no_lyric_events() -> None:
    song = make_song()
    for track in song.tracks:
        for note in track.notes:
            note.lyric = None
    midi = parse(export_song(song))
    assert not [msg for track in midi.tracks for msg in track if msg.type == "lyrics"]


def test_programs_and_channels() -> None:
    midi = parse(export_song(make_song()))
    programs = {}
    for track in midi.tracks[1:]:
        change = next(msg for msg in track if msg.type == "program_change")
        programs[change.channel] = change.program
    assert programs == {0: 73, 1: 33, 9: 0}  # percussion on channel 10 (index 9)

    drum_notes = [msg for msg in midi.tracks[3] if msg.type == "note_on"]
    assert drum_notes and all(msg.channel == 9 for msg in drum_notes)


def test_note_timing_uses_ticks_per_beat() -> None:
    midi = parse(export_song(make_song()))
    absolute = 0
    onsets = []
    for msg in midi.tracks[1]:
        absolute += msg.time
        if msg.type == "note_on":
            onsets.append(absolute)
    assert onsets == [0, midi.ticks_per_beat]


def test_export_is_deterministic() -> None:
    song = make_song()
    assert export_song(song) == export_song(song)


def test_tiny_duration_still_emits_off_after_on() -> None:
    song = make_song()
    song.tracks[0].notes[0].duration = 1e-9
    midi = parse(export_song(song))
    events = [msg.type for msg in midi.tracks[1] if msg.type in ("note_on", "note_off")]
    assert events[0] == "note_on" and events[1] == "note_off"


def test_smart_punctuation_in_lyric_is_normalized_not_crashed() -> None:
    song = make_song()
    song.tracks[0].notes[0].lyric = "don\u2019t\u2014stop"
    midi = parse(export_song(song))
    lyrics = [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"]
    assert lyrics[0] == "don't-stop"


def test_accents_survive_export() -> None:
    song = make_song()
    song.title = "Café Session"
    midi = parse(export_song(song))
    track_name = next(msg for msg in midi.tracks[0] if msg.type == "track_name")
    assert track_name.name == "Café Session"


@pytest.mark.parametrize("lyric", ["日本", "Привет", "안녕"])
def test_non_latin_script_lyrics_round_trip(lyric: str) -> None:
    song = make_song()
    song.tracks[0].notes[0].lyric = lyric
    midi = parse(export_song(song))
    assert next(m.text for m in midi.tracks[1] if m.type == "lyrics") == lyric


def test_control_and_format_characters_are_stripped_from_meta_text() -> None:
    song = make_song()
    song.tracks[0].notes[0].lyric = "safe‮malicious"
    midi = parse(export_song(song))
    lyrics = [msg.text for msg in midi.tracks[1] if msg.type == "lyrics"]
    assert lyrics[0] == "safemalicious"
