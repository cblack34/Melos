# Slice 02 — Canonical semantic-score kernel

> **Status: active and revisable.** This tactical record is subordinate to
> [`../brief.md`](../brief.md), [`../design.md`](../design.md), and
> [`../acceptance.md`](../acceptance.md). The strategic pack wins on conflict.

GitHub tracking: [#57](https://github.com/cblack34/Melos/issues/57), under
[#52](https://github.com/cblack34/Melos/issues/52). Issues
[#39](https://github.com/cblack34/Melos/issues/39) and
[#27](https://github.com/cblack34/Melos/issues/27) remain downstream.

## Outcome

Add the first production, versioned Pydantic `SemanticScore` contract to the
framework-free domain layer without connecting it to the live composition or
MIDI path.

The canonical artifact is one whole-song root composed from discriminated,
instrument-specific internal models. Individual parts are not separate
canonical songs.

## Boundaries

In scope:

- an exact, JSON-safe canonical timing representation selected by executable
  evidence against the pinned dependencies;
- stable score, form-occurrence, pattern, part, and lyric-token identities;
- ordered form spans, reusable pattern references, and boundary relationships;
- separate user-authored directives and composer-added enhancements;
- guitar accompaniment semantics derived from the approved feasibility gate;
- explicit melodic/vocal phrases and immutable display-token assignments;
- deterministic validation, JSON/schema round trips, representative-size
  evidence, and a domain import-boundary test.

Out of scope:

- changing `GenerationRequest`, `SongGenerator`, `CompactSong`, `Song`, API,
  UI, prompts, downloads, or production configuration;
- connecting the score to Pydantic AI, expanders, MIDI, or persistence;
- fixing production lyric completeness or adding target duration;
- adding instrument families without an active fixture; and
- any deferred renderer, exporter, DAW, plugin, audio, account, or storage work.

## Research and implementation gates

- [x] Exact timing round-trips through JSON without binary floating-point
      ambiguity and remains independent of MIDI resolution.
- [x] The discriminated family models produce a usable JSON Schema with the
      pinned Pydantic version.
- [x] The domain imports no generation, MIDI, API, framework, persistence, or
      deferred implementation.
- [x] Common fixtures prove identity/reference validation, repeated pattern
      reuse, boundary relationships, and deterministic serialization.
- [x] Lyric fixtures prove ordered exactly-once primary coverage while
      non-primary copies remain legal and display text is immutable.
- [x] The full repository verification suite passes.
- Independent review, CI, and integration remain live GitHub state rather than
  self-attested checklist items in this document.

## Timing and schema decision

Canonical score time uses a normalized JSON-native rational value object with
an integer numerator and positive denominator. Python uses the explicit names
`numerator` and `denominator`; canonical JSON uses the compact aliases `n` and
`d`. Fractions must be reduced, zero has the single representation `0/1`,
denominators are not restricted to powers of two, and ordinary duration or
position models apply positivity rules in their own context. This supports
tuplets without adopting MIDI ticks or leaking binary floating-point
approximations into canonical data.

The pinned environment serializes Python `Fraction` values as strings and can
turn a JSON decimal such as `0.1` into its exact binary-float fraction. The
explicit value object instead round-trips as ordinary integer JSON fields with
`additionalProperties: false`. Pydantic also emits a discriminator and `oneOf`
mapping for the guitar, melodic, and vocal part models, and rejects fields from
the wrong family.

## Implementation evidence

- `SemanticScore` is a single immutable whole-song root with schema version
  `0.1.0`; the live `SongGenerator -> Song -> MIDI` path does not import it.
- The representative fixture has verse plus two distinct chorus occurrences,
  references one guitar-strum definition from both choruses, includes explicit
  melodic material, distributes primary lyrics across two vocal parts, and
  records a legal third-part harmony copy.
- User directives and composer enhancements occupy separate collections.
- Guitar uses retain chord symbols, explicit fret/string voicings, and selected
  sounding-string checks without storing MIDI pitches or performance offsets.
- Boundary uses must reference adjacent form occurrences, cross exactly their
  shared marker, remain within those occurrences, and contain complete pattern
  repetitions.
- The canonical fixture serializes to 4,194 UTF-8 JSON bytes and hashes to
  `3779234210e259397d403311980981997426977a147305eebcdf7730c3a113d3`.
  Its generated JSON Schema is 13,665 bytes and exposes the three-family
  discriminator map.
- Sixteen pure tests cover exact timing, schema discrimination, round-trip and
  hash stability, pattern reuse, form and reference failures, boundary rules,
  lyric coverage/order, non-primary assignments, pronunciation/display
  separation, immutability, and the forbidden-import boundary.

## Stop conditions

Stop for human input if the evidence requires multiple canonical song roots,
a new dependency, a change to an existing public/runtime contract, coupling the
domain to an adapter, implementing another instrument family speculatively, or
changing strategic scope or acceptance.
