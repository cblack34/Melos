# Deterministic guitar-strum feasibility

> **Status: automated evidence complete; human playback judgment pending.** This
> record belongs to the revisable tactical slice in
> [`../slices/01-representation-guitar-gate.md`](../slices/01-representation-guitar-gate.md)
> and is subordinate to the active strategic pack. The experimental types under
> `backend/tests/feasibility/` are evidence, not a production schema.

## Result

The fixture proves that a canonical chord occurrence and a reusable semantic
strum can expand deterministically into string-ordered performance events while
preserving exact score timing. Whole-fixture lookahead also lets a ringing
string cross a section marker and end exactly at its next physical-string
attack, avoiding ambiguous overlapping same-pitch MIDI notes.

This evidence supports the Melos-owned Pydantic direction recommended in
[`representation-decision.md`](representation-decision.md). It does not approve
the eventual production type or field layout.

## Fixture

- Tempo: 112 quarter-note BPM
- Meter: 4/4
- Form context: two verse bars followed by two chorus bars
- Chords: one bar each of G, C, Am, and D
- Reusable pattern: D/D-U-/U-D-U at beats `0`, `1`, `1.5`, `2.5`, `3`, `3.5`
- Expander recipe: `guitar-feasibility-v1`, seed `0`
- Per-string onset spacing: `0.0125` beats, about 6.70 ms at 112 BPM
- Velocity contour in attack order: `96, 91, 86, 81, 76, 71`
- Nominal ring time: one beat, shortened only by the next attack on the same
  physical string

Standard tuning uses string index 0 for low E and 5 for high E. Omitted strings
do not appear in the voicing.

| Chord | Fret shape, low to high | Sounding MIDI pitches, low to high |
| --- | --- | --- |
| G | `3 2 0 0 0 3` | `43 47 50 55 59 67` |
| C | `x 3 2 0 1 0` | `48 52 55 60 64` |
| Am | `x 0 2 2 1 0` | `45 52 57 60 64` |
| D | `x x 0 2 3 2` | `50 57 62 66` |

A down-strum visits those sounding strings low-to-high. An up-strum visits the
same selection in reverse. The velocity contour follows attack order, so it
also reverses physically with the strum direction.

## Canonical timing and performance realization

Every emitted event retains `canonical_chord_onset`; the first string starts on
that exact beat and later strings receive only the declared deterministic
offset. A notation adapter could therefore render the chord at the canonical
beat and ignore performance offsets, while the current MIDI adapter exports the
offset note attacks.

No random value is sampled. Identical validated fixture data and recipe produce
identical Pydantic event records, JSON, hashes, `Song` notes, and MIDI bytes.

## Section-boundary evidence

The C bar ends and the Am bar begins at beat 8. The last C up-strum begins at
beat 7.5. The expander sees the following Am occurrence and ends each C string
at its next attack when that is sooner than the one-beat nominal tail.

Pure tests prove:

- at least one C string rings beyond the beat-8 section marker;
- Am emits exactly one attack for each of its five sounding strings;
- no two events on the same physical string overlap;
- no accidental attack or gap is introduced at the marker; and
- for the shared high-E pitch, the old C note-off is emitted before the new Am
  note-on at the same MIDI tick.

This is boundary-aware realization from whole-fixture context, not independent
section expansion or stitching.

## Repeatability and size

Measured with Python 3.14.6 and the locked Pydantic 2.13.4:

| Evidence | Value |
| --- | ---: |
| Expanded performance events | 120 |
| Canonical experimental JSON | 1,555 bytes |
| Expanded performance-event JSON | 15,341 bytes |
| Expanded/canonical ratio | 9.87x |
| Event-data SHA-256 | `119b6c3a223c25b53207417f0a57b8f8e2ccd57520e838b466952a9be3006eeb` |
| MIDI bytes | 1,136 |
| MIDI SHA-256 | `9dec216b5260240e79ee222d73cf218c22f1d927393bbe515c20c02edfb760cc` |

The compact input still spells out each chord's selected strings because that
choice is canonical voicing intent. Its savings come from declaring the six-step
strum and recipe once rather than repeating 120 final attacks.

## Existing export seam

The optional fixture writer converts only `start`, `duration`, `pitch`, and
`velocity` into the existing `Note`, builds the smallest valid two-track `Song`,
and calls the unchanged MIDI exporter. Normal application code cannot select
the experiment, and normal tests write only to pytest's temporary directory.

## Automated verification

Focused verification:

```text
ruff check: passed
ruff format --check: passed
ty check: passed
pytest test_guitar_strum_feasibility.py + test_midi_export.py: 20 passed
```

The full repository verification suite and CI evidence are recorded on the
slice PR.

## Manual playback

Artifact: `/private/tmp/melos-guitar-feasibility.mid` (generated, not committed)

Environment:

- GarageBand 10.4.12
- MIDI program 25, General MIDI acoustic steel guitar
- fixture opened successfully through macOS on 2026-07-31

Human listening result: **pending**. Record whether the guitar is recognizably
strummed and any artificial timing, velocity, sustain, voicing, or patch
limitations before accepting the gate.
