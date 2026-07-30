"""Writing lyrics on request — a helper for the lyrics field, not a generator step.

Its output goes back into the same free-text field the user edits, so the song
generator only ever sees one path: whatever is in that field. That keeps
generation ignorant of where the words came from.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

_INSTRUCTIONS = (
    "You are Melos, a lyricist. Write song lyrics as plain text. "
    "Label each part on its own line with a bracket tag — [intro], [verse 1], "
    "[pre-chorus], [chorus], [bridge], [outro] — and put the sung lines under "
    "it. Do not use curly braces. Do not number or annotate the sung lines. "
    "When existing lyrics are given, treat them as the user's own work: keep "
    "what they wrote and extend or revise it as asked rather than starting "
    "over. When a style is given, match its genre, mood, and era."
)


class LyricRequest(BaseModel):
    """What to write about. Every field optional, but at least one is needed."""

    model_config = ConfigDict(extra="forbid")

    # The song prompt (Suno calls this "style"); shapes genre and mood.
    prompt: str | None = Field(default=None, max_length=4000)
    # Whatever is already in the lyrics field, tags and all.
    lyrics: str | None = Field(default=None, max_length=8000)
    # What the composer typed into the "help me write lyrics" box.
    topic: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _needs_a_signal(self) -> Self:
        if not any(
            field and field.strip() for field in (self.prompt, self.lyrics, self.topic)
        ):
            raise ValueError(
                "give at least one of prompt, lyrics, or topic to write from"
            )
        return self


class WrittenLyrics(BaseModel):
    """Lyrics text destined for the user's editable lyrics field."""

    model_config = ConfigDict(extra="forbid")

    lyrics: str = Field(min_length=1, max_length=8000)


class LyricWriter:
    def __init__(
        self,
        model: Model,
        *,
        use_native_output: bool,
        model_settings: ModelSettings | None = None,
    ) -> None:
        output_type = (
            NativeOutput(WrittenLyrics) if use_native_output else WrittenLyrics
        )
        self._agent = Agent(
            model,
            output_type=output_type,
            instructions=_INSTRUCTIONS,
            retries={"output": 2},
            model_settings=model_settings,
        )

    async def write(self, request: LyricRequest) -> WrittenLyrics:
        """Write or revise lyrics.

        Raises whatever pydantic-ai's ``Agent.run`` raises, e.g.
        ``UnexpectedModelBehavior`` once output retries are exhausted.
        """
        result = await self._agent.run(_prompt(request))
        return result.output


def _prompt(request: LyricRequest) -> str:
    parts = []
    if request.prompt and request.prompt.strip():
        parts.append(f"Song style: {request.prompt.strip()}")
    if request.topic and request.topic.strip():
        parts.append(f"What to write about: {request.topic.strip()}")
    if request.lyrics and request.lyrics.strip():
        parts.append(
            "Existing lyrics to keep and build on (preserve the user's lines,"
            f" tags included):\n{request.lyrics.strip()}"
        )
    else:
        parts.append("There are no existing lyrics; write them from scratch.")
    return "\n\n".join(parts)
