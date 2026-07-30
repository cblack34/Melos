"""Parsing the lyrics field: [sections], {directives}, and sung text."""

import time
import unicodedata

import pytest
from pydantic import ValidationError

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


@pytest.mark.parametrize("body", ["[]", "[  ]", "{}", "{  }"])
def test_empty_tag_body_falls_through_as_sung_text(body: str) -> None:
    # A bracket/brace pair with nothing (or only whitespace) inside is not a
    # meaningful section/directive name; treat it consistently either way
    # rather than letting the whitespace case produce a name of " ".
    spec = parse_lyrics(body)
    assert spec.section_names == [] and spec.directives == []
    assert spec.sung_lines == [body]


@pytest.mark.parametrize("width", [1_000, 4_000, 8_000])
def test_unterminated_tag_with_whitespace_body_parses_quickly(width: int) -> None:
    # Regression for catastrophic backtracking: a lazy body quantifier
    # followed by a greedy `\s*` that accepts the same characters used to
    # take ~24s at 4,000 spaces (unauthenticated, and well inside
    # GenerationRequest.lyrics's own 8,000-char limit). Must stay near-instant.
    start = time.monotonic()
    parse_lyrics("[" + " " * width)
    assert time.monotonic() - start < 1.0


def test_syllable_key_normalizes_unicode_form() -> None:
    # NFC and NFD encode the same visible word ("café") as different
    # codepoint sequences; text from different sources (LLM output vs. some
    # filesystem/editor paths) can arrive in either form.
    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", "café")
    assert nfc != nfd  # sanity check: genuinely different strings
    assert syllable_key(nfc) == syllable_key(nfd)


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


def test_punctuation_only_lyrics_are_rejected() -> None:
    # "..." has sung_lines (so has_lyrics is True) but normalizes to an empty
    # syllable_key, which would make Constraints.violations() reject any real
    # sung output forever, exhausting retries on every generation attempt.
    with pytest.raises(ValidationError, match="sung words"):
        GenerationRequest.model_validate({"prompt": "a song", "lyrics": "..."})


def test_too_many_lyric_sections_are_rejected() -> None:
    # generation/contract.py caps a song at 64 sections; a lyrics field
    # asking for more can never be satisfied by any valid compact output.
    lyrics = "\n".join(f"[section {i}]\nwords" for i in range(65))
    with pytest.raises(ValidationError, match="sections requested"):
        GenerationRequest.model_validate({"prompt": "a song", "lyrics": lyrics})


def test_overlong_lyric_section_name_is_rejected() -> None:
    # CompactSection.n caps section names at 80 chars; a longer requested
    # name can never be echoed back exactly by any valid compact output.
    lyrics = f"[{'x' * 81}]\nwords"
    with pytest.raises(ValidationError, match="too long"):
        GenerationRequest.model_validate({"prompt": "a song", "lyrics": lyrics})
