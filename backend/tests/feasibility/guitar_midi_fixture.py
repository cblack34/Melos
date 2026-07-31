"""Explicit, optional MIDI-fixture writer for manual GarageBand playback."""

from pathlib import Path

from feasibility.guitar_strum import (
    PerformanceEvent,
    expand_guitar_fixture,
    standard_gcad_fixture,
)
from melos.domain.models import Note, Song, TimeSignature, Track
from melos.midi.exporter import export_song


def note_compatible_events(events: tuple[PerformanceEvent, ...]) -> list[Note]:
    """Convert only the shared note fields at the existing Song/MIDI edge."""
    note_fields = {"start", "duration", "pitch", "velocity"}
    return [Note(**event.model_dump(include=note_fields)) for event in events]


def guitar_fixture_song() -> Song:
    """Build the smallest valid existing Song carrying the experimental events."""
    return Song(
        title="G C Am D guitar strum feasibility",
        tempo_bpm=112,
        key="G",
        time_signature=TimeSignature(numerator=4, denominator=4),
        tracks=[
            Track(
                name="Strummed Guitar",
                program=25,
                notes=note_compatible_events(
                    expand_guitar_fixture(standard_gcad_fixture())
                ),
            ),
            Track(
                name="Reference Bass",
                program=33,
                notes=[Note(start=0, duration=16, pitch=43)],
            ),
        ],
    )


def write_guitar_fixture_midi(destination: Path) -> Path:
    """Write only when invoked explicitly; normal tests never create artifacts."""
    destination.write_bytes(export_song(guitar_fixture_song()))
    return destination
