"""FastAPI edge: HTTP request -> generator -> exporter -> MIDI download."""

import re

from fastapi import FastAPI, HTTPException, Response
from pydantic_ai.exceptions import AgentRunError, ModelAPIError, UnexpectedModelBehavior

from melos.config import LlmSettings
from melos.domain.generator import GenerationRequest, SongGenerator
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.llm import (
    generation_model,
    generation_model_settings,
    meta_model,
    meta_model_settings,
    supports_native_output,
)
from melos.generation.meta import MetaResolver
from melos.generation.stub import StubSongGenerator
from melos.midi.exporter import export_song


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


def create_app(generator: SongGenerator | None = None) -> FastAPI:
    """Composition root: wires the generator; routes only use the protocol."""
    song_generator = generator if generator is not None else default_generator()
    app = FastAPI(title="Melos")

    @app.post("/api/generate", response_class=Response)
    async def generate(request: GenerationRequest) -> Response:
        try:
            song = await song_generator.generate(request)
        except UnexpectedModelBehavior as error:
            # Retries exhausted: the model kept violating constraints/schema.
            raise HTTPException(
                status_code=502, detail=f"generation failed: {error}"
            ) from error
        except ModelAPIError as error:
            raise HTTPException(
                status_code=502, detail=f"LLM provider error: {error}"
            ) from error
        except AgentRunError as error:
            # Catch-all for the rest of the AgentRunError hierarchy (e.g.
            # UsageLimitExceeded) — a sibling of, not a superclass of, the two
            # exceptions above.
            raise HTTPException(
                status_code=502, detail=f"agent run failed: {error}"
            ) from error
        try:
            # export_song is CPU-bound but sub-ms for realistic songs (benchmarked
            # ~54ms for an intentionally oversized 8-track/10-min arrangement);
            # revisit with asyncio.to_thread if profiling ever shows otherwise.
            content = export_song(song)
        except ValueError as error:
            # e.g. an LLM-generated title/name/lyric outside the MIDI file's
            # Latin-1 charset that the exporter's folding couldn't fix.
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


def _filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"
    return f"{slug}.mid"


# No module-level `app`: building the generator (and its provider client) at
# import time is a side effect that fires on any import, including test
# collection. Served via `uvicorn --factory melos.api.app:create_app`.
