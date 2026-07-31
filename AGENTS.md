# AGENTS.md — Melos

Instructions for the AI agents that plan and build this app. This is the source of truth for **how** to work; the active strategic pack listed below defines **what** must be true.

**Code, types, schemas, commands, and file layouts in strategic docs are illustrative guidance, not mandates.** Described behavior, architecture contracts, non-negotiables, and final acceptance are authoritative. Verify implementation details against current official documentation and the live repository.

## What this is

Melos is an AI-powered music creation web app. The shipped MVP turns a prompt into multi-track MIDI. Active work replaces the MIDI-shaped composition core with a whole-song semantic score that can later support editable notation, deterministic audio rendering, stems, and DAW exports without making any output format the source of truth.

Stack: Python 3.14, Pydantic V2, Pydantic AI, FastAPI, React + TypeScript + Vite, and Docker. Lockfiles are authoritative.

## Prime directive

**Cold-read the active pack and current repository, then propose a tactical implementation plan to the user before coding.** Preserve the complete strategic outcome, keep the shipped MVP green, and stop when final acceptance passes.

The pack's suggested implementation approach is informed but non-binding. Preserve hard causal dependencies, but revise advisory order when live code, tests, or new evidence justify a better plan. Discuss material replanning with the user.

Archived specs are historical evidence, not active instructions. Do not revive a direction from the archive or GitHub issue history when it conflicts with the active pack or [`docs/decisions/inactive-directions.md`](docs/decisions/inactive-directions.md).

## Definition of done

Run before every PR is integration-ready and before declaring the feature complete:

```bash
# backend — from backend/
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
# frontend — from frontend/
npm run lint
npm run typecheck
npm run test
npm run build
# PR review must come back clean
```

CI (`.github/workflows/ci.yml`) runs the same commands. All must pass before merge.

## Non-negotiables

1. **The canonical source is a Pydantic semantic score.** LLMs emit validated structured data, never MIDI, audio, MusicXML, or DAW files. MIDI-shaped note events are an export/performance model, not the composition source.
2. **Every composition attempt sees the whole song.** One whole-song composition operation produces the arrangement; validation-driven retries, when needed, retry the whole score and are logged. It may enrich the user's direction but may not countermand user constraints or directives. Do not generate independent sections and stitch them together.
3. **Code realizes declared musical intent deterministically.** Reusable patterns, chords, techniques, lyrics, and transitions expand through typed adapters. Keep the canonical score exact; seeded performance variation belongs at a rendering boundary. Instrumental audio is not composed by an audio LLM.
4. **Every run is an experiment.** Preserve the raw user request separately from injected instructions and log model/settings, prompt-component versions, raw responses, validated results, retries, and artifact hashes.
5. **Dependencies remain closed-source-compatible.** Prefer MIT, Apache-2.0, BSD, ISC, or clear equivalents. Review weak file-level copyleft before use and record required notices in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Reject strong/network copyleft.

## Strategic-to-tactical handoff

- The strategic lead and pack own scope, directives, architecture boundaries, research gates, risks, causal dependencies, suggested high-level order, and final acceptance.
- The implementation lead inspects live code, proposes execution-sized slices and actual order, discusses them with the user, and retains integration and replanning responsibility.
- Create tasks, issues, branches, PRs, or sub-agent assignments only after the plan is agreed and the relevant action is authorized.
- Give execution sub-agents bounded concrete assignments and use the least expensive capable model/effort. They surface surprises rather than changing scope or replanning the wider effort.

## Delivery governance

- A human is the only authority that merges to `main`.
- **Active topology:** one feature spine from `main`, with implementation-lead-defined leaf PRs into the spine. The implementation lead may squash-merge clean, green leaf PRs; the final spine PR to `main` requires human merge.
- Request GitHub Copilot review first with `gh pr edit PR-NUMBER --add-reviewer @copilot`; use `review-pr` if Copilot is unavailable, then a fresh bounded review sub-agent if needed. Self-review is not the independent gate.
- Follow the full CI, HEAD-matched review, reply/resolve, re-request-until-clean, and stop loop in [`docs/engineering/workflow.md`](docs/engineering/workflow.md).
- Only a PR to `main` may use `Closes #N`; leaf PRs reference issues without closing them.

## Working rules

- Prefer maintained libraries behind narrow interfaces when they beat hand-rolling. Research representation standards before inventing a Melos-specific language.
- Follow Clean Architecture: the domain imports no framework, file-format, DAW, plugin, or storage implementation.
- Update affected docs in the same PR and follow [`docs/engineering/workflow.md`](docs/engineering/workflow.md).
- Ask first—or stop and flag when autonomous—before changing active scope, final acceptance, a public contract or architecture boundary, adding a paid service, adopting a schema before its required research gate, or starting a broad refactor.
- Never commit secrets, force-push without approval, merge to `main`, integrate on red/absent CI, add speculative adapters, or implement deferred items from the inactive-directions record.

## Build spec reading order

1. [`docs/features/semantic-composition/brief.md`](docs/features/semantic-composition/brief.md) — active scope and invariants
2. [`docs/features/semantic-composition/design.md`](docs/features/semantic-composition/design.md) — architecture boundaries, research gates, risks, and advisory approach
3. [`docs/features/semantic-composition/acceptance.md`](docs/features/semantic-composition/acceptance.md) — stable final completion contract
4. [`docs/decisions/inactive-directions.md`](docs/decisions/inactive-directions.md) — superseded and deferred directions that must not leak into active work
5. [`docs/engineering/workflow.md`](docs/engineering/workflow.md) — strategic handoff and delivery governance
6. [`docs/engineering/code-quality.md`](docs/engineering/code-quality.md) — code standards

The completed MVP pack lives in [`docs/archive/mvp/`](docs/archive/mvp/README.md). Read it only when investigating shipped behavior or historical acceptance evidence.
