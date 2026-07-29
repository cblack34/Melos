# Acceptance & How to Run

The build is done when the run commands work and every box below holds. Verify by hand in the running product except where a pure-logic test is noted.

## Setup & run

```bash
# Setup
(cd backend && uv sync)
(cd frontend && npm ci)

# App — UI at http://localhost:5173, API at http://localhost:8000
docker compose up --build
```

The self-verify commands (lint, typecheck, test, build) live in [`AGENTS.md`](../AGENTS.md) — that block is canonical; all of it must pass.

## MVP — Prompt to multi-track MIDI

- [ ] WHEN a user submits a valid prompt through the web UI, a multi-track MIDI file is generated and offered for download.
- [ ] WHEN the downloaded `.mid` file is opened in a DAW (REAPER or equivalent), it contains multiple tracks (not a single collapsed track). _The agent verifies MIDI structure programmatically (parse the file — track count, tempo, key, lyric events); the open-in-DAW check itself is performed by a human at handback._
- [ ] WHEN lyrics are present in the generation request, the MIDI contains lyric meta events that align with notes.
- [ ] WHEN tempo / key / time signature are supplied in the request, the generated MIDI respects those values.
- [ ] WHEN the request specifies instruments to include and/or exclude, every must-include instrument appears in the output and no excluded instrument does.
- [ ] _Pure test:_ Every track's program number is a valid General MIDI program, percussion sits on channel 10, and no GM sound-effect program appears unless the request asked for it.
- [ ] _Pure test:_ Valid compact JSON that passes Pydantic validation round-trips through the MIDI exporter and produces a parseable Standard MIDI File.
- [ ] _Pure test:_ The MIDI generation path rejects (or never produces) raw MIDI binary from the LLM; only Pydantic-validated structured data is accepted for export.
- [ ] The FastAPI endpoint that serves the MIDI returns a correct `audio/midi` (or appropriate) content type and a usable filename.
- [ ] The React frontend successfully triggers generation and initiates the download without console errors.

## Non-negotiable enforcement

- [ ] No code path allows the MIDI-generation LLM call to write a `.mid` file directly.
- [ ] All structured LLM outputs are validated by Pydantic V2 models before side effects occur.
- [ ] Dependency licenses are permissive (MIT / Apache-2.0 / equivalent); no AGPL-style packages are introduced.

## Not in this build

Audio rendering, VST hosting, user accounts, stem export UI, reference-audio analysis, and MusicXML export are future work. The agent may design seams for them but must not implement them as part of the MVP acceptance criteria.
