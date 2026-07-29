"""FastAPI edge: HTTP request -> generator -> exporter -> MIDI download."""

import re

from fastapi import FastAPI, Response

from melos.domain.generator import GenerationRequest, SongGenerator
from melos.generation.stub import StubSongGenerator
from melos.midi.exporter import export_song


def create_app(generator: SongGenerator | None = None) -> FastAPI:
    """Composition root: wires the generator; routes only use the protocol."""
    song_generator = generator if generator is not None else StubSongGenerator()
    app = FastAPI(title="Melos")

    @app.post("/api/generate", response_class=Response)
    async def generate(request: GenerationRequest) -> Response:
        song = await song_generator.generate(request)
        # export_song is CPU-bound but sub-ms for realistic songs (benchmarked
        # ~54ms for an intentionally oversized 8-track/10-min arrangement);
        # revisit with asyncio.to_thread if profiling ever shows otherwise.
        return Response(
            content=export_song(song),
            media_type="audio/midi",
            headers={
                "Content-Disposition": f'attachment; filename="{_filename(song.title)}"'
            },
        )

    return app


def _filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"
    return f"{slug}.mid"


app = create_app()
