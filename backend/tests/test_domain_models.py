import pytest
from pydantic import ValidationError

from melos.domain.models import Note, Song, TimeSignature, Track


def note(**overrides: object) -> Note:
    return Note.model_validate(
        {"start": 0.0, "duration": 1.0, "pitch": 60, **overrides}
    )


def track(**overrides: object) -> Track:
    return Track.model_validate(
        {"name": "Lead", "program": 0, "notes": [note()], **overrides}
    )


def song(**overrides: object) -> Song:
    defaults: dict[str, object] = {
        "title": "Test Song",
        "tempo_bpm": 120,
        "key": "C",
        "time_signature": TimeSignature(numerator=4, denominator=4),
        "tracks": [track(), track(name="Bass", program=33)],
    }
    return Song.model_validate({**defaults, **overrides})


def test_valid_song_passes() -> None:
    assert len(song().tracks) == 2


def test_song_requires_multiple_tracks() -> None:
    with pytest.raises(ValidationError):
        song(tracks=[track()])


def test_sound_effect_program_rejected_by_default() -> None:
    gunshot = track(name="FX", program=127)
    with pytest.raises(ValidationError, match="sound-effect"):
        song(tracks=[track(), gunshot])


def test_sound_effect_program_allowed_when_requested() -> None:
    gunshot = track(name="FX", program=127)
    assert song(tracks=[track(), gunshot], allow_sound_effects=True)


def test_percussion_program_is_not_a_sound_effect() -> None:
    drums = track(name="Drums", program=120, is_percussion=True)
    assert song(tracks=[track(), drums])


def test_too_many_melodic_tracks_rejected() -> None:
    tracks = [track(name=f"T{i}") for i in range(16)]
    with pytest.raises(ValidationError, match="melodic tracks"):
        song(tracks=tracks)


def test_max_melodic_tracks_accepted() -> None:
    tracks = [track(name=f"T{i}") for i in range(15)]
    assert len(song(tracks=tracks).tracks) == 15


def test_multiple_percussion_tracks_rejected() -> None:
    drums_a = track(name="DrumsA", is_percussion=True)
    drums_b = track(name="DrumsB", is_percussion=True)
    with pytest.raises(ValidationError, match="percussion"):
        song(tracks=[track(), drums_a, drums_b])


def test_single_percussion_track_allowed() -> None:
    drums = track(name="Drums", is_percussion=True)
    assert song(tracks=[track(), drums])


def test_validate_assignment_rejects_invalid_mutation() -> None:
    built = song()
    with pytest.raises(ValidationError):
        built.tempo_bpm = 99999


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pitch", 128),
        ("pitch", -1),
        ("velocity", 0),
        ("velocity", 128),
        ("duration", 0),
        ("start", -0.5),
    ],
)
def test_note_bounds_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        note(**{field: value})


def test_invalid_program_rejected() -> None:
    with pytest.raises(ValidationError):
        track(program=128)


def test_invalid_key_rejected() -> None:
    with pytest.raises(ValidationError):
        song(key="H")


def test_invalid_time_signature_denominator_rejected() -> None:
    with pytest.raises(ValidationError):
        TimeSignature.model_validate({"numerator": 4, "denominator": 3})
