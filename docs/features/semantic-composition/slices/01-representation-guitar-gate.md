# Slice 01 — Representation and guitar feasibility gate

> **Status: active and revisable.** This tactical slice is subordinate to
> [`../brief.md`](../brief.md), [`../design.md`](../design.md), and
> [`../acceptance.md`](../acceptance.md). If this plan conflicts with the active
> strategic pack, the strategic pack wins.

## Outcome

Close the representation-research and deterministic guitar-strum feasibility
gates together, without adopting a production semantic schema or changing the
shipped generation path.

The slice will produce:

- a source- and license-backed representation decision record;
- an isolated deterministic guitar feasibility harness and pure tests;
- serialized-size and repeatability evidence against the shared fixtures;
- a GarageBand playback record for the G–C–Am–D strum fixture; and
- a joint recommendation for human approval before production schema adoption.

GitHub tracking: [#53](https://github.com/cblack34/Melos/issues/53) and
[#54](https://github.com/cblack34/Melos/issues/54), under
[#52](https://github.com/cblack34/Melos/issues/52).

## Boundaries

In scope:

- current official-source research across the candidate space required by the
  strategic design;
- exact license, maintenance, stability, Python-fit, round-trip, semantic-fit,
  and representation-size evidence;
- the shared guitar, repeated-pattern, explicit-note, boundary-event, and lyric
  performance fixtures;
- an experimental guitar model and expander isolated from production code;
- deterministic event/hash tests and MIDI export through the existing adapter;
- correction of stale comments that still prescribe independent section
  generation, without changing runtime behavior.

Out of scope:

- a production `SemanticScore` or any public contract change;
- changes to `GenerationRequest`, `SongGenerator`, `CompactSong`, API/UI, or
  production prompts;
- target duration, distributed lyric validation, provenance storage, or legacy
  generator retirement; and
- any deferred renderer, exporter, plugin, cloud, account, or editing work.

## Gate checks

- [x] Candidate matrix uses current official sources and exact licenses.
- [x] Every candidate is classified as dependency, concepts to adapt, later
      export format, or reject.
- [x] The common fixtures are compared on semantic fit and serialized size.
- [x] The guitar fixture proves voicings, sounding strings, direction, chord
      changes, deterministic offsets, velocity contour, and canonical timing.
- [x] A boundary-context fixture has no accidental gap, duplicate, or clipping.
- [x] Identical inputs produce identical event data and hashes.
- [x] GarageBand playback evidence records the instrument and limitations.
- [x] Research and feasibility evidence support one joint recommendation.
- [ ] The full repository verification suite and independent PR review pass.
- [x] Human review approves the recommendation before production adoption.

## Stop conditions

Stop and return to the user if the evidence requires a public-contract or
architecture-boundary change, a paid service, an incompatible or ambiguous
license, a new dependency before its license gate closes, or if the research
and guitar evidence do not support the same production direction.
