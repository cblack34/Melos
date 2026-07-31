# Design

_Descriptive target, not a mandated class/file layout. Shipped code wins when it differs; update this document in the same PR._

## Current seam and target flow

The current `GenerationRequest -> SongGenerator -> Song -> MIDI exporter` flow remains externally usable while the middle changes:

```text
GenerationRequest
  -> resolve hard meta and parse user-authored lyrics/directives
  -> one whole-song composition operation
  -> validate SemanticScore
  -> deterministic instrument expanders
  -> existing MIDI-shaped Song
  -> existing MIDI exporter
```

The working MIDI exporter remains the delivery adapter for this feature. During migration, the legacy direct-note generator may exist only as a controlled comparison/fallback path. At final acceptance the semantic path is the sole production composition path and obsolete prompt/validation branches are removed.

## Research signals and representation gate

Research supports the direction without dictating Melos's implementation:

- [MeloForm](https://arxiv.org/abs/2208.14345) combines explicit musical-form control with learned refinement.
- [MuseCoco](https://arxiv.org/abs/2306.00110) uses musical attributes as the bridge between text and symbolic music.
- [Whole-Song Hierarchical Generation](https://arxiv.org/abs/2405.09901) conditions lower-level notes/chords/patterns on higher-level form, phrase, and cadence.

These papers support explicit hierarchy, semantic conditioning, and separation of declared form from note realization. They do **not** establish that Melos needs their model architectures, training pipelines, or multiple creative stages. Melos retains one whole-song composition operation; any validation-driven model retry receives the complete score context.

No target schema may be approved until existing representations are compared against the acceptance fixtures. At minimum inspect current official specifications/documentation for:

- MusicXML 4.0 and the developing MNX notation model
- DAWproject 1.0 session interchange
- Standard MIDI/MIDI 2.0 concepts relevant to performance export
- concise score languages such as Alda, ABC, or LilyPond
- pattern systems such as Tidal/Strudel
- maintained Python libraries that expose compatible domain models or deterministic expansion

The decision must distinguish **reuse as a dependency**, **adapt concepts**, and **use only as an export format**. Record maintenance, format stability, round-trip behavior, token cost, Python fit, and closed-source license compatibility. Studying a copyleft project is allowed; importing or deriving covered code is not.

Starting references:

- [MusicXML 4.0](https://www.w3.org/2021/06/musicxml40/) is a notation interchange candidate, not assumed to be the composition source.
- [MNX](https://w3c.github.io/mnx/docs/) is under active development and must not be treated as stable without verification.
- [DAWproject 1.0](https://github.com/bitwig/dawproject) is a stable session-interchange candidate for a later exporter, not a composition language.
- [Alda](https://alda.io/) demonstrates concise textual scoring.
- [Tidal pattern documentation](https://tidalcycles.org/docs/reference/patterns/) and its [long-form composition operations](https://tidalcycles.org/docs/reference/composition/) demonstrate named patterns and pattern reuse.

## Semantic layers

The schema should express these concepts without embedding exporter or DAW details:

- **Provenance identity:** schema version and stable IDs needed to reference form events, pattern definitions, lyric tokens, and part assignments.
- **User intent:** raw hard constraints and directives remain distinguishable from compatible composer enhancements.
- **Global form:** an ordered sequence of section occurrences with bar spans, energy/density intent, and transition relationships. Repeated names are occurrences, not deduplicated sections.
- **Harmony:** chord symbols/functions, harmonic rhythm, and explicit voicing constraints where the user or technique requires them.
- **Pattern registry:** named typed definitions declared once, with references and bounded transformations/variations.
- **Parts:** instrument roles and timelines that combine pattern references, chord spans, motifs/notes, articulations, dynamics, and transition intent.
- **Lyrics:** immutable display tokens plus primary/harmony/ad-lib assignments, syllabification, holds, and optional pronunciation data.
- **Performance recipe:** explicit deterministic realization settings and version/seed identity. It does not mutate the canonical score.

Use discriminated Pydantic models for genuinely different instrument semantics. Do not force guitars, drums, bass, vocals, and pads into one bag of optional fields.

Likely families to test are:

- chordal strings/guitar: strum steps, direction, subdivision, selected strings, voicing/fret constraints, mute/palm-mute/power-chord articulation
- drums: lane hits, accents/ghosts, repetition, and transition/fill variants
- bass: rhythmic pattern plus chord/scale-degree selection and approach behavior
- melodic/vocal: explicit motifs or notes, transformations, lyric-token assignments, holds, and phrase boundaries
- keys/pads: chord voicing, rhythm, sustain, register, and voice-leading policy

Only implement a family when an active fixture needs it. Exact notes remain valid semantic content for melody/solo material that cannot be usefully compressed.

## Whole-song composition and directives

The composition model receives the complete ordered form and full user context. A section occurrence may reference a shared pattern, but the model decides references and transitions with awareness of both neighbors.

Preserve these separately in the run record and composer input model:

1. raw user request and markup
2. resolved hard constraints
3. user-authored directives, associated with their location rather than flattened
4. versioned system instructions and music-knowledge fragments
5. composer-added enhancements

A deterministic validator rejects an enhancement that conflicts with a machine-checkable user constraint. For prose directives, the prompt requires fidelity and the run record makes later A/B evaluation possible; do not pretend every aesthetic conflict can be proven by code.

Music-practice knowledge used by the composer comes from versioned local records with source and verification metadata. An LLM may assist offline ingestion/diffing, but generation does not depend on live web searches and logs the exact knowledge-fragment IDs injected.

## Boundary-aware realization

Expanders receive the whole score or an explicit context window containing both adjacent sections. Fills, pickup notes, cymbal tails, anticipations, and transitions may cross a section marker while the form remains bar-aligned. A section is not expanded as an isolated miniature song.

Pattern reuse must allow an occurrence to request a bounded variation or transition overlay without copying the base pattern. Transformations need explicit semantics and deterministic composition order.

## Guitar-strum feasibility gate

Before a guitar schema is accepted, feasibility evidence must represent a reusable strum and apply it to at least one bar each of G, C, Am, and D. A down-strum realizes sounding strings from low to high; an up-strum reverses them. Voicing/fretboard choice determines which strings sound, including omitted strings and power-chord/muting behavior.

The semantic chord onset remains on its notated beat. The performance expansion emits deliberate per-string offsets and velocity contours. These offsets are technique, not stochastic humanization. The output must be identical for identical score plus recipe, and a future notation exporter must be able to ignore the performance offsets and render the canonical chord.

The evidence records:

- chosen voicing and sounding strings
- note order for each strum direction
- onset spacing and velocity contour
- behavior at chord changes and section boundaries
- manual playback result in at least one available DAW/instrument

Do not freeze a universal guitar language until the feasibility result and representation research are reviewed together.

## Lyrics and future singing

Parse the user's text into stable source tokens scoped to section occurrences. Primary vocal assignments reference those token IDs. Completeness means every singable source token has exactly one primary assignment across all vocal tracks in source order; harmony or call-and-response copies are explicitly non-primary and do not satisfy or violate coverage.

Display text never changes. Performance data may split a token into syllables, hold a vowel across notes, or provide a pronunciation/phoneme override. MIDI lyric export uses display text or a reversible display mapping, not phonetic respelling. The schema preserves this distinction for a future score-conditioned voice renderer, but this feature generates no vocal audio.

## Determinism and validation

Validation occurs before any file is written. It covers at least:

- resolved tempo, key, time signature, duration tolerance, and instrument constraints
- unique IDs and valid references
- ordered, non-overlapping section spans and legal boundary overlays
- pattern duration and transformation compatibility
- playable ranges/monophony where required
- source lyric coverage and ordering across primary vocal assignments
- deterministic expansion into a valid `Song`

Any randomness is an explicit input. The run record stores the seed, expander/recipe version, semantic-score hash, expanded-song hash, and artifact hash.

## Experiment provenance

Use a repository port so tests can run in memory and local development can use the smallest durable implementation justified by the live dependencies. Do not bind the domain to a production database prematurely.

Each run records:

- experiment-group ID, run/sample ID, parent revision if any
- raw user request and resolved constraints
- every injected prompt/knowledge component by version/hash and final messages sent
- provider, model, model settings, schema version, and available provider response/usage IDs
- raw responses, validation failures, retry feedback, timing, and terminal error
- validated semantic score and hashes for every generated artifact
- code/build identity when available without making local development fail

Successful and failed attempts are both evidence. Secrets and authorization headers are never logged. Multiple samples from the same experimental input share a group but remain separate immutable runs.

## Deferred boundaries

The semantic score must not import MIDI, MusicXML, DAW, plugin, audio, or storage implementations. That clean dependency boundary is sufficient for later exporters/renderers; do not add empty REAPER, VST, voice, or cloud adapters in this feature.

## Risks and mitigations

- **An invented schema becomes an expensive dead end.** Close the representation and guitar feasibility gates against common fixtures before adopting the public domain contract; keep export formats at the boundary.
- **Semantic compression becomes either too vague or as verbose as raw notes.** Measure serialized size and deterministic realizability on repeated patterns, explicit melody, cross-boundary events, and lyric-performance fixtures before accepting the representation.
- **Deterministic accompaniment sounds canned.** Encode technique and bounded variation as declared intent, preserve expressive note-level material where compression is harmful, and require manual playback evidence rather than equating theory metrics with quality.
- **Whole-song structured output omits or corrupts content.** Validate references, form, hard constraints, duration, and lyric-token identity before export; retain raw responses and retry evidence for diagnosis.
- **Migration leaves two production architectures.** Treat the legacy generator as temporary comparison machinery and make its removal observable in final acceptance.

## Known causal dependencies

- The representation and guitar feasibility evidence must precede adoption of the canonical schema because those results determine whether Melos can reuse an existing model and which guitar semantics are actually realizable.
- Deterministic realization requires validated identity, timing, pattern-reference, and lyric-assignment contracts; expanders cannot safely infer missing semantics.
- The legacy production path cannot be retired until the semantic path preserves the existing API/MIDI behavior and passes the final regression and quality gates.

## Suggested implementation approach

_This is strategic guidance, not a required sequence. The implementation lead should inspect the live repository, propose slices and actual order to the user, and may reorder this advice when code, tests, or unforeseen constraints justify it._

1. Close the representation and guitar feasibility gates together so the domain contract is evidence-based and does not inherit a disposable experiment by accident.
2. Establish the semantic ownership, validation, deterministic-realization, and provenance boundaries before coupling them to the live composition path; this keeps failures attributable and migration reversible.
3. Bring whole-song composition, distributed lyric identity, pattern reuse, and boundary-aware realization together through shared fixtures because none proves the intended outcome in isolation.
4. Integrate through the existing API/MIDI seams, compare repeated live samples, and retire the legacy production path only after the stable final acceptance contract passes.
