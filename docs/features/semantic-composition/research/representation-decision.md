# Semantic representation research and recommendation

> **Status: direction approved by the human owner on 2026-07-31; production
> schema remains a later gate.** This evidence record belongs
> to the revisable tactical slice in
> [`../slices/01-representation-guitar-gate.md`](../slices/01-representation-guitar-gate.md)
> and is subordinate to the active strategic pack. It approves no production
> schema by itself.

Research checked on 2026-07-31 against current official documentation and the
live Melos dependency locks. The decision is intentionally about the canonical
composition boundary; a useful export format is not automatically a suitable
source model.

## Recommendation

Use the existing Pydantic dependency to define a small, versioned, Melos-owned
semantic score, then realize it with Melos-owned deterministic typed expanders.
Retain `Song` as the note-level performance/export model and `mido` as the MIDI
adapter. Add no representation dependency now.

Adapt concepts rather than code:

- separate canonical notation/intent from performance realization;
- identify form occurrences, patterns, lyric tokens, and assignments with
  stable references;
- declare reusable named patterns once and apply explicit, ordered
  transformations at occurrences;
- keep explicit notes for melody or solo material that is not usefully
  compressible;
- model boundary overlays in whole-song score time rather than clipping them to
  isolated sections; and
- keep immutable lyric display tokens separate from syllabification, holds,
  pronunciation, and primary/non-primary performance assignments.

The guitar feasibility result must support this direction before the gate is
accepted. Production type and field design remain a later, separately approved
public-contract decision.

## Candidate decision matrix

| Candidate | Current evidence and exact license | Fit against Melos | Decision |
| --- | --- | --- | --- |
| [MusicXML 4.0](https://www.w3.org/2021/06/musicxml40/) | Final Community Group Report, 1 June 2021, published under the W3C Community Final Specification Agreement. It is a notation-interchange format supported by more than 250 applications. | Rich notation, tablature, chords, lyrics, ties, and repeats, but verbose XML and notation occurrences do not supply Melos's reusable typed performance recipes, experiment provenance, or immutable lyric/performance split. | Later export format; adapt the score-versus-performance distinction. |
| [MNX](https://w3c.github.io/mnx/docs/) | MNX 1.0 remains a work-in-progress without a stable implementation standard. The specification is published under the W3C Community Contributor License Agreement; the source repository exposes no SPDX software license. | Its JSON notation semantics and stable IDs are useful signals, but its instability and notation focus make it unsafe as Melos's source contract. | Observe and consider for later export; adapt identity concepts only. Do not copy repository code while its software license is unspecified. |
| [DAWproject 1.0](https://github.com/bitwig/dawproject) | The project declares 1.0 stable and uses the [MIT License](https://github.com/bitwig/dawproject/blob/main/LICENSE). It stores XML in a ZIP container and deliberately models DAW session interchange. | Strong for later tracks, clips, notes, automation, plug-in state, and higher-level DAW exchange. It materializes production/performance state rather than whole-song composition intent. | Later export format; no dependency in the canonical domain. |
| [MIDI 1.0 and MIDI 2.0](https://midi.org/midi-2-0) | MIDI 2.0 extends rather than replaces MIDI 1.0. Current core concepts include Universal MIDI Packets, MIDI-CI, profiles, per-note control, and the MIDI Clip File. Specification terms are distinct from software licenses. Melos currently locks `mido` 1.3.3 under MIT. | Correct for final note attacks, timing, controllers, and delivery, but it loses named patterns, semantic chords, form intent, and lyric identity. JSON-shaped MIDI events are the live token-cost problem. | Performance/export model only; retain `mido` behind the existing adapter. |
| [Alda](https://alda.io/) | Actively maintained textual composition language; implementation is [EPL-2.0](https://github.com/alda-lang/alda/blob/master/LICENSE), a weak-copyleft license requiring separate review and notices if adopted. | Concise instruments, sequences, chords, and variables are useful product evidence, but Alda has no Python domain API and remains playback-oriented rather than a typed provenance and lyric contract. | Adapt concise-reference concepts only; no dependency or code derivation. |
| [ABC 2.1](https://abcnotation.com/wiki/abc%3Astandard%3Av2.1) and [2.2 draft](https://abcnotation.com/wiki/abc%3Astandard%3Av2.2) | Version 2.1 is the current stable standard; 2.2 is explicitly a draft. No explicit software-reuse license was located for the specification. | Compact traditional note transcription with parts, repeats, decorations, and lyrics, but multi-voice evolution remains unsettled and the format lacks typed guitar realization, boundary overlays, provenance, and pronunciation identity. | Do not depend on it or use it as canonical; adapt only general repeat/part concepts. |
| [LilyPond 2.26.0](https://lilypond.org/) | Current stable release on the research date. Software uses GNU GPL-3.0 and documentation uses the GNU Free Documentation License. | Mature engraving, variables, repeats, chords, tablature, and lyrics, but notation-first semantics do not provide the required composition/provenance model and GPL code is incompatible with closed-source Melos. | Reject as a dependency. A later independently authored exporter may target its text format after a separate gate. |
| [Tidal patterns](https://tidalcycles.org/docs/reference/patterns/) and [long-form composition](https://tidalcycles.org/docs/reference/composition/) | Current documentation demonstrates named patterns, patterns of patterns, transformations, and scheduled spans. Tidal source is GPL-3.0; documentation is CC-BY-SA. | Excellent conceptual evidence for named temporal patterns and explicit transformation order. Its live cyclic/audio model does not supply notation, chord/voicing intent, lyric identity, or one-shot whole-song provenance. | Adapt only the high-level idea of named patterns and ordered transformations. Do not port algorithms or types. |
| [Strudel](https://codeberg.org/uzu/strudel) | Current source moved from an archived GitHub mirror to Codeberg and uses AGPL-3.0. | Demonstrates browser pattern composition but inherits the same semantic gaps as Tidal; its network-copyleft license is explicitly disallowed. | Reject dependency and code derivation. |
| [music21 10.5.0](https://pypi.org/project/music21/10.5.0/) | Current PyPI release supports Python 3.11+ and declares BSD-3-Clause. Its own documentation warns that corpus and external assets have separate licenses and offers a no-corpus variant for strict BSD use. | Broad Python notation/analysis object model and MusicXML/MIDI support, but it is a large dependency graph and not a compact Pydantic pattern/provenance contract. | Do not add now. Re-evaluate behind a later notation/analysis adapter with corpus excluded. |
| [Partitura 1.9.0](https://pypi.org/project/partitura/1.9.0/) | Maintained Python package under Apache-2.0 with MusicXML/MIDI score and performance models. Its declared dependencies include NumPy, SciPy, lxml, Lark, xmlschema, and mido. | The strongest later Python import/export candidate, but still notation/performance-first and much broader than the canonical-domain need. Current classifiers do not claim Python 3.14 even though its `>=3.10` metadata permits installation. | No dependency now; re-evaluate for a later MusicXML adapter after compatibility and transitive-license checks. |
| [Symusic 0.6.0](https://pypi.org/project/symusic/0.6.0/) | Current alpha release under MIT with Python 3.14 wheels. | Fast Python/C++ symbolic-performance containers for notes, tempo, meters, pedals, bends, and controllers, but no reusable semantic pattern, form, guitar, lyric, or provenance model. It duplicates the current performance boundary rather than solving the source model. | Reject as a new canonical dependency. |
| [pretty_midi 0.2.11](https://pypi.org/project/pretty-midi/0.2.11/) | MIT-licensed MIDI utility centered on seconds-based note containers. | Convenient performance manipulation, but redundant with `mido` and the existing exporter and offers no semantic ownership. | Reject new dependency. |

## Common-fixture comparison

| Fixture | Required semantic evidence | Result |
| --- | --- | --- |
| Reusable D/D/U/U/D/U guitar pattern over G–C–Am–D | One typed pattern reference, canonical chord/voicing intent, selected strings, articulation, and deterministic performance offsets. | A Melos Pydantic model can retain the intent once and expand it. Notation formats describe the written or expanded outcome; MIDI and DAW formats carry only performance output. |
| Explicit melody or solo notes | Exact pitch, onset, duration, dynamics, articulation, and optional motif identity. | Keep explicit typed notes. Compression is not a goal where it destroys expressive information. |
| Repeated chorus references | Stable pattern/form IDs plus occurrence-local bounded variation or transition overlays. | Named references are smaller and less ambiguous than duplicated note payloads or notation repeat instructions whose playback interpretation varies. |
| Boundary-crossing fill, pickup, anticipation, or tail | Whole-song score time, adjacent occurrence identity, legal span, and deterministic composition order. | Model an ID-bearing overlay with adjacent context. A section label must not clip its events. |
| Held vowel and pronunciation override | Immutable display token ID, one primary assignment, syllables/hold, and separate pronunciation data. | A custom typed lyric layer is required. Notation lyric fields and MIDI meta events do not portably preserve this identity split. |

## Representation-size method

The feasibility harness records canonical compact JSON bytes for one declared
guitar pattern plus four chord applications and compares that with JSON for the
fully expanded note events. The same measurement must be deterministic and
reported in [`guitar-strum-feasibility.md`](guitar-strum-feasibility.md).

No external source can provide Melos-specific token counts before a concrete
schema exists. Byte size is therefore the reproducible gate metric in this
slice; provider-token measurements belong in the later quality harness once the
production schema and prompts exist.

## License conclusion

No new dependency is justified, so this slice changes neither lockfile nor
[`THIRD_PARTY_NOTICES.md`](../../../../THIRD_PARTY_NOTICES.md). Pydantic and
`mido` are already locked and reviewed. Strong/network-copyleft projects are
reference material only; no source, types, or algorithms are copied or derived.

## Human decision

The human owner approved the Melos-owned Pydantic semantic-score direction and
the decision to add no representation dependency on 2026-07-31, after reviewing
the guitar feasibility result.

This approval does not decide whether the production score will use one
aggregate model with instrument-specific intent types and adapters, multiple
instrument-focused internal models, or another composition that preserves the
same architecture boundary. That type and field design belongs to a later
production-schema slice. This decision authorizes planning that slice; it does
not authorize a public-contract change here.
