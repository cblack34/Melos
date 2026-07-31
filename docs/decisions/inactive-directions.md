# Inactive Directions

These decisions prevent historical plans and attractive future ideas from leaking into the active build. They may be reconsidered only when the stated trigger occurs and a new decision updates the active feature pack.

## Superseded

### Independent section generation and stitching

Do not make one generative call per verse, chorus, or bridge and stitch the results. Token savings do not compensate for weakened continuity, repeated-section monotony, or missing pickup notes, fills, and transitions at boundaries.

**Active alternative:** one composition call sees the entire ordered form and emits reusable semantic patterns and references. Deterministic expansion may operate in smaller units, but it receives whole-song context.

**Reconsider only if:** semantic compression plus prompt/schema tuning still cannot produce complete validated songs within supported model limits, and a spike demonstrates boundary continuity and lyric completeness better than the whole-song path.

### Expanded MIDI note JSON as the composition source

The shipped MVP's `Song` is a valid performance/export model, but it is not the target canonical representation. Repeating every note for every occurrence wastes tokens and obscures chords, voicings, patterns, techniques, and musical relationships.

**Active alternative:** a Pydantic semantic score declares intent once and references it. Deterministic adapters expand it to exact note events. Explicit note sequences remain appropriate for melodies, solos, and other irreducibly note-level material.

### MIDI, MusicXML, audio, or a DAW project as the canonical file

No interchange or delivery format is the source of truth. MIDI lacks notation and production semantics; notation formats do not represent the complete production; DAW projects are host-specific; audio is not editable enough.

**Active alternative:** export each format from the semantic score and its versioned performance/production recipes.

### Independent random humanization in the canonical score

Do not perturb canonical timing or notation to make playback feel human. That damages reproducibility and future sheet-music output.

**Active alternative:** encode intentional techniques such as strum direction and articulations semantically. A rendering adapter may later apply seeded, recorded performance variation without changing the score.

### Generative instrumental audio

Do not use a music-audio LLM to invent instrumental stems or masters. It would weaken editability and fidelity to the score.

**Active alternative:** deterministic instruments, plugins, and renderers perform the score. A future score-conditioned vocal model is the sole planned exception.

## Deferred, not rejected

The following are out of scope for the active semantic-composition pack:

- REAPER, VST3, Kontakt/Native Instruments, Studio One, and other audio-renderer adapters
- Lazy user-selected exports and presets for dry/processed stems, effects returns, masters, portable consolidated DAW projects, and live-plugin DAW projects
- MusicXML, MNX, and DAWproject exporters
- Voice-model selection and sung-audio rendering; the semantic lyric model must only preserve the future seam
- User accounts and storage policy: durable project/selected-LLM source versus a separate weighted/time-limited render cache; candidate deterministic retention is 30–90 days and unselected generative variants 90–365 days by tier
- User plugin inventories and per-role plugin/preset preferences (for example, hall reverb → exact plugin/preset), with versioned vendor subscription catalogs and fallback mappings
- Public SaaS licensing decisions for DAWs, plugins, sample libraries, and render farms; personal-only rendering may be prototyped behind an interface, but commercial terms are a public-release gate
- SoundGrid as a possible real-time batch effects renderer; channel count is not assumed to equal independent job concurrency
- Chat-based score editing, visual note/chord editing, branching, and undo UI

These items require separate feature packs after the semantic score is proven. Implement no empty adapter or speculative schema solely for them; preserve only the explicit seams required by the active design.
