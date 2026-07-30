"""FastAPI edge: HTTP request -> generator -> exporter -> MIDI download."""

import re

from fastapi import FastAPI, HTTPException, Response
from pydantic_ai.exceptions import (
    AgentRunError,
    ModelAPIError,
    UnexpectedModelBehavior,
    UserError,
)

from melos.config import LlmSettings
from melos.domain.generator import GenerationRequest, SongGenerator
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.llm import (
    generation_model,
    generation_model_settings,
    lyric_model,
    lyric_model_settings,
    meta_model,
    meta_model_settings,
    supports_native_output,
)
from melos.generation.lyric_writer import (
    LyricRequest,
    LyricWriter,
    WrittenLyrics,
)
from melos.generation.meta import MetaResolver
from melos.generation.stub import StubSongGenerator
from melos.midi.exporter import export_song


def default_lyric_writer(settings: LlmSettings | None = None) -> LyricWriter:
    """Build the configured lyric writer. Uses the per-task lyric model."""
    settings = settings if settings is not None else LlmSettings()
    return LyricWriter(
        lyric_model(settings),
        use_native_output=supports_native_output(settings.lyric_model, settings),
        model_settings=lyric_model_settings(settings),
    )


def default_generator(settings: LlmSettings | None = None) -> SongGenerator:
    """Build the configured generator (creation separate from use)."""
    settings = settings if settings is not None else LlmSettings()
    if settings.generation_backend == "stub":
        return StubSongGenerator()
    return PydanticAISongGenerator(
        generation_model(settings),
        MetaResolver(
            meta_model(settings),
            use_native_output=supports_native_output(settings.meta_model, settings),
            model_settings=meta_model_settings(settings),
        ),
        use_native_output=supports_native_output(settings.generation_model, settings),
        model_settings=generation_model_settings(settings),
    )


def create_app(
    generator: SongGenerator | None = None,
    lyric_writer: LyricWriter | None = None,
) -> FastAPI:
    """Composition root: wires the AI collaborators; routes use them abstractly."""
    song_generator = generator if generator is not None else default_generator()
    app = FastAPI(title="Melos")

    def _writer() -> LyricWriter:
        # Built on first use so a generator-only app (tests, stub mode) never
        # constructs a provider client it will not call.
        nonlocal lyric_writer
        if lyric_writer is None:
            lyric_writer = default_lyric_writer()
        return lyric_writer

    @app.post("/api/lyrics")
    async def write_lyrics(request: LyricRequest) -> WrittenLyrics:
        try:
            return await _writer().write(request)
        except AgentRunError as error:
            raise _llm_unavailable(error) from error
        except UserError as error:
            # UserError is a sibling of AgentRunError (both subclass RuntimeError
            # directly), not a subclass, so it needs its own handler. Raised
            # synchronously by the provider (e.g. OpenRouterProvider) when the
            # lazily-built writer is misconfigured -- most commonly a missing
            # OPENROUTER_API_KEY. default_generator() builds eagerly in
            # create_app() so the same misconfiguration fails fast at startup;
            # the lyric writer is built lazily on first use (see _writer()
            # above), so this is the first point such a misconfiguration can
            # surface for it.
            raise HTTPException(
                status_code=500, detail=f"lyric writer misconfigured: {error}"
            ) from error

    @app.post("/api/generate", response_class=Response)
    async def generate(request: GenerationRequest) -> Response:
        try:
            song = await song_generator.generate(request)
        except AgentRunError as error:
            raise _llm_unavailable(error) from error
        try:
            # export_song is CPU-bound but sub-ms for realistic songs (benchmarked
            # ~54ms for an intentionally oversized 8-track/10-min arrangement);
            # revisit with asyncio.to_thread if profiling ever shows otherwise.
            content = export_song(song)
        except ValueError as error:
            # Defensive: export_song is UTF-8 end to end and no longer raises
            # ValueError for any Song that passed domain validation, but the
            # domain/export boundary is exactly where an encoding assumption
            # would surface first if that ever changed.
            raise HTTPException(
                status_code=502, detail=f"song could not be exported: {error}"
            ) from error
        return Response(
            content=content,
            media_type="audio/midi",
            headers={
                "Content-Disposition": f'attachment; filename="{_filename(song.title)}"'
            },
        )

    return app


def _llm_unavailable(error: AgentRunError) -> HTTPException:
    """Map a pydantic-ai failure onto a 502 the client can show the user.

    ``UnexpectedModelBehavior`` means output retries were exhausted — the model
    kept violating the constraints or the schema. ``ModelAPIError`` is the
    provider failing. Everything else in the ``AgentRunError`` hierarchy (e.g.
    ``UsageLimitExceeded``) is a sibling of those two, not a subclass, so the
    bare branch is a real catch-all rather than dead code.
    """
    if isinstance(error, UnexpectedModelBehavior):
        detail = f"generation failed: {error}"
    elif isinstance(error, ModelAPIError):
        detail = f"LLM provider error: {error}"
    else:
        detail = f"agent run failed: {error}"
    return HTTPException(status_code=502, detail=detail)


def _filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"
    return f"{slug}.mid"


# No module-level `app`: building the generator (and its provider client) at
# import time is a side effect that fires on any import, including test
# collection. Served via `uvicorn --factory melos.api.app:create_app`.
