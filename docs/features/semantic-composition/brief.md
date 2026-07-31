# Semantic Composition Foundation

_This is the active strategic feature brief. Code, schemas, and names are illustrative; behavioral requirements, architecture contracts, non-negotiables, and [`acceptance.md`](acceptance.md) are authoritative. The implementation lead owns tactical decomposition with the user._

## Problem

The shipped generator asks an LLM to repeat every MIDI-shaped note in a full arrangement. That is expensive and makes reusable musical ideas implicit. Its lyric-completeness validator also assumes one vocal track carries the whole text; real output has distributed lyrics across several tracks, so the disabled validator cannot prove whole-song coverage or distinguish lead handoffs from overlapping parts. The `Song` model also makes MIDI limitations look like composition rules.

Melos needs a compact whole-song representation that says what the music means—form, harmony, reusable patterns, techniques, transitions, melody, and lyric delivery—then lets deterministic code realize that intent as exact note events. This is the prerequisite for later editing, notation, audio rendering, stems, and DAW exports.

## User outcomes

- A user submits the existing prompt, hard constraints, optional section/directive markup, and optional lyrics and still receives a usable multi-track MIDI file.
- Supplied lyrics are complete and retain the user's display text even when lines are divided among vocal parts or a pronunciation hint is needed later.
- Repeated accompaniment is represented once and referenced across the form; changing a pattern or chord progression has predictable downstream effects.
- Intentional techniques such as a guitar strum sound like those techniques when expanded, while the canonical chord remains aligned for future notation.
- Every generated sample is traceable to the raw request, injected knowledge/instructions, model configuration, response, validation, and exported artifact.

## In scope

1. Compare existing notation, pattern, composition, and DAW interchange representations before approving a Melos schema or dependency.
2. Add a Pydantic semantic score above the shipped MIDI-shaped `Song` model.
3. Make one whole-song composition operation produce the ordered arrangement. Existing meta resolution and optional lyric-writing calls may remain separate; a validation-driven retry retries the whole score, and no section gets its own composition call.
4. Preserve user constraints and directives as authoritative inputs while allowing the composer to add compatible musical detail from versioned local music-practice knowledge.
5. Define reusable, typed pattern concepts for distinct instrument families. Implement only the families needed by the acceptance fixtures; do not attempt a universal music language.
6. Prove deterministic guitar chord/voicing/strum expansion, including direction, string order, articulation, velocity contour, and section-boundary context.
7. Expand a validated semantic score deterministically into the existing note-level `Song`, then reuse the current MIDI exporter and download flow.
8. Add the target-duration request/control and validate hard meta/instrument constraints, pattern references, duration, section alignment, playable ranges, transition placement, and complete primary lyric coverage across vocal tracks.
9. Store experiment/run provenance locally behind a repository boundary, keeping raw user input distinct from injected prompt components.
10. Extend the quality harness to compare repeated samples and report representation size, validation results, and musical metrics without declaring subjective quality from theory checks alone.

## Out of scope

Audio rendering, vocals-as-audio, MusicXML/MNX/DAWproject export, DAW/plugin adapters, cloud storage and subscription policy, user-facing score editing, and public SaaS licensing are deferred in [`../../decisions/inactive-directions.md`](../../decisions/inactive-directions.md).

The feature does not promise that deterministic theory checks make a song good. They detect contract violations and measurable pathologies; human preference remains the quality signal.

## Non-negotiables

1. **Whole-song authority:** every composition attempt sees the full form, including preceding/following sections and every user directive. Reusable references replace duplication; section-by-section generation is not a fallback. Any validation retry retries the complete score.
2. **Semantic source:** Pydantic models are the source of truth. The composition response contains no binary/file payload and does not expand repeated accompaniment into final MIDI note lists.
3. **User authority:** separately preserve user-authored constraints/directives and system enhancements. Enhancements may clarify or strengthen but never contradict the user.
4. **Deterministic realization:** the same validated score, expander version, and declared seed/configuration produce the same note-level result. Intentional strum offsets are performance realization, not random corruption of score time.
5. **Lyric identity:** canonical display text is immutable. Pronunciation, syllabification, melisma, and phonetic hints are separate performance data; primary assignments cover every source lyric token exactly once across vocal parts.
6. **Reproducible experiments:** successful and failed runs record enough separated inputs and versions to compare prompt or model changes without conflating variables.

## Definition of done

All items in [`acceptance.md`](acceptance.md) pass, the existing MVP regression suite stays green, the required manual DAW strum check is recorded, and representation research supports the chosen schema/dependencies. No deferred audio or SaaS work is implemented.
