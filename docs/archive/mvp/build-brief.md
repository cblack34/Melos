# MVP Build Brief (Historical)

> **Status: completed and archived.** This file records the original prompt-to-MIDI MVP contract. It is evidence and context, not an active instruction set. Active development is governed by [`../../features/semantic-composition/brief.md`](../../features/semantic-composition/brief.md).

_Read this first, then the rest of the docs in the order listed in `AGENTS.md`. The goal: an agent reads `docs/` and builds the app unattended._

_Code, types, and file layouts throughout these docs are **illustrative** — a guide to intent, not a required implementation. The acceptance criteria ([`acceptance.md`](acceptance.md)) and the described behavior are the contract; you choose the how, following current best practice._

## What we're building

Melos is an AI-powered music generation web application. Users submit creative prompts (and optional constraints such as key, tempo, or lyrics direction) and receive a complete multi-track MIDI file that can be loaded directly into a DAW.

The system is designed for expansion: lyric generation, richer controls, later audio rendering, and single-instrument generation from reference material are expected future capabilities. Architecture must keep generation (structured data) cleanly separated from export/rendering so those capabilities can be added without rewriting the core.

Primary users: musicians and producers who want fast, editable song sketches rather than final mixed audio (at least for the MVP).

## In scope (MVP)

- User can submit a text prompt (and optional meta constraints) via the web UI.
- The system produces a multi-track Standard MIDI File (`.mid`) containing at least a lead/melody track and supporting instrumental tracks.
- Lyrics are embedded in the MIDI as lyric meta events when lyrics are present.
- The generated MIDI opens cleanly in a DAW (REAPER or equivalent) with correct tempo, key signature, and track separation.
- Backend exposes a FastAPI endpoint that returns the MIDI file (or a download link).
- Frontend (React + TypeScript + Vite) provides a simple prompt form and download action.
- All structured AI outputs are validated with Pydantic V2 models before any file is written.
- The dedicated MIDI generation AI call outputs only compact JSON; a deterministic converter produces the binary MIDI.

## Planned features (agent decides slices / order)

These are desired capabilities. The agent is free to define intermediate milestones and vertical slices. Do not treat them as required for the MVP acceptance criteria.

- Lyric generation assistance
- Stronger control over song structure (sections, chord progressions)
- Single-instrument MIDI generation guided by a reference MIDI
- Export of individual stems or per-track MIDI
- Later: audio rendering via headless VST hosts
- User accounts / project history (far future)

## Non-negotiables

1. **MIDI generation call outputs only compact JSON**  
   The AI call responsible for producing musical content must never emit MIDI binary, base64 MIDI, or any other file format. It emits structured data that is validated by Pydantic V2 and then converted by deterministic code. This keeps generation token-efficient, testable, and free of binary-format bugs.

2. **Pydantic V2 is the single source of truth**  
   Domain models and all structured LLM outputs live as Pydantic models. Do not introduce dataclasses or ad-hoc dict schemas for the same concepts. This gives one clean interface for validation, serialization, and documentation throughout the app.

3. **Multi-track MIDI + embedded lyrics from the start**  
   Even the first working version must produce a multi-track file (not a single mixed track) and must carry lyrics as MIDI lyric meta events when lyrics exist. Downstream tools and DAWs expect this shape.

4. **Provided meta values are hard constraints**  
   When tempo, key, time signature, instrumentation, or similar values are supplied to the generation call, the model must obey them. Missing values are resolved by upstream steps or earlier AI/tool calls so the generation call always receives a complete package.

5. **Dependency license policy**  
   Keep Melos closed-source-compatible. Prefer permissive licenses (MIT, Apache 2.0, BSD, ISC, and clear equivalents). Weak, file-level copyleft such as MPL-2.0 is allowed after review confirms that disclosure obligations remain limited to the covered dependency files; record notices and corresponding source locations in [`THIRD_PARTY_NOTICES.md`](../../../THIRD_PARTY_NOTICES.md). No AGPL, GPL, or other strong/network copyleft that could require Melos source disclosure.

## Definition of done

- All self-verify commands (typecheck, lint, tests, build) pass.
- PR review comes back clean.
- Every acceptance item in [`acceptance.md`](acceptance.md) is satisfied, including the manual check that the downloaded MIDI opens correctly in a DAW with the expected tracks and tempo.
