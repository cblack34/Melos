# Acceptance & How to Run

The build is done when the run commands work and every box below holds. Verify by hand in the running product except where a pure-logic test is noted.

## Run

Exact commands will be finalized during the first scaffold/CI story. Expected shape:

```bash
# Backend
uv sync
uv run ruff check .
uv run pytest
# (type checker once chosen)

# Frontend
npm ci
npm run lint
npm run typecheck
npm run build

# App (docker-compose or equivalent once present)
docker compose up --build
```

## MVP — Prompt to multi-track MIDI

- [ ] WHEN a user submits a valid prompt through the web UI, a multi-track MIDI file is generated and offered for download.
- [ ] WHEN the downloaded `.mid` file is opened in a DAW (REAPER or equivalent), it contains multiple tracks (not a single collapsed track).
- [ ] WHEN lyrics are present in the generation request, the MIDI contains lyric meta events that align with notes.
- [ ] WHEN tempo / key / time signature are supplied in the request, the generated MIDI respects those values.
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
