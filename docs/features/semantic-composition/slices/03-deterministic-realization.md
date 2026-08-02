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
- [x] Backend/frontend verification, GitHub CI, manual playback evidence, and a clean HEAD-matched independent review pass.

## Manual evidence

Render the production semantic G-C-Am-D fixture with a recorded DAW/instrument. Listen specifically for the earlier feasibility limitation that upstrokes sounded like downstrokes. Record what distinguishes direction, any remaining limitation, and whether the fixture is recognizable as strummed guitar.

Pending human playback: `/private/tmp/melos-semantic-realization-gcad.mid`.

First playback finding: the six-tick sweep and shallow velocity contour still sounded like uniform downstrokes, and every pattern hit carried effectively the same weight. In response, the recipe doubles the string interval to twelve ticks, increases first-contact emphasis, makes upstrokes lighter, and the canonical fixture declares primary emphasis on beats 2 and 4 with secondary emphasis on beat 1. A regenerated playback check is required.

Second playback finding: at 60 BPM the revised string attacks and direction are clearly audible, confirming that this is appropriately the performance MIDI rather than canonical score timing. The emphasis strength still needs a human-directed adjustment. DAW inspection also exposed notes from one physical string ringing through that string's next fretted attack. The realization diagnostic reproduced 18 same-string overlaps; attacks are now bounded by both the next use of their physical string and the next use of their MIDI pitch while different strings within the chord remain free to ring together. Another regenerated playback check is required after the emphasis adjustment.

SoundBench reference evidence now grounds the next adjustment. Strum Lab `0.1.0` at SoundBench commit `0fa6d02` analyzed 40 intended-even E-major quarter-note downstrokes at 60 BPM using `examples/e-major-quarter-down.yaml`. The local input SHA-256 is `ac5f94ef74928fe7e4b3284d209c5283971bc4801e76fc6b07e0ad3a46921781`; the retained `report.json` SHA-256 is `565109f84ac4b4636526e5296f2c8347bc9e64611cba0110d42613a594e17540`. Median RMS by beat was -13.64, -15.24, -13.40, and -14.00 dBFS. Because the performer intended equal weight, that measured 1-and-3 tendency is observed realization rather than declared accent intent: `emphasis: none` must continue to produce equal nominal MIDI velocities across beats. The chord-level frequency proxies reported roughly 0.49-0.55 low-band energy and 0.17-0.20 high-band energy; they are not per-string loudness or a standardized MIDI-velocity mapping.

The evidence supports a conservative steeper low-to-high downstroke contour, not a literal conversion of band energy into velocity. The recipe now separates direction-specific contours: downstrokes use `(108, 94, 82, 68, 60, 54)`, while the previously reviewed upstroke contour remains unchanged until an upstroke recording exists. This avoids projecting downstroke evidence onto the opposite physical gesture. A regenerated playback check is required before accepting the adjustment.

Third playback finding and slice acceptance: after the SoundBench-informed downstroke adjustment, the listener reported that the MIDI sounds good enough to move forward. Better samples would improve realism, but the available work Mac does not have the listener's preferred production instruments; a later comparison on the personal Windows production environment may refine rendering without blocking this deterministic-realization slice. The current General MIDI sample limitation is accepted as an exporter/playback-environment limitation rather than a semantic-score or realization defect.

## Automated evidence

- Representative canonical JSON: 4,517 UTF-8 bytes.
- Generated schema: 14,529 compact JSON bytes.
- Semantic-score hash: `79f640f083755e3381986ce9349d8ffa86c98b1d5f2a076b47cf508465a25342`.
- Realization-recipe hash: `89b96f3b07a407f93c71efc96e5cfd5607063006071f149d4b96f961cd27ad35`.
- Expanded-song hash: `44c68d203990f380a3c703c14a4b29b187b324947e25b0d94f75153ec2391449`.
- Accepted playback MIDI artifact: 1,235 bytes, SHA-256 `fcc51fd8ba5d6cc3a74b6673d360d4ee87868085d45b35bacf61560af3320d2c`.
- The representative result contains 120 guitar attacks and four tracks: guitar, melody, lead vocal, and answer vocal.
- Full local verification initially passed with 275 backend tests and 20 frontend tests. Copilot identified silent truncation when an articulation multiplier produced a fractional tick; realization now rejects that case and a focused regression pins it. Its HEAD-matched re-review then found that boundary replacement still had a default even though the operation must be explicit; the field is now required and omission is rejected. A suppressed wording comment also correctly noted that the shared key-signature set should not claim format independence, so its module description now names the narrower contract without changing the type. The final complete gate passes with 279 backend tests and 20 frontend tests, including the direction-specific contour, equal-intent, and leading lyric-token ordering regressions.

## Delivery

One leaf PR targets `spine/semantic-composition`. The implementation lead may squash-merge it only after every gate above is satisfied. It must not target or merge to `main`; the final spine PR remains human-controlled.
