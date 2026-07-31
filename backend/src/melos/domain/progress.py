"""Typed progress events for a song generation run.

Emitted by the generate pipeline (meta → composition → validation retries →
done/fail). Export phases are defined here so the HTTP layer (SSE story) can
report them with the same contract; this module does not know about HTTP.
"""

import asyncio
from collections.abc import AsyncIterator
from contextvars import ContextVar, Token
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ProgressPhase = Literal[
    "request_received",
    "meta_started",
    "meta_skipped",
    "meta_completed",
    "generation_started",
    "model_response",
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
    # validation_retry: 1-based output attempt that was rejected, and the
    # total attempts allowed (pydantic-ai retries={"output": N} ⇒ N+1 attempts).
    attempt: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1)
    # Model-response correlation data. OpenRouter uses a `gen-…` value for
    # provider_response_id; other providers may use a different request ID.
    model_id: str | None = None
    provider_response_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    # Terminal success payload for SSE (phase=completed only).
    filename: str | None = None
    midi_base64: str | None = None


class ProgressReporter(Protocol):
    async def report(self, event: ProgressEvent) -> None: ...


class ListProgressReporter:
    """In-memory sink for tests and simple callers."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def report(self, event: ProgressEvent) -> None:
        self.events.append(event)


class QueueProgressReporter:
    """Async queue sink for streaming progress (SSE)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()

    async def report(self, event: ProgressEvent) -> None:
        await self._queue.put(event)

    async def close(self) -> None:
        """Unblock consumers; ``None`` is the end-of-stream sentinel."""
        await self._queue.put(None)

    async def events(self) -> AsyncIterator[ProgressEvent]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item


_current: ContextVar[ProgressReporter | None] = ContextVar(
    "melos_progress_reporter", default=None
)


def bind_progress(reporter: ProgressReporter | None) -> Token[ProgressReporter | None]:
    """Bind a reporter for the current task; pair with ``reset_progress``."""
    return _current.set(reporter)


def reset_progress(token: Token[ProgressReporter | None]) -> None:
    _current.reset(token)


async def report_progress(event: ProgressEvent) -> None:
    """Emit to the reporter bound for this task, if any (no-op otherwise).

    Reporter errors are swallowed so observability cannot fail generation.
    """
    reporter = _current.get()
    if reporter is None:
        return
    try:
        await reporter.report(event)
    except Exception:
        # Intentionally broad: any sink bug/backpressure must not fail the run.
        return
