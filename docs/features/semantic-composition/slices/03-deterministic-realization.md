# Slice 03: Deterministic realization

> **Tactical and revisable.** This record is subordinate to the active semantic-composition brief, design, acceptance contract, inactive-directions record, and engineering workflow. Revise implementation details when repository evidence requires it; do not weaken strategic scope or acceptance.

GitHub story: #59

Parent tracker: #52

Base: `spine/semantic-composition`

Leaf: `feat/59-deterministic-realization`

## Outcome

Deterministically realize one representative canonical `SemanticScore` into the existing MIDI-shaped `Song`, then export it through the unchanged MIDI exporter. Keep the shipped generation path untouched.

This is the next causal slice because canonical identity, exact timing, pattern references, lyric assignments, and the guitar representation gate are now integrated. Whole-song model composition cannot responsibly depend on the semantic score until code can realize its declared intent without inference.

## In scope

- A narrow realization boundary from `SemanticScore` to `Song`.
- The approved G-C-Am-D down/down/up/up/down/up guitar fixture.
- Exact voicings and deterministic standard-tuning fret-to-pitch conversion.
- Canonical chord beats separated from per-string performance offsets.
- Deterministic velocities, note lengths, same-string retrigger handling, and cross-occurrence boundary behavior.
- Current explicit melodic and vocal families, including distributed primary lyrics and display/pronunciation separation.
- Exact rational timing until conversion to the performance model.
- Versioned local realization recipe identity and deterministic score, expanded-song, and MIDI evidence hashes.
- Minimal canonical amendments proven necessary for resolved key, semantic instrument identity, or explicit boundary composition.
- Pure tests, exported-MIDI parsing, full regression checks, and manual playback evidence.

## Out of scope

- Live Pydantic AI composition, prompt changes, retries, or generator selection.
- API, UI, SSE, download, or production configuration changes.
- Provenance persistence and runtime knowledge injection.
- Drums, bass, keys, target duration, or production resolution of #39.
- Audio or voice rendering, MusicXML/DAW exports, plugins, accounts, storage, or new representation dependencies.

## Research gates

- [x] Inventory the data needed to realize the representative fixture and identify whether it belongs in canonical intent, a versioned recipe, or the adapter configuration.
- [x] Select exact rational-to-performance conversion that remains deterministic and keeps ticks/floats out of the canonical score; non-integral 480-TPB timing is rejected rather than silently rounded.
- [x] Define boundary-use composition with executable collision cases rather than silently assuming additive or replacement behavior.
- [x] Confirm semantic instrument identity maps narrowly to the current `Song` model without making General MIDI canonical.
- [x] Stop for human input if evidence requires a material architecture-boundary change, a broad instrument taxonomy, a change to `Song` or an external API, or an ambiguous musical decision. The user approved the four contract decisions recorded below before production implementation.

## Approved contract decisions

The user approved these decisions on 2026-08-01:

- Schema version advances to `0.2.0` for the canonical key, instrument identity, and boundary-semantics amendments.
- A boundary use replaces ordinary guitar attacks for the referenced part within its interval. Notes already ringing may continue until their next realized retrigger; additive and transform modes remain deferred.
- Same-pitch guitar events are bounded by the next attack at that performance pitch regardless of physical string. Exact simultaneous duplicates collapse deterministically into one performance note while the canonical score preserves its physical-string intent.
- Global key and narrow semantic instrument identities are canonical. General MIDI programs and vocal flags remain versioned realization-recipe mappings outside the score.

## Architecture seams

- `melos.domain.semantic` remains canonical and imports no performance, MIDI, web, persistence, DAW, plugin, or audio implementation.
- Realization lives outside the canonical domain module and may depend inward on semantic intent and outward on the existing performance `Song` model.
- `Song` remains an export/performance model; `melos.midi.exporter` remains an unchanged output adapter.
- Recipe settings are versioned local code/data. Seeded variation, offsets, velocities, and quantization do not mutate canonical score time.

## Slice acceptance

- [x] Repeated realization with the same score, recipe version, seed, and configuration yields identical `Song` events and hashes.
- [x] The G-C-Am-D fixture yields expected pitches, chord changes, down/up string order, per-string offsets, and velocity contour.
- [x] Semantic chord onsets remain exact while performance offsets exist only in the realized model.
- [x] Same-string and same-performance-pitch notes do not overlap, including retriggers across an occurrence boundary; exact simultaneous duplicates coalesce deterministically.
- [x] Boundary material uses both adjacent occurrences and emits no accidental gap, duplicate attack, or clipped event.
- [x] Melodic and vocal phrases preserve exact semantic pitch/timing at the realization boundary.
- [x] Distributed primary lyrics reach the correct vocal notes; MIDI uses immutable display text, never pronunciation overrides.
- [x] Sections, tempo, key, meter, instruments, and vocal flags survive through `Song` and parsed MIDI evidence.
- [x] Existing production generation behavior is unchanged; no generation, API, UI, or exporter implementation changed.
- [ ] Backend/frontend verification, GitHub CI, manual playback evidence, and a clean HEAD-matched independent review pass.

## Manual evidence

Render the production semantic G-C-Am-D fixture with a recorded DAW/instrument. Listen specifically for the earlier feasibility limitation that upstrokes sounded like downstrokes. Record what distinguishes direction, any remaining limitation, and whether the fixture is recognizable as strummed guitar.

Pending human playback: `/private/tmp/melos-semantic-realization-gcad.mid`.

## Automated evidence

- Representative canonical JSON: 4,398 UTF-8 bytes.
- Generated schema: 14,434 compact JSON bytes.
- Semantic-score hash: `1216e2cc29c419c885f7851f81d25d52a7b4259bc00f6381e46a8ff539a3adfd`.
- Realization-recipe hash: `0c6dd7f30cd7d34f5864a51982b2c8a260eec6978639016ecbeb8e12da9b6cb9`.
- Expanded-song hash: `ae0e76a2d77554105bc87e803a517736857eeb68c0982a5663365f52b390be0e`.
- MIDI artifact: 1,218 bytes, SHA-256 `fcc9b7683badf40b759629f31cca404c05073c9c46b792ec08fe4ce23928ca29`.
- The representative result contains 120 guitar attacks and four tracks: guitar, melody, lead vocal, and answer vocal.
- Full local verification passes with 275 backend tests and 20 frontend tests, plus backend lint/format/type checks and frontend lint/typecheck/build. GitHub CI and independent review remain pending publication.

## Delivery

One leaf PR targets `spine/semantic-composition`. The implementation lead may squash-merge it only after every gate above is satisfied. It must not target or merge to `main`; the final spine PR remains human-controlled.
