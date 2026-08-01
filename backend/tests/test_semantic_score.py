import ast
from collections.abc import Callable
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from melos.domain.semantic import (
    Beat,
    GuitarPart,
    SemanticScore,
    VocalPart,
    semantic_score_hash,
)


def beat(numerator: int, denominator: int = 1) -> dict[str, int]:
    return {"n": numerator, "d": denominator}


def fixture_data() -> dict[str, Any]:
    voicing = {
        "chord_symbol": "G",
        "strings": [
            {"string_index": index, "fret": fret}
            for index, fret in ((0, 3), (1, 2), (2, 0), (3, 0), (4, 0), (5, 3))
        ],
    }
    note = {
        "onset": beat(0),
        "duration": beat(1),
        "pitch": {"step": "G", "octave": 4},
    }
    return {
        "id": "whole-song",
        "title": "Whole Song Fixture",
        "tempo_bpm": 120,
        "key": "G",
        "meter": {"numerator": 4, "denominator": 4},
        "form": [
            {"id": "verse", "label": "Verse", "start": beat(0), "duration": beat(8)},
            {
                "id": "chorus-one",
                "label": "Chorus",
                "start": beat(8),
                "duration": beat(8),
            },
            {
                "id": "chorus-two",
                "label": "Chorus",
                "start": beat(16),
                "duration": beat(8),
            },
        ],
        "user_directives": [
            {
                "id": "user-intent",
                "text": "Keep the chorus bright.",
                "occurrence_id": "chorus-one",
            }
        ],
        "composer_enhancements": [
            {
                "id": "composer-intent",
                "text": "Use open voicings.",
                "occurrence_id": "chorus-two",
            }
        ],
        "patterns": [
            {
                "id": "guitar-strum",
                "duration": beat(2),
                "steps": [
                    {"onset": beat(0), "direction": "down"},
                    {"onset": beat(1), "direction": "up"},
                ],
            }
        ],
        "parts": [
            {
                "family": "guitar",
                "id": "guitar",
                "name": "Acoustic guitar",
                "instrument": "acoustic-guitar",
                "pattern_uses": [
                    {
                        "id": "chorus-one-use",
                        "occurrence_id": "chorus-one",
                        "pattern_id": "guitar-strum",
                        "start": beat(8),
                        "repetitions": 4,
                        "voicing": voicing,
                    },
                    {
                        "id": "chorus-two-use",
                        "occurrence_id": "chorus-two",
                        "pattern_id": "guitar-strum",
                        "start": beat(16),
                        "repetitions": 4,
                        "voicing": voicing,
                    },
                ],
            },
            {
                "family": "melodic",
                "id": "melody",
                "name": "Counter melody",
                "instrument": "lead-synth",
                "phrases": [
                    {
                        "id": "verse-melody",
                        "occurrence_id": "verse",
                        "start": beat(0),
                        "notes": [note],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "lead-vocal",
                "name": "Lead vocal",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "lead-chorus",
                        "occurrence_id": "chorus-one",
                        "start": beat(8),
                        "notes": [note],
                        "lyric_assignments": [
                            {
                                "id": "primary-we",
                                "token_id": "token-we",
                                "role": "primary",
                                "syllables": [
                                    {
                                        "text": "We",
                                        "note_indexes": [0],
                                        "pronunciation": "wi",
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "answer-vocal",
                "name": "Answer vocal",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "answer-chorus",
                        "occurrence_id": "chorus-one",
                        "start": beat(10),
                        "notes": [note, {**note, "onset": beat(1)}],
                        "lyric_assignments": [
                            {
                                "id": "primary-rise",
                                "token_id": "token-rise",
                                "role": "primary",
                                "syllables": [{"text": "rise", "note_indexes": [0, 1]}],
                            }
                        ],
                    }
                ],
            },
            {
                "family": "vocal",
                "id": "harmony-vocal",
                "name": "Harmony vocal",
                "instrument": "voice",
                "phrases": [
                    {
                        "id": "harmony-chorus",
                        "occurrence_id": "chorus-one",
                        "start": beat(12),
                        "notes": [note],
                        "lyric_assignments": [
                            {
                                "id": "harmony-we",
                                "token_id": "token-we",
                                "role": "harmony",
                                "syllables": [{"text": "We", "note_indexes": [0]}],
                            }
                        ],
                    }
                ],
            },
        ],
        "lyric_tokens": [
            {
                "id": "token-we",
                "occurrence_id": "chorus-one",
                "source_index": 0,
                "display_text": "We",
            },
            {
                "id": "token-rise",
                "occurrence_id": "chorus-one",
                "source_index": 1,
                "display_text": " rise",
            },
            {
                "id": "token-punctuation",
                "occurrence_id": "chorus-one",
                "source_index": 2,
                "display_text": "!",
                "is_singable": False,
            },
        ],
        "boundary_uses": [
            {
                "id": "chorus-boundary",
                "part_id": "guitar",
                "pattern_id": "guitar-strum",
                "from_occurrence_id": "chorus-one",
                "to_occurrence_id": "chorus-two",
                "start": beat(15),
                "duration": beat(2),
                "voicing": voicing,
            }
        ],
        "realization": {"recipe_version": "fixture-v1", "seed": 7},
    }


def score(**overrides: Any) -> SemanticScore:
    return SemanticScore.model_validate({**fixture_data(), **overrides})


def test_beat_json_round_trip_is_exact_reduced_and_supports_tuplets() -> None:
    tuplet = Beat(n=1, d=3)
    assert Beat.model_validate_json(tuplet.model_dump_json()) == tuplet
    assert tuplet.model_dump(mode="json", by_alias=True) == {"n": 1, "d": 3}
    with pytest.raises(ValidationError, match="reduced"):
        Beat(n=2, d=6)
    with pytest.raises(ValidationError):
        Beat.model_validate(0.1)
    data = fixture_data()
    data["form"][0]["duration"] = beat(0)
    with pytest.raises(ValidationError, match="duration must be positive"):
        SemanticScore.model_validate(data)


def test_score_json_round_trip_and_hash_are_deterministic() -> None:
    fixture = score()
    assert SemanticScore.model_validate_json(fixture.model_dump_json()) == fixture
    assert semantic_score_hash(fixture) == semantic_score_hash(score())
    assert semantic_score_hash(fixture) == (
        "129c1ab061c45294177d5c42b86e87ff9ffcccf0f0105c5ca6809bc0b303e471"
    )


def test_schema_020_keeps_key_and_semantic_instrument_identity_canonical() -> None:
    """GM programs remain a recipe concern, not semantic-score data."""
    data = fixture_data()
    data["schema_version"] = "0.2.0"
    data["key"] = "G"
    data["parts"][0]["instrument"] = "acoustic-guitar"
    data["parts"][1]["instrument"] = "lead-synth"
    for part in data["parts"][2:]:
        part["instrument"] = "voice"

    fixture = SemanticScore.model_validate(data)

    assert fixture.schema_version == "0.2.0"
    assert fixture.key == "G"
    assert [part.instrument for part in fixture.parts] == [
        "acoustic-guitar",
        "lead-synth",
        "voice",
        "voice",
        "voice",
    ]
    serialized = fixture.model_dump(mode="json")
    assert "program" not in str(serialized)
    assert "is_vocal" not in str(serialized)


@pytest.mark.parametrize("tempo_bpm", [nan, inf, -inf])
def test_score_and_canonical_hash_reject_non_finite_numbers(
    tempo_bpm: float,
) -> None:
    data = fixture_data()
    data["tempo_bpm"] = tempo_bpm
    with pytest.raises(ValidationError, match="finite number"):
        SemanticScore.model_validate(data)

    bypassed = score().model_copy(update={"tempo_bpm": tempo_bpm})
    with pytest.raises(ValueError, match="Out of range float values"):
        semantic_score_hash(bypassed)


def test_part_schema_is_discriminated_and_cross_family_extra_is_rejected() -> None:
    part_schema = SemanticScore.model_json_schema()["properties"]["parts"]["items"]
    assert part_schema["discriminator"]["propertyName"] == "family"
    assert set(part_schema["discriminator"]["mapping"]) == {
        "guitar",
        "melodic",
        "vocal",
    }
    data = fixture_data()
    data["parts"][0]["phrases"] = []
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SemanticScore.model_validate(data)
    unknown = fixture_data()
    unknown["parts"][0]["family"] = "keys"
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        SemanticScore.model_validate(unknown)


def test_repeated_choruses_share_one_pattern_and_measure_serialized_bytes() -> None:
    fixture = score()
    guitar = cast(GuitarPart, fixture.parts[0])
    serialized_bytes = len(fixture.model_dump_json().encode())
    assert len(fixture.patterns) == 1
    assert [use.pattern_id for use in guitar.pattern_uses] == [
        "guitar-strum",
        "guitar-strum",
    ]
    assert serialized_bytes == len(score().model_dump_json().encode())
    assert serialized_bytes < 10_000


def test_form_must_be_bar_aligned_and_contiguous() -> None:
    data = fixture_data()
    data["form"][1]["start"] = beat(9)
    with pytest.raises(ValidationError, match=r"bar lines|contiguous"):
        SemanticScore.model_validate(data)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda data: data["user_directives"][0].__setitem__("id", "whole-song"),
            "globally unique",
        ),
        (
            lambda data: data["parts"][0]["pattern_uses"][0].__setitem__(
                "pattern_id", "missing-pattern"
            ),
            "unknown pattern",
        ),
    ],
)
def test_duplicate_and_dangling_ids_are_rejected(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    data = fixture_data()
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        SemanticScore.model_validate(data)


def test_pattern_use_cannot_fall_outside_its_occurrence() -> None:
    data = fixture_data()
    data["parts"][0]["pattern_uses"][0]["repetitions"] = 5
    with pytest.raises(ValidationError, match="falls outside"):
        SemanticScore.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("to_occurrence_id", "verse", "adjacent occurrences"),
        ("start", beat(16), "cross the referenced"),
        ("duration", beat(3), "complete pattern repetitions"),
    ],
)
def test_boundary_use_requires_adjacency_and_a_crossing(
    field: str, value: Any, message: str
) -> None:
    data = fixture_data()
    data["boundary_uses"][0][field] = value
    with pytest.raises(ValidationError, match=message):
        SemanticScore.model_validate(data)


def test_boundary_replacement_operation_is_explicit_and_cannot_overlap() -> None:
    data = fixture_data()
    data["boundary_uses"][0]["operation"] = "add"
    with pytest.raises(ValidationError, match="replace"):
        SemanticScore.model_validate(data)

    data = fixture_data()
    overlapping = {
        **data["boundary_uses"][0],
        "id": "overlapping-boundary",
        "start": beat(31, 2),
    }
    data["boundary_uses"].append(overlapping)
    with pytest.raises(ValidationError, match="cannot overlap"):
        SemanticScore.model_validate(data)


def reverse_primary_performance_order(data: dict[str, Any]) -> None:
    lead = data["parts"][2]["phrases"][0]["lyric_assignments"][0]
    answer = data["parts"][3]["phrases"][0]["lyric_assignments"][0]
    lead["token_id"], answer["token_id"] = answer["token_id"], lead["token_id"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda data: data["parts"][2]["phrases"][0].__setitem__(
                "lyric_assignments",
                [],
            ),
            "exactly one primary",
        ),
        (
            lambda data: data["parts"][4]["phrases"][0]["lyric_assignments"][
                0
            ].__setitem__("role", "primary"),
            "exactly one primary",
        ),
        (reverse_primary_performance_order, "source order"),
    ],
)
def test_primary_lyrics_require_complete_unique_ordered_coverage(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    data = fixture_data()
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        SemanticScore.model_validate(data)


def test_lyric_tokens_are_occurrence_scoped_in_global_song_source_order() -> None:
    data = fixture_data()
    data["lyric_tokens"].append(
        {
            "id": "token-again",
            "occurrence_id": "chorus-two",
            "source_index": 3,
            "display_text": " Again",
        }
    )
    data["parts"][2]["phrases"].append(
        {
            "id": "lead-chorus-two",
            "occurrence_id": "chorus-two",
            "start": beat(16),
            "notes": [
                {
                    "onset": beat(0),
                    "duration": beat(1),
                    "pitch": {"step": "G", "octave": 4},
                }
            ],
            "lyric_assignments": [
                {
                    "id": "primary-again",
                    "token_id": "token-again",
                    "role": "primary",
                    "syllables": [{"text": "Again", "note_indexes": [0]}],
                }
            ],
        }
    )

    fixture = SemanticScore.model_validate(data)

    assert fixture.display_lyrics == "We rise! Again"
    assert [token.source_index for token in fixture.lyric_tokens] == [0, 1, 2, 3]
    token_schema = SemanticScore.model_json_schema()["$defs"]["LyricToken"]
    assert (
        "whole-song source stream"
        in token_schema["properties"]["source_index"]["description"]
    )


def test_primary_lyrics_may_start_simultaneously_across_vocal_parts() -> None:
    data = fixture_data()
    data["parts"][3]["phrases"][0]["start"] = beat(8)

    fixture = SemanticScore.model_validate(data)

    assert fixture.display_lyrics == "We rise!"


def test_non_primary_lyrics_and_immutable_display_tokens_are_legal() -> None:
    fixture = score()
    lead = cast(VocalPart, fixture.parts[2])
    answer = cast(VocalPart, fixture.parts[3])
    harmony = cast(VocalPart, fixture.parts[4])
    assert fixture.display_lyrics == "We rise!"
    assert lead.phrases[0].lyric_assignments[0].token_id == "token-we"
    assert answer.phrases[0].lyric_assignments[0].token_id == "token-rise"
    assert lead.phrases[0].lyric_assignments[0].syllables[0].pronunciation == "wi"
    assert answer.phrases[0].lyric_assignments[0].syllables[0].note_indexes == (
        0,
        1,
    )
    assert harmony.phrases[0].lyric_assignments[0].role == "harmony"
    with pytest.raises(ValidationError, match="frozen"):
        type(fixture.lyric_tokens[0]).__setattr__(
            fixture.lyric_tokens[0], "display_text", "They"
        )


def test_semantic_module_imports_only_standard_library_and_pydantic() -> None:
    source = Path(__file__).parents[1] / "src" / "melos" / "domain" / "semantic.py"
    tree = ast.parse(source.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imports <= {
        "__future__",
        "collections",
        "fractions",
        "hashlib",
        "itertools",
        "json",
        "math",
        "melos.domain.music",
        "typing",
        "pydantic",
    }
