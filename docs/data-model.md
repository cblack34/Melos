# Data Model

Pydantic V2 models are the single source of truth for song structure. The LLM that performs MIDI content generation must emit data that validates against these models (or a compact equivalent that maps 1:1 onto them). No dataclasses for the same concepts.

## Core concepts (illustrative)

The exact field names and nesting are for the agent to finalize, but the shape must support:

- **Song** — tempo, key, time signature, metadata, list of tracks, optional sections
- **Track** — name, program/instrument hint, notes, control changes, pitch bends, lyrics
- **Note** — start time, duration (or end), pitch, velocity, optional lyric syllable
- **Section** — a named span of the arrangement (`verse 1`, `chorus`), exported as a MIDI marker
- **ControlChange / PitchBend** — timed expression data
- **Generation request** — prompt, optional constraints (key, tempo, structure, lyrics direction, instrumentation)

## Sections

Sections carry only a name and a start beat — a section ends where the next begins. Names are free text and repeats are expected (`chorus` appears several times), so sections are a **sequence, not a set**. They start at the top of the song and land on bar lines, because real arrangements change on the bar.

## Vocals

- `is_vocal` marks **a singable single-voice line** — words optional, but one note at a time, because that is what a voice can do. Enforced: vocal tracks are monophonic.
- Multi-part harmony means one vocal track per part. A polyphonic choir *chord* is an instrument track using a choir program, not a vocal track.
- Lyric syllables belong on vocal tracks. The lead is not a flag — it is simply the vocal track carrying the supplied lyrics.

## Text encoding

The SMF spec predates Unicode and names no encoding for meta text. Files are written **UTF-8** so lyrics, titles, and section names in any script survive; smart punctuation is still normalized to ASCII equivalents, which render more predictably across DAWs.

## Instrumentation

- Tracks map to **General MIDI** program numbers (percussion on MIDI channel 10, per GM convention) so any DAW or synth renders them sensibly.
- The generation request may carry instrument constraints: **must-include** and **must-exclude** lists. These are hard constraints (non-negotiable #4); beyond them the model chooses freely.
- GM sound-effect programs (helicopter, gunshot, telephone, …) are excluded by default — include one only when the prompt explicitly asks for it.

## Compact JSON contract

The MIDI generation AI call returns compact structured JSON (array-style notes are acceptable for token efficiency). That JSON is parsed and validated into the Pydantic models above. Only after successful validation does deterministic code write a Standard MIDI File.

**Rule:** the generation call never returns MIDI binary, base64 MIDI, or MusicXML. Other AI calls (lyrics, meta resolution, etc.) may have different output schemas; each schema is still a Pydantic model.

## Serialization boundary

- Inbound: HTTP request → Pydantic request models
- LLM output: raw JSON → Pydantic domain models (validation gate)
- Outbound: domain models → MIDI bytes via a dedicated exporter

The exporter is the only component that knows the MIDI binary format.
