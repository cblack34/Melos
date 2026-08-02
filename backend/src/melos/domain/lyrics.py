"""Parsing the lyrics field into the three things it can contain.

One free-text field carries all of it, Suno-style:

    [verse 1]
    {piano and voice only}
    lyrics to verse 1...

``[section]`` tags name spans of the arrangement and are verified against the
generated song. ``{directive}`` lines are creative guidance passed to the model
but not verified — mapping prose like "piano and voice only" onto program
numbers and silent spans needs its own AI call (roadmap). Everything else is
sung text, and only sung text may become lyric meta events.
"""

import difflib
import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Whole-line tags only, so a bracket inside a sung line stays sung. A malformed
# tag ("[verse 1" with no closer) falls through as lyrics on purpose: the user
# hears the mistake immediately, which beats an error dialog over a typo.
#
# Padding is stripped in Python (see parse_lyrics), not in the pattern: a lazy
# body (`+?`) followed by a greedy `\s*` that accepts the same characters is
# catastrophically ambiguous on an unterminated tag whose body is whitespace
# (e.g. "[" + " " * 8000, which fits GenerationRequest.lyrics's own size
# limit) — the engine explores every split point between the two quantifiers
# before concluding there's no closing bracket. Measured against this exact
# shape of pattern: ~3s at 2,000 spaces, ~24s at 4,000. Keeping the character
# class as the only quantified, unambiguous span makes matching O(n).
_SECTION = re.compile(r"^\[(?P<name>[^\[\]]+)\]$")
_DIRECTIVE = re.compile(r"^\{(?P<text>[^{}]+)\}$")

# Word-boundary markers the model may emit around syllables ("lov-", " er").
_SYLLABLE_NOISE = re.compile(r"[\s\-_]+")


class LyricsSpec(BaseModel):
    """What the user's lyrics field asks for, split by kind."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    section_names: list[str] = Field(default_factory=list)
    directives: list[str] = Field(default_factory=list)
    sung_lines: list[str] = Field(default_factory=list)

    @property
    def has_lyrics(self) -> bool:
        return bool(self.sung_lines)

    @property
    def sung_text(self) -> str:
        return " ".join(self.sung_lines)


class _SourceItem(BaseModel):
    """One parsed line retained for whole-song composition input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    line_number: int = Field(ge=1)


class SourceSection(_SourceItem):
    kind: Literal["section"] = "section"
    name: str = Field(min_length=1, max_length=80)


class SourceDirective(_SourceItem):
    """A directive with its source location, not an inferred occurrence scope."""

    kind: Literal["directive"] = "directive"
    text: str = Field(min_length=1, max_length=1_000)


class SourceLyricLine(_SourceItem):
    kind: Literal["lyric"] = "lyric"
    id: str = Field(min_length=1, max_length=80, pattern=r"^lyric-line-[1-9][0-9]*$")
    text: str = Field(min_length=1, max_length=8_000)


SourceItem = Annotated[
    SourceSection | SourceDirective | SourceLyricLine,
    Field(discriminator="kind"),
]


class SongSource(BaseModel):
    """Ordered markup parsed without assigning directives to occurrences."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[SourceItem, ...] = ()

    @property
    def sections(self) -> tuple[SourceSection, ...]:
        return tuple(item for item in self.items if isinstance(item, SourceSection))

    @property
    def directives(self) -> tuple[SourceDirective, ...]:
        return tuple(item for item in self.items if isinstance(item, SourceDirective))

    @property
    def sung_text(self) -> str:
        """Match LyricsSpec's normalized sequence of non-markup source lines."""
        return " ".join(
            item.text for item in self.items if isinstance(item, SourceLyricLine)
        )


def parse_lyrics(raw: str | None) -> LyricsSpec:
    """Split the lyrics field. Blank input means an instrumental, not an error."""
    if not raw or not raw.strip():
        return LyricsSpec()
    sections: list[str] = []
    directives: list[str] = []
    sung: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if (section := _SECTION.match(stripped)) and section["name"].strip():
            sections.append(section["name"].strip())
        elif (directive := _DIRECTIVE.match(stripped)) and directive["text"].strip():
            directives.append(directive["text"].strip())
        else:
            sung.append(stripped)
    return LyricsSpec(section_names=sections, directives=directives, sung_lines=sung)


def parse_song_source(raw: str | None) -> SongSource:
    """Preserve ordered user markup for the semantic composer.

    Existing brace markup does not state whether a directive applies to the
    preceding section, the following section, or the whole song. Retaining its
    line number preserves source location without inventing that association.
    """
    if not raw or not raw.strip():
        return SongSource()
    items: list[SourceItem] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if (section := _SECTION.match(stripped)) and section["name"].strip():
            items.append(
                SourceSection(line_number=line_number, name=section["name"].strip())
            )
        elif (directive := _DIRECTIVE.match(stripped)) and directive["text"].strip():
            items.append(
                SourceDirective(line_number=line_number, text=directive["text"].strip())
            )
        else:
            items.append(
                SourceLyricLine(
                    id=f"lyric-line-{line_number}",
                    line_number=line_number,
                    text=stripped,
                )
            )
    return SongSource(items=tuple(items))


def syllable_key(text: str) -> str:
    """Comparable form of sung text: what was sung, not how it was split.

    A model may break "lover" into ``lov`` + ``er`` or ``lov-`` + ``er``, and
    marks new words with a leading space. Casing, punctuation, and those
    markers are all irrelevant to whether the right words came back.

    Normalized to NFC first: accented text from different sources (e.g. NFD
    from some filesystem/editor paths vs. the NFC an LLM typically emits) is
    otherwise the same visible word but a different codepoint sequence, which
    would spuriously fail this comparison.
    """
    stripped = _SYLLABLE_NOISE.sub("", unicodedata.normalize("NFC", text).casefold())
    return "".join(
        ch for ch in stripped if not unicodedata.category(ch).startswith("P")
    )


def closest_by_syllables[T](
    candidates: Sequence[T], wanted: str, *, text: Callable[[T], str]
) -> T:
    """Pick the candidate whose sung text best matches ``wanted``, by syllables.

    Used wherever a "which track actually sang the requested lyrics" decision
    has to survive a model splitting words into different syllable groups
    (``generation/ai.py``'s output validator, and ``scripts/quality_run.py``'s
    independent post-export check of the same claim) — comparison is on
    ``syllable_key``, not raw text, for the same reason ``syllable_key`` exists.
    """
    wanted_key = syllable_key(wanted)
    return max(
        candidates,
        key=lambda candidate: difflib.SequenceMatcher(
            None, syllable_key(text(candidate)), wanted_key
        ).ratio(),
    )
