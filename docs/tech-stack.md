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

### Model choices per AI task (researched 2026-07-29)

Dev runs against local Ollama (default); production against OpenRouter. Switch via env (`MELOS_LLM_PROVIDER`, `MELOS_*_MODEL` — see `.env.example`); no code change.

| AI task | Dev (Ollama) | Prod (OpenRouter) | Why |
| --- | --- | --- | --- |
| MIDI content generation | `qwen3.6:27b` (Apache-2.0, 256K ctx) | `anthropic/claude-sonnet-5` ($2/$10 per M, 128k max out) | Qwen 27B leads IFEval among local models fitting 48 GB unified memory; Sonnet 5 has the best hard-constraint obedience + native strict json_schema |
| Lyric generation | `qwen3.6:27b` (reuse) | `anthropic/claude-sonnet-5` | Claude family tops creative-writing benchmarks; one prod model simplifies ops |
| Meta resolution | `qwen3.5:9b` (Apache-2.0) | `openai/gpt-5-nano` ($0.05/$0.40 per M) | Tiny fill-in schema; cheapest model with strict json_schema once routed via `require_parameters` (see caveat below) |

Budget fallback for prod generation: `deepseek/deepseek-v4-pro` (~10× cheaper, 384k max out, weaker constraint adherence).

Structured-output notes (verified against vendor docs):

- Local Ollama (≥0.5) enforces json_schema via grammar-constrained decoding → use Pydantic AI `NativeOutput`. Ollama **Cloud** does not enforce it. OpenRouter enforcement is per endpoint → `ToolOutput` (default) for portability, `provider: {require_parameters: true}` to route to enforcing endpoints.
- Ollama truncation risk is context fill, not output cap (`num_predict` defaults to −1). There is no per-request way to raise the context window through Ollama's OpenAI-compatible endpoint (confirmed against Ollama's own docs, `docs/api/openai-compatibility.mdx`: the only supported mechanism is a custom Modelfile with `PARAMETER num_ctx <N>`, or the server-wide `OLLAMA_CONTEXT_LENGTH` env var) — `ModelSettings(extra_body=...)` is silently ignored by Ollama's compat layer, not a working override.
- All local picks are Apache-2.0 (license gate); `pydantic-ai-slim[openai,openrouter]` is MIT (openai extra covers Ollama). Its `openai` extra transitively pulls in `certifi` and `tqdm` (both MPL-2.0, weak/file-level copyleft) — accepted as unavoidable given the OpenAI-SDK-based transport, and low-risk since Melos uses both unmodified.

### Live quality-pass findings (2026-07-29, story #19)

Verified empirically against a running Ollama 0.32 on an M4 Pro / 48 GB:

- **Disable thinking on local models.** qwen3.x reasons in prose for thousands of tokens (~12.5 t/s) before the constrained JSON begins; a song generation blew the 32k context and 400'd. Ollama's OpenAI-compat endpoint honors `reasoning_effort: "none"` (top-level `think: false` and Qwen's `/no_think` are ignored). Applied automatically to local models in `generation/llm.py`; meta calls dropped from ~64s to ~2s.
- **Grammar ceiling: `maxItems` ≤ 1000.** llama.cpp's json_schema→grammar conversion fails ("failed to parse grammar") for `maxItems: 5000`; passes at 1000 (bisected). The compact contract's per-track note cap is 1000 accordingly.
- **Baseline result (local `qwen3.6:27b` + `qwen3.5:9b`):** 4/4 acceptance cases pass — meta echo exact, instrument include/exclude honored, lyrics aligned to note onsets, multi-track SMF. 1.5–10 min per song (`scripts/quality_run.py`).
- **Ollama Cloud:** free tier on this account covers `gpt-oss:120b-cloud` only (deepseek/glm/kimi cloud tags 403 → subscription). Cloud models don't enforce json_schema, so the factory automatically drops to ToolOutput for `*-cloud`/`*:cloud` tags; set `MELOS_GENERATION_MODEL=gpt-oss:120b-cloud` to use it.
- **Cloud result (`gpt-oss:120b-cloud`):** 4/4 acceptance cases pass, 1–4 min per song (~3× faster than local) with denser arrangements (up to 5 tracks / ~300 notes). One transient cloud-side 500 observed across two runs — the route's 502 mapping plus a client retry covers it. Good free upgrade over the local default when online.

## Dependency rules

- Only very open licenses: MIT, Apache 2.0, or clear equivalents. No AGPL or strong copyleft.
- Prefer well-maintained existing libraries over custom implementations.
- Thin wrappers around libraries are acceptable; large "shoehorn" adapters are not.
- Most third-party libraries should sit behind interfaces/protocols so they can be swapped or mocked. Core, stable libraries may be used directly when the cost of abstraction is higher than the benefit.
