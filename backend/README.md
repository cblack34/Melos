# Melos backend

AI-powered music generation: creative prompts to multi-track MIDI. FastAPI service that validates
structured LLM output through Pydantic V2 models and deterministically converts it to `.mid` files.

## Setup

```bash
uv sync
```

## Self-verify

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

See [`AGENTS.md`](../AGENTS.md) for the full definition of done and [`docs/`](../docs) for the build
spec.
