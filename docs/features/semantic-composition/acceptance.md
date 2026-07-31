# Acceptance

The feature is complete only when every item below holds and the canonical self-verify commands in [`AGENTS.md`](../../../AGENTS.md) pass. Tactical replanning may add slice checks but may not weaken or replace this contract.

## Representation and architecture

- [ ] The representation decision compares existing standards/languages/libraries against the common fixtures, cites current official sources and exact licenses, and explains every custom concept retained. _Human review._
- [ ] Every dependency added for the feature has a recorded exact license compatible with closed-source Melos; required notices are present and no strong/network-copyleft dependency is introduced. _Automated dependency inventory plus human license review._
- [ ] The canonical composition artifact is a versioned Pydantic semantic score that imports no MIDI, DAW, plugin, audio, web-framework, or persistence implementation. _Pure test: dependency/import rule plus model round-trip._
- [ ] Repeated accompaniment is defined once in a typed pattern registry and referenced by multiple form occurrences rather than copied as expanded notes. _Pure test: fixture identity/reference assertions._
- [ ] Distinct implemented instrument families use typed/discriminated semantics rather than one optional-field bag. _Pure test: invalid cross-family fields are rejected._

## Whole-song generation and user authority

- [ ] WHEN one sample is requested, one whole-song composition operation receives all requested section occurrences and scoped directives and returns the complete ordered form; any validation-driven retry again receives the complete score, and no section-level composition call occurs. Existing meta/lyric-writing calls do not count as composition calls. _Pure integration test with a spy model._
- [ ] WHEN the user supplies tempo, key, time signature, instrumentation, section/directive markup, or target duration, the validated score and expanded song obey every machine-checkable constraint or the request fails with precise feedback. _Pure tests plus live case._
- [ ] WHEN system knowledge or the composer enriches a request, the raw user text remains separately stored and no machine-checkable enhancement contradicts it. _Pure test: conflict rejection and provenance comparison._
- [ ] GIVEN representative prose directives including a deliberately restrained chorus, the effective plan strengthens unspecified musical detail without countermanding the requested character, instrumentation, or intensity. _Human review of raw directive, injected enhancement, validated score, and MIDI playback._
- [ ] Runtime composition uses versioned local knowledge fragments and records their IDs/hashes; it does not require a live web search. _Pure integration test._

## Deterministic realization

- [ ] GIVEN the approved G–C–Am–D fixture and down/down/up/up/down/up pattern, the guitar expander produces the expected voicings, string order, chord changes, onset offsets, and velocity contour. Down travels low-to-high and up high-to-low over sounding strings. _Pure test._
- [ ] GIVEN the same semantic score, expander version, seed, and configuration, repeated realization produces identical note events and hashes. _Pure test._
- [ ] The semantic chord remains on the exact notated beat while the performance model contains deterministic per-string strum offsets. _Pure test._
- [ ] WHEN a fill, pickup, anticipation, or tail crosses a section boundary, realization uses both neighboring sections and emits no accidental gap, duplicate attack, or clipped event. _Pure test fixtures._
- [ ] A manual playback in an available DAW/instrument confirms the guitar fixture is recognizably strummed; the record includes the renderer/instrument and limitations heard. _Manual check._

## Lyrics

- [ ] WHEN supplied lyrics are divided among multiple vocal tracks, every source token has exactly one primary assignment in source order across the song. _Pure tests: lead-only and call-and-response fixtures._
- [ ] WHEN harmony/ad-lib parts repeat text, their non-primary assignments neither satisfy missing primary coverage nor create duplicate-primary errors. _Pure test._
- [ ] WHEN syllables, vowel holds, or pronunciation overrides are present, canonical display text remains unchanged and reconstructs exactly. _Pure test._
- [ ] MIDI lyric output never substitutes phonetic respelling for the user's display text. _Pure export test._

## Experiments and observability

- [ ] Every successful or failed composition attempt records its experiment/run identity, raw request, resolved constraints, injected prompt/knowledge versions, final messages, provider/model/settings, raw response, validation/retry history, timing, schema/expander versions, and available usage/provider response IDs. _Repository integration test._
- [ ] Stored logs contain no configured API key, authorization header, or secret value. _Pure redaction test._
- [ ] Multiple samples from identical inputs are immutable sibling runs in one experiment group; changing a single prompt component creates a distinguishable run without modifying the user request. _Pure repository test._
- [ ] The quality report includes representation size, duration, lyric coverage, retry/validation counts, deterministic musical metrics, and artifact hashes without using theory metrics as a proxy for subjective quality. _Harness test._

## Regression and delivery

- [ ] WHEN a valid request is submitted through the existing web UI, the semantic path emits progress and returns a downloadable multi-track MIDI file with correct supplied meta and instruments. _Automated API/UI tests plus live browser check._
- [ ] Existing [completed-MVP acceptance](../../archive/mvp/acceptance.md) behavior remains green, including MIDI parsing, vocals/lyrics events, sections, instrument constraints, SSE failure reporting, and model selection.
- [ ] The production configuration cannot select the obsolete direct-note LLM generator after migration; unused prompting/validation code is removed rather than retained as a second active architecture. _Pure configuration/test assertion._
- [ ] No audio renderer, voice renderer, MusicXML/DAWproject exporter, plugin catalog, account/subscription system, or SoundGrid integration is introduced by this feature. _Human review against changed files._
