# Tech Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.14 | Locked |
| Validation / models | Pydantic V2 | Locked — single source of truth |
| AI harness | Pydantic AI | Locked |
| API | FastAPI | Locked |
| Frontend | React + TypeScript + Vite | Locked |
| Local runtime | Docker + Docker Compose | Locked |
| Python packaging | UV (workspaces if multiple packages) | Locked preference |
| Python type checking | ty (`uv run ty check`) | Locked — native Pydantic support, same vendor as uv/ruff. Beta: if it blocks a story (missing feature, false positive), fall back to mypy and record the swap here |
| TypeScript type checking | tsc (`npm run typecheck` = `tsc -b --noEmit`, see [`AGENTS.md`](../AGENTS.md#definition-of-done-self-verify--run-before-every-pr-is-merge-ready)) | Locked — industry standard |
| LLM access | OpenRouter, or a locally hosted model (Ollama / Docker) | Locked — Pydantic AI keeps the model swappable |
| LLM models | Agent researches and selects per AI task | Delegated — see below |
| MIDI writing | Deterministic library (e.g. mido) behind an interface | Suggestion — keep binary format out of the LLM |

Versions are pinned at scaffold time; lockfiles become authoritative.

## LLM provider and models

- Provider is OpenRouter (`OPENROUTER_API_KEY`, from the environment — never committed) or a locally hosted model via Ollama or Docker. Pydantic AI abstracts the provider, so keep the model/provider choice configurable and cheap to swap.
- OpenRouter is the one sanctioned paid service; introduce no others.
- The agent researches current model quality, cost, and structured-output reliability for each AI task (MIDI content generation, lyric generation, meta resolution, …), picks per task, and records each choice with a one-line why in this doc.

## Dependency rules

- Only very open licenses: MIT, Apache 2.0, or clear equivalents. No AGPL or strong copyleft.
- Prefer well-maintained existing libraries over custom implementations.
- Thin wrappers around libraries are acceptable; large "shoehorn" adapters are not.
- Most third-party libraries should sit behind interfaces/protocols so they can be swapped or mocked. Core, stable libraries may be used directly when the cost of abstraction is higher than the benefit.
