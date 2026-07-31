# MVP Acceptance Record (Historical)

> **Status: completed and archived.** These checks remain useful as regression evidence, but they are not the active feature acceptance contract. See [`../../features/semantic-composition/acceptance.md`](../../features/semantic-composition/acceptance.md).

The build is done when the run commands work and every box below holds. Verify by hand in the running product except where a pure-logic test is noted.

## Setup & run

```bash
# Setup
(cd backend && uv sync)
(cd frontend && npm ci)

# App — UI at http://localhost:5173, API at http://localhost:8000
docker compose up --build
```

The self-verify commands (lint, typecheck, test, build) live in [`AGENTS.md`](../../../AGENTS.md) — that block remains canonical; all of it must pass.

## Verification record

Manual and artifact verification collected 2026-07-30 through 2026-07-31:

- Docker Compose launches a working app.
- A generated download opened in GarageBand with multiple separate instrument tracks.
- Supplied tempo, key, and time signature appeared correctly.
- The browser initiated the download without console errors.
- `night-drive-blues.mid` was parsed programmatically: it contains seven MIDI tracks, including a dedicated Lead Vocal track with 91 lyric meta events; all 91 events occur on vocal-note onsets.
- An include-instrument run completed through the UI with Piano, Acoustic Guitar, Electric Bass, Drums, Rock Organ, and Warm Pad required. `dust-on-the-dashboard.mid` was parsed programmatically: all six required parts are present on their exact GM programs (with drums on channel 10), alongside two Melos-selected parts. It is a nine-track type-1 MIDI at 120 BPM in E, 4/4; its 114 lyric events all occur on vocal-note onsets.

## MVP — Prompt to multi-track MIDI

- [x] WHEN a user submits a valid prompt through the web UI, a multi-track MIDI file is generated and offered for download.
- [x] WHEN the downloaded `.mid` file is opened in a DAW (REAPER or equivalent), it contains multiple tracks (not a single collapsed track). _Verified in GarageBand; the automated suite also parses track count, tempo, key, and lyric events._
- [x] WHEN lyrics are present in the generation request, the MIDI contains lyric meta events that align with notes. _Verified by parsing `night-drive-blues.mid`: 91/91 lyric events align with note onsets on the Lead Vocal track._
- [x] WHEN tempo / key / time signature are supplied in the request, the generated MIDI respects those values.
- [x] WHEN the request specifies instruments to include and/or exclude, every must-include instrument appears in the output and no excluded instrument does. _Verified end to end with six UI-selected instruments in `dust-on-the-dashboard.mid`._
- [x] _Pure test:_ Every track's program number is a valid General MIDI program, percussion sits on channel 10, and no GM sound-effect program appears unless the request asked for it.
- [x] _Pure test:_ Valid compact JSON that passes Pydantic validation round-trips through the MIDI exporter and produces a parseable Standard MIDI File.
- [x] _Pure test:_ The MIDI generation path rejects (or never produces) raw MIDI binary from the LLM; only Pydantic-validated structured data is accepted for export.
- [x] The FastAPI endpoint that serves the MIDI returns a correct `audio/midi` (or appropriate) content type and a usable filename.
- [x] The React frontend successfully triggers generation and initiates the download without console errors.

## Non-negotiable enforcement

- [x] No code path allows the MIDI-generation LLM call to write a `.mid` file directly.
- [x] All structured LLM outputs are validated by Pydantic V2 models before side effects occur.
- [x] Dependency licenses are closed-source-compatible; reviewed weak, file-level copyleft is documented in [`THIRD_PARTY_NOTICES.md`](../../../THIRD_PARTY_NOTICES.md), and no strong/network copyleft is introduced.

## Not in this build

Audio rendering, VST hosting, user accounts, stem export UI, reference-audio analysis, and MusicXML export are future work. The agent may design seams for them but must not implement them as part of the MVP acceptance criteria.
