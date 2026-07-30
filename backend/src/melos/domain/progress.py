"""Typed progress events for a song generation run.

Emitted by the generate pipeline (meta → composition → validation retries →
done/fail). Export phases are defined here so the HTTP layer (SSE story) can
report them with the same contract; this module does not know about HTTP.
"""

from contextvars import ContextVar, Token
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ProgressPhase = Literal[
    "request_received",
    "meta_started",
    "meta_skipped",
    "meta_completed",
    "generation_started",
    "validation_retry",
    "generation_completed",
    "export_started",
    "export_completed",
    "failed",
    "completed",
]


class ProgressEvent(BaseModel):
    """One step in a generation run, safe to serialize for SSE later."""

    model_config = ConfigDict(extra="forbid")

    phase: ProgressPhase
    message: str | None = None
    # validation_retry: 1-based attempt that was rejected, and configured max
    # output retries (pydantic-ai ``retries={"output": N}``).
    attempt: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)
    model_id: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ProgressReporter(Protocol):
    async def report(self, event: ProgressEvent) -> None: ...


class ListProgressReporter:
    """In-memory sink for tests and simple callers."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def report(self, event: ProgressEvent) -> None:
        self.events.append(event)


_current: ContextVar[ProgressReporter | None] = ContextVar(
    "melos_progress_reporter", default=None
)


def bind_progress(reporter: ProgressReporter | None) -> Token[ProgressReporter | None]:
    """Bind a reporter for the current task; pair with ``reset_progress``."""
    return _current.set(reporter)


def reset_progress(token: Token[ProgressReporter | None]) -> None:
    _current.reset(token)


async def report_progress(event: ProgressEvent) -> None:
    """Emit to the reporter bound for this task, if any (no-op otherwise)."""
    reporter = _current.get()
    if reporter is not None:
        await reporter.report(event)
