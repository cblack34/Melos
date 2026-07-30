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

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

# Whole-line tags only, so a bracket inside a sung line stays sung. A malformed
# tag ("[verse 1" with no closer) falls through as lyrics on purpose: the user
# hears the mistake immediately, which beats an error dialog over a typo.
_SECTION = re.compile(r"^\s*\[\s*(?P<name>[^\[\]]+?)\s*\]\s*$")
_DIRECTIVE = re.compile(r"^\s*\{\s*(?P<text>[^{}]+?)\s*\}\s*$")

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


def parse_lyrics(raw: str | None) -> LyricsSpec:
    """Split the lyrics field. Blank input means an instrumental, not an error."""
    if not raw or not raw.strip():
        return LyricsSpec()
    sections: list[str] = []
    directives: list[str] = []
    sung: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if section := _SECTION.match(line):
            sections.append(section["name"])
        elif directive := _DIRECTIVE.match(line):
            directives.append(directive["text"])
        else:
            sung.append(line.strip())
    return LyricsSpec(section_names=sections, directives=directives, sung_lines=sung)


def syllable_key(text: str) -> str:
    """Comparable form of sung text: what was sung, not how it was split.

    A model may break "lover" into ``lov`` + ``er`` or ``lov-`` + ``er``, and
    marks new words with a leading space. Casing, punctuation, and those
    markers are all irrelevant to whether the right words came back.
    """
    stripped = _SYLLABLE_NOISE.sub("", text.casefold())
    return "".join(
        ch for ch in stripped if not unicodedata.category(ch).startswith("P")
    )
