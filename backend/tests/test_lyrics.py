"""Parsing the lyrics field: [sections], {directives}, and sung text."""

import pytest

from melos.domain.generator import GenerationRequest
from melos.domain.lyrics import parse_lyrics, syllable_key

SUNO_STYLE = """
[verse 1]
{Piano and voice only}
Morning light across the floor
Coffee going cold

[chorus]
{Start layering in the Acoustic Guitar and Bass}
Carry me home
"""


def test_splits_sections_directives_and_sung_lines() -> None:
    spec = parse_lyrics(SUNO_STYLE)
    assert spec.section_names == ["verse 1", "chorus"]
    assert spec.directives == [
        "Piano and voice only",
        "Start layering in the Acoustic Guitar and Bass",
    ]
    assert spec.sung_lines == [
        "Morning light across the floor",
        "Coffee going cold",
        "Carry me home",
    ]


@pytest.mark.parametrize("blank", [None, "", "   ", "\n\n\t\n"])
def test_blank_lyrics_mean_instrumental_not_an_error(blank: str | None) -> None:
    spec = parse_lyrics(blank)
    assert not spec.has_lyrics
    assert spec.section_names == [] and spec.directives == []


def test_empty_section_body_is_an_instrumental_section() -> None:
    # No auto-repeat: a bare [chorus] contributes a section and no words.
    spec = parse_lyrics("[intro]\n[verse]\nsome words\n[outro]")
    assert spec.section_names == ["intro", "verse", "outro"]
    assert spec.sung_lines == ["some words"]


def test_any_bracket_text_is_a_section_no_vocabulary_policed() -> None:
    spec = parse_lyrics("[the big weird drop]\nwords")
    assert spec.section_names == ["the big weird drop"]


def test_malformed_tag_falls_through_as_sung_text() -> None:
    # Deliberate: the user hears the mistake immediately, no error dialog.
    spec = parse_lyrics("[verse 1\nreal words")
    assert spec.section_names == []
    assert spec.sung_lines == ["[verse 1", "real words"]


def test_brackets_inside_a_sung_line_stay_sung() -> None:
    spec = parse_lyrics("she said [loudly] come home")
    assert spec.section_names == []
    assert spec.sung_lines == ["she said [loudly] come home"]


def test_tags_may_be_padded_with_whitespace() -> None:
    spec = parse_lyrics("  [ verse 1 ]  \n  { soft drums }  \nwords")
    assert spec.section_names == ["verse 1"]
    assert spec.directives == ["soft drums"]


def test_sung_text_joins_lines() -> None:
    assert parse_lyrics("one two\nthree").sung_text == "one two three"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("lov er", "lover"),  # syllable split
        ("lov- er", "lover"),  # hyphen convention
        (" Carry me home", "carry me home"),  # leading space + casing
        ("Don't stop!", "dont stop"),  # punctuation
        ("carry\nme", "carry me"),  # line breaks
    ],
)
def test_syllable_key_ignores_how_text_was_split(left: str, right: str) -> None:
    assert syllable_key(left) == syllable_key(right)


def test_syllable_key_still_distinguishes_different_words() -> None:
    assert syllable_key("carry me home") != syllable_key("carry me away")


def test_request_exposes_parsed_lyrics() -> None:
    request = GenerationRequest.model_validate(
        {"prompt": "a song", "lyrics": "[verse]\nsing this"}
    )
    assert request.lyrics_spec.section_names == ["verse"]
    assert request.lyrics_spec.sung_lines == ["sing this"]


def test_request_without_lyrics_is_instrumental() -> None:
    request = GenerationRequest.model_validate({"prompt": "an instrumental"})
    assert not request.lyrics_spec.has_lyrics
