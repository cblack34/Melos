"""FastAPI edge: HTTP request -> generator -> exporter -> MIDI download."""

import re

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from pydantic_ai.exceptions import (
    AgentRunError,
    ModelAPIError,
    UnexpectedModelBehavior,
    UserError,
)

from melos.config import LlmSettings
from melos.domain.generator import GenerationRequest, SongGenerator
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.catalog import ModelCatalog, load_catalog
from melos.generation.llm import (
    build_model,
    catalog_lookup,
    generation_model_settings,
    lyric_model_settings,
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
        build_model(settings.lyric_model, settings),
        use_native_output=supports_native_output(settings.lyric_model, settings),
        model_settings=lyric_model_settings(settings.lyric_model, settings),
    )


def ai_generator(
    settings: LlmSettings,
    catalog: ModelCatalog,
    generation_model_id: str,
    meta_model_id: str,
) -> PydanticAISongGenerator:
    """Build an AI generator for one (generation model, meta model) pair.

    A model id present in ``catalog`` is built from its catalog entry
    (provider, reasoning, budgets); anything else falls back to
    ``llm.py``'s code-based heuristics keyed on ``settings.llm_provider``.
    """
    gen_entry, gen_provider = catalog_lookup("generation", generation_model_id, catalog)
    meta_entry, meta_provider = catalog_lookup("meta", meta_model_id, catalog)
    return PydanticAISongGenerator(
        build_model(generation_model_id, settings, gen_provider),
        MetaResolver(
            build_model(meta_model_id, settings, meta_provider),
            use_native_output=supports_native_output(
                meta_model_id, settings, meta_entry, meta_provider
            ),
            model_settings=meta_model_settings(
                meta_model_id, settings, meta_entry, meta_provider
            ),
        ),
        use_native_output=supports_native_output(
            generation_model_id, settings, gen_entry, gen_provider
        ),
        model_settings=generation_model_settings(
            generation_model_id, settings, gen_entry, gen_provider
        ),
    )


def default_generator(settings: LlmSettings | None = None) -> SongGenerator:
    """Build the configured generator (creation separate from use)."""
    settings = settings if settings is not None else LlmSettings()
    if settings.generation_backend == "stub":
        return StubSongGenerator()
    return ai_generator(
        settings, load_catalog(), settings.generation_model, settings.meta_model
    )


class ModelOption(BaseModel):
    id: str
    label: str


class ModelOptions(BaseModel):
    generation: list[ModelOption]
    meta: list[ModelOption]


def create_app(
    generator: SongGenerator | None = None,
    lyric_writer: LyricWriter | None = None,
    settings: LlmSettings | None = None,
    catalog: ModelCatalog | None = None,
) -> FastAPI:
    """Composition root: wires the AI collaborators; routes use them abstractly."""
    settings = settings if settings is not None else LlmSettings()
    # Named separately (not reassigned to `catalog`): route closures capture
    # free variables by name, and a type checker cannot assume a captured
    # name keeps its narrowed (non-None) type across the closure boundary.
    resolved_catalog = catalog if catalog is not None else load_catalog()
    song_generator = generator if generator is not None else default_generator(settings)
    app = FastAPI(title="Melos")

    def _writer() -> LyricWriter:
        # Built on first use so a generator-only app (tests, stub mode) never
        # constructs a provider client it will not call.
        nonlocal lyric_writer
        if lyric_writer is None:
            lyric_writer = default_lyric_writer(settings)
        return lyric_writer

    @app.get("/api/models")
    async def list_models() -> ModelOptions:
        return ModelOptions(
            generation=[
                ModelOption(id=e.id, label=e.label)
                for e in resolved_catalog.models.get("generation", [])
            ],
            meta=[
                ModelOption(id=e.id, label=e.label)
                for e in resolved_catalog.models.get("meta", [])
            ],
        )

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
        # An explicit per-request model choice wins even in stub mode --
        # picking a model in the UI is an unambiguous request for AI
        # generation. Unknown ids 422 rather than silently falling back,
        # since a typo'd model id should not quietly become the default. Only
        # the ids the client actually sent are checked against the catalog --
        # the server's own configured default is trusted either way, so
        # overriding one task never fails validation because the *other*
        # task's untouched default happens not to be catalogued.
        overridden = bool(request.generation_model or request.meta_model)
        gen_id = request.generation_model or settings.generation_model
        meta_id = request.meta_model or settings.meta_model
        unknown = [
            model_id
            for task, model_id in (
                ("generation", request.generation_model),
                ("meta", request.meta_model),
            )
            if model_id is not None
            and resolved_catalog.models.get(task)
            and resolved_catalog.find(task, model_id) is None
        ]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown model id(s) not in the catalog: {unknown}",
            )
        try:
            # ai_generator() itself can raise UserError (e.g. a missing API
            # key for the chosen provider), so it has to be inside this try —
            # not built before it, where that error would bypass the handler.
            generator_for_request = (
                ai_generator(settings, resolved_catalog, gen_id, meta_id)
                if overridden
                else song_generator
            )
            song = await generator_for_request.generate(request)
        except AgentRunError as error:
            raise _llm_unavailable(error) from error
        except UserError as error:
            # UserError is a sibling of AgentRunError (both subclass RuntimeError
            # directly), not a subclass, so it needs its own handler here too.
            # default_generator()'s eager construction in create_app() covers
            # provider-construction-time misconfiguration (e.g. a missing API
            # key), but Model.prepare_request() -- called inside Agent.run(),
            # not at construction -- can also raise UserError at request time
            # (e.g. an OpenRouter model profile that doesn't support tool
            # output). Without this handler that surfaces as a bare 500.
            raise HTTPException(
                status_code=500, detail=f"generator misconfigured: {error}"
            ) from error
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
