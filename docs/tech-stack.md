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
| Lyric generation (`MELOS_LYRIC_MODEL`) | `qwen3.6:27b` (reuse) | `anthropic/claude-sonnet-5` | Claude family tops creative-writing benchmarks; one prod model simplifies ops |
| Meta resolution | `qwen3.5:9b` (Apache-2.0) | `openai/gpt-5-nano` ($0.05/$0.40 per M) | Tiny fill-in schema; cheapest model with strict json_schema once routed via `require_parameters` (see caveat below) |

Budget fallback for prod generation: `deepseek/deepseek-v4-pro` (~10× cheaper, 384k max out, weaker constraint adherence).

Structured-output notes (verified against vendor docs):

- Local Ollama (≥0.5) enforces json_schema via grammar-constrained decoding → use Pydantic AI `NativeOutput`. Ollama **Cloud** does not enforce it. OpenRouter enforcement is per endpoint → `ToolOutput` (default) for portability, `provider: {require_parameters: true}` to route to enforcing endpoints.
- Ollama truncation risk is context fill, not output cap (`num_predict` defaults to −1). There is no per-request way to raise the context window through Ollama's OpenAI-compatible endpoint (confirmed against Ollama's own docs, `docs/api/openai-compatibility.mdx`: the only supported mechanism is a custom Modelfile with `PARAMETER num_ctx <N>`, or the server-wide `OLLAMA_CONTEXT_LENGTH` env var) — `ModelSettings(extra_body=...)` is silently ignored by Ollama's compat layer, not a working override.
- All local picks are Apache-2.0 (license gate); `pydantic-ai-slim[openai,openrouter]` is MIT (openai extra covers Ollama). Its `openai` extra transitively pulls in `certifi` and `tqdm` (MPL-2.0/file-level coverage) — reviewed and accepted because Melos uses them unmodified, their copyleft does not extend to separate Melos files, and distribution/source notices are recorded in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). Vite's build-only `lightningcss` dependency is handled by the same notice.
- **Model catalog (`backend/models.yaml`)** lets generation/meta models — and their per-model quirks (disabled reasoning, native-output override, token/timeout budgets) — be added or retuned by editing that one file, no code change. A model absent from the catalog still works through the code-based heuristics in `generation/llm.py` (provider inferred from `MELOS_LLM_PROVIDER`, DeepSeek-prefix reasoning fallback, etc.); the catalog is additive. `GET /api/models` serves it to the frontend; the UI's "⚙ Model" picker lets a request override the generation/meta model per call (validated against the catalog; the *server's own default* is trusted even when absent from the catalog, so overriding one task never fails because the other task's untouched default isn't catalogued). Must live inside `backend/` — the Docker build context is `./backend`, so a repo-root file would not reach the image. Provider `base_url` (ollama) is an **optional override** of `MELOS_OLLAMA_BASE_URL` / `LlmSettings.ollama_base_url` — leave it unset on the default `ollama` provider so compose's `host.docker.internal` (and any other env default) is not shadowed by a YAML `localhost`.
- **DeepSeek reasoning models on OpenRouter reject a forced `tool_choice`** — verified live: `deepseek/deepseek-v4-flash` 400s with "Thinking mode does not support this tool_choice" (pydantic-ai's `ToolOutput`, OpenRouter's default output mode, always forces one). OpenRouter's unified `reasoning: {"enabled": false}` sidesteps it. Confirmed **not** a general reasoning+tool_choice conflict: Claude Sonnet 5 and GPT-5-nano were tested with the identical forced `tool_choice` and have no issue, so the fix targets `deepseek/*` model names only (`generation/llm.py`) rather than disabling reasoning for every hosted model.

### Live quality-pass findings (2026-07-29, story #19)

Verified empirically against a running Ollama 0.32 on an M4 Pro / 48 GB:

- **Disable thinking on local models.** qwen3.x reasons in prose for thousands of tokens (~12.5 t/s) before the constrained JSON begins; a song generation blew the 32k context and 400'd. Ollama's OpenAI-compat endpoint honors `reasoning_effort: "none"` (top-level `think: false` and Qwen's `/no_think` are ignored). Applied automatically to local models in `generation/llm.py`; meta calls dropped from ~64s to ~2s.
- **Grammar ceiling: `maxItems` ≤ 1000.** llama.cpp's json_schema→grammar conversion fails ("failed to parse grammar") for `maxItems: 5000`; passes at 1000 (bisected). The compact contract's per-track note cap is 1000 accordingly.
- **Baseline result (local `qwen3.6:27b` + `qwen3.5:9b`):** 4/4 acceptance cases pass — meta echo exact, instrument include/exclude honored, lyrics aligned to note onsets, multi-track SMF. 1.5–10 min per song (`scripts/quality_run.py`).
- **Ollama Cloud:** free tier on this account covers `gpt-oss:120b-cloud` only (deepseek/glm/kimi cloud tags 403 → subscription). Cloud models don't enforce json_schema, so the factory automatically drops to ToolOutput for `*-cloud`/`*:cloud` tags; set `MELOS_GENERATION_MODEL=gpt-oss:120b-cloud` to use it.
- **Cloud result (`gpt-oss:120b-cloud`):** 4/4 acceptance cases pass, 1–4 min per song (~3× faster than local) with denser arrangements (up to 5 tracks / ~300 notes). One transient cloud-side 500 observed across two runs — the route's 502 mapping plus a client retry covers it. Good free upgrade over the local default when online.

### Live quality-pass findings (2026-07-30, story #31 — lyrics & sections)

Two failure modes that **unit tests cannot see** — the mocked suite was fully green while both were happening. Found by running real generations, fixed in the instructions, then confirmed by re-running:

- **Transliteration.** Asked to sing 咲く, the model emitted さく — the same sound, but no longer the characters the user typed. A lyric sheet should come back as written, so the instructions forbid transliterating, romanizing, translating, and respelling. This only shows up in non-phonetic scripts, so an English-only test suite would never catch it.
- **Melisma repetition.** The model emitted `Morningrning` and `Carryry`: the whole word on the first note, then a continuation fragment. Per-note guidance ("one syllable per note") was too weak; stating the rule the validator actually checks — concatenating `lyr` in note order reproduces the text exactly once, words spread over notes get *consecutive* pieces — fixed it.
- **Not a defect:** a model adding its own `Intro`/`Verse`/`Chorus` markers when the request specified no `[tags]`. Sections are optional and `_section_problems` deliberately leaves the model free there; a quality check that flagged this failed two otherwise-passing cases.
- **Result:** 7/7 cases pass on `gpt-oss:120b-cloud`, 1.5–6 min per song, including supplied lyrics with sections, Japanese lyrics, and structure-tags-only instrumentals. Transient cloud-side 500s remain occasional (three sightings across five runs) and are cloud-side, not ours.

### Generation progress events (M3)

While a song generates, the pipeline emits typed **progress events** (`domain/progress.py`) for phases such as meta resolution, composition start, model responses, validation retries (with attempt/max and human-readable reasons), export, completion, and failure. Every model response that supplies a provider request ID emits a `model_response` event, including responses later rejected and retried. With OpenRouter this is its `gen-…` generation ID, which the Activity window exposes for exact log/cost correlation. Callers pass an optional `ProgressReporter` into `SongGenerator.generate(..., progress=...)`. With no reporter, generation is silent.

**HTTP:** `POST /api/generate/stream` streams those events as SSE (`text/event-stream`, one message per phase; `event:` is the phase name, `data:` is the JSON `ProgressEvent`). The terminal `completed` event includes `filename` + `midi_base64` so the client can download without a job store. Classic `POST /api/generate` still returns a binary MIDI blob. Request validation (422) happens before the stream opens; pipeline failures end the stream with a terminal `failed` event (HTTP 200).

## Dependency rules

- Keep Melos source closed: prefer MIT, Apache 2.0, BSD, ISC, or clear equivalents.
- Weak, file-level copyleft such as MPL-2.0 is allowed only after review confirms that obligations remain limited to covered dependency files. Record the package, version, license, modification status, and corresponding source location in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
- No AGPL, GPL, strong/network copyleft, or other license that could require disclosure of Melos source.
- Prefer well-maintained existing libraries over custom implementations.
- Thin wrappers around libraries are acceptable; large "shoehorn" adapters are not.
- Most third-party libraries should sit behind interfaces/protocols so they can be swapped or mocked. Core, stable libraries may be used directly when the cost of abstraction is higher than the benefit.
