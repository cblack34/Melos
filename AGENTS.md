# AGENTS.md — Melos

Instructions for the AI agent that builds this app. This is the source of truth for **how** we work; the build spec (`docs/` — see the list at the bottom) is **what** to build.

**The code in every doc — types, snippets, file layouts, commands — is illustrative guidance, not a mandate.** The docs give the high-level *what*; you own the *how*: research, validate against current official docs, and follow best practice. The acceptance criteria and the described behavior are the contract — not any particular snippet.

## What this is

Melos is an AI-powered music generation web app that turns creative prompts into complete multi-track MIDI arrangements (with lyric support). Stack: Python 3.14, Pydantic V2, Pydantic AI, FastAPI, React + TypeScript + Vite, Docker. Versions are pinned at scaffold; lockfiles are authoritative once they exist.

## Prime directive

**Build the Melos MVP end-to-end, autonomously, until it works — then stop and hand it back.**

You may create spine/integration branches per milestone and smash-merge into the spine branch. A human merges spine → main. Definition of working: every item in [`docs/acceptance.md`](docs/acceptance.md) passes (automated + manual DAW check).

## Definition of done (self-verify — run before every PR is merge-ready)

```bash
# Exact commands will be finalized in the first CI/scaffold story.
# Expected shape (adjust to real scripts once they exist):
uv run ruff check .
uv run ty check          # or mypy / pyright equivalent once chosen
uv run pytest
# frontend:
npm run lint
npm run typecheck
npm run build
# PR review must come back clean
```

All must pass before you merge.

## Non-negotiables (you can't infer these)

1. **MIDI generation call outputs only compact JSON.** The dedicated MIDI generation AI call must never emit MIDI binary or any other file format. A deterministic converter turns validated Pydantic models into the `.mid` file.
2. **Pydantic V2 is the single source of truth.** Use Pydantic models instead of dataclasses everywhere. All structured LLM outputs are validated by Pydantic before use.
3. **Multi-track MIDI + embedded lyrics from day one.** Generated MIDI must contain multiple tracks and lyric meta events.
4. **Meta values are hard constraints.** When tempo, key, time signature (etc.) are supplied to the generation call, the model must obey them. Missing meta is resolved upstream before the generation call runs.
5. **Very open licenses only.** Dependencies must use MIT, Apache 2.0, or equivalent permissive licenses. No AGPL or strong copyleft.

## Code style (deviations only — defaults assumed)

- Prefer well-maintained open-license libraries behind interfaces (thin wrappers OK; heavy shoehorns not).
- Follow Clean Architecture + Uncle Bob / ArjanCodes principles (high cohesion, depend on abstractions, IO at the edges).
- Full checklist: [`docs/engineering/code-quality.md`](docs/engineering/code-quality.md).

## Always / Ask-first / Never

- **Always:** research the best-practice approach and verify library/API syntax against current official docs before writing code; run the self-verify commands before finishing a story; follow [`docs/engineering/workflow.md`](docs/engineering/workflow.md); update any affected docs in the **same** PR.
- **Ask-first → if you're autonomous, STOP-and-flag instead of asking:** schema changes that affect the public compact JSON contract, a new pattern/refactor beyond the task, or anything risky/ambiguous/large.
- **Never:** commit secrets or `.env`; force-push without asking; merge on red/absent CI or unresolved in-scope review comments; break `main`; add paid services; add speculative generality ("might need it later").

## Dependencies

**Add packages yourself when they clearly beat hand-rolling — no need to stop.** Reach for the stdlib or an already-installed package first; if you add one, vet it: widely used, actively maintained, a very open license (MIT/Apache-2.0/equivalent), and a fit for the stack. Prefer existing libraries over custom code; put most libraries behind interfaces.

## Build spec (read `docs/build-brief.md` first — this list is the reading order)

- [`docs/build-brief.md`](docs/build-brief.md) — What we're building, scope, non-negotiables
- [`docs/acceptance.md`](docs/acceptance.md) — Verifiable done criteria
- [`docs/tech-stack.md`](docs/tech-stack.md) — Locked stack and rationale
- [`docs/data-model.md`](docs/data-model.md) — Domain models and compact JSON contract
- [`docs/engineering/workflow.md`](docs/engineering/workflow.md) — How to plan and ship
- [`docs/engineering/code-quality.md`](docs/engineering/code-quality.md) — Code standards
