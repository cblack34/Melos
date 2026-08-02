# Slice plan — Semantic composition foundation

> **Approved, tactical, and subordinate.** This is the durable charter for the
> single semantic-composition slice delivered on
> `spine/semantic-composition`. The active strategic pack remains authoritative.
> GitHub issues hold execution details, progress, blockers, and verification.

## Strategic source

- **Active build pack:** [`brief.md`](brief.md), [`design.md`](design.md), and
  [`acceptance.md`](acceptance.md), constrained by
  [`../../decisions/inactive-directions.md`](../../decisions/inactive-directions.md)
- **Human approval:** approved before the spine was created; on 2026-08-01 the
  human clarified that **slice and spine are the same unit** and authorized the
  implementation lead to continue bounded leaves until the slice is complete
- **Final acceptance advanced:** every criterion in [`acceptance.md`](acceptance.md)

Historical files under [`slices/`](slices/) are completed **leaf records** whose
titles use earlier terminology. They do not define separate slices or approval
gates and are retained unchanged as delivery evidence.

## Outcome

Replace the shipped MIDI-shaped composition core with one whole-song,
Pydantic-validated semantic score and deterministic realization while
preserving the existing prompt-to-multi-track-MIDI experience.

The slice is complete only when the semantic path is the sole production
composition path, final acceptance passes on the spine, and the final PR is
ready for the human to merge to `main`.

## Why this slice is active

The direct-note generator is costly, obscures reusable musical intent, and
cannot prove primary lyric coverage distributed across vocal parts. The active
pack replaces it with compact semantic identity, reusable typed patterns,
whole-song composition authority, deterministic realization, and reproducible
experiment evidence. Research and guitar feasibility established that Melos
should own the Pydantic score instead of adopting a representation dependency.

## Scope

### In scope

- Evidence-backed semantic representation and closed-source-compatible
  dependency decisions.
- One versioned whole-song Pydantic semantic score with typed instrument-family
  intent, exact canonical timing, reusable patterns, occurrence-aware form,
  directives, and lyric identity.
- One complete-song composition operation with complete-score retries and
  user constraints that cannot be countermanded by enhancements.
- Deterministic realization into the existing `Song` performance model and
  unchanged MIDI exporter, including boundary-aware guitar technique.
- Target duration, distributed primary lyric coverage, local versioned music
  knowledge, experiment provenance, quality evidence, and integration through
  the existing API/UI/download flow.
- Retirement of the obsolete direct-note production architecture after the
  semantic path passes final regression and quality gates.

### Out of scope

- Audio or voice rendering; MusicXML, MNX, or DAWproject export; DAW/plugin
  adapters; stems; accounts, subscriptions, cloud storage, or retention policy;
  public score editing; and every other direction deferred by the active pack.
- A universal instrument language or speculative adapters/families without an
  active acceptance fixture.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Canonical semantic source | Makes one framework-free Pydantic score the composition authority. |
| Whole-song authority and user fidelity | Gives every attempt the complete ordered form, scoped directives, lyrics, and hard constraints. |
| Deterministic realization | Expands declared intent through versioned typed adapters without mutating canonical timing. |
| Lyric identity | Proves exactly-once ordered primary coverage across vocal parts while preserving display text. |
| Reproducible experiments | Separates raw and injected inputs and records attempts, retries, versions, responses, and artifact hashes. |
| Shipped MVP preservation | Reuses the existing `Song`, MIDI exporter, API/UI shape, and regression suite until controlled legacy retirement. |

## Gates and dependencies

### Hard gates

- Representation research and deterministic guitar feasibility precede schema
  adoption. Both are complete and integrated on the spine.
- Validated semantic identity, timing, references, and lyric assignments
  precede deterministic realization. Both are complete and integrated.
- The whole-song composition boundary must exist before provenance can record
  stable final messages, retries, responses, and semantic artifacts.
- The semantic path must preserve production behavior and pass final acceptance
  before the legacy generator is retired.

### Sequencing recommendations

- Choose and execute one bounded leaf at a time from current repository
  evidence. Leaf order and count remain tactical; do not create an upfront
  execution backlog.
- Put implementation details and live status in GitHub issues rather than this
  charter. Return material public-contract, architecture, scope, or risk changes
  to the human before proceeding.

## Architecture and contracts

- **Affected seams:** `GenerationRequest` and parsed user intent; resolved meta;
  whole-song semantic composer; `SemanticScore`; deterministic realization;
  existing `Song` and MIDI exporter; experiment repository; quality harness;
  existing API, SSE, UI, and download flow.
- **Public contracts:** preserve shipped contracts unless a bounded leaf
  explicitly returns a necessary contract decision to the human. The final
  production path changes composition ownership, not the user's MIDI-download
  outcome.
- **Data and migration considerations:** experiment records use a repository
  boundary and the smallest durable local implementation justified by live
  dependencies. No production database or external retention policy is assumed.

## High-level approach

Continue from the integrated representation, semantic-kernel, and realization
leaves. Establish the missing whole-song composition and experiment boundaries
before routing production traffic through them. Add only acceptance-required
instrument semantics and constraint controls. Integrate through the existing
application seams, compare evidence, then remove the obsolete generator only
after the semantic path is proven complete.

## Verification

- Each leaf runs the complete backend and frontend definition-of-done commands,
  receives green GitHub CI, and completes a clean HEAD-matched independent
  review loop before spine integration.
- Final verification exercises every criterion in [`acceptance.md`](acceptance.md),
  preserves the completed MVP acceptance suite, records required manual musical
  evidence, and confirms no deferred implementation leaked into the slice.

## Risks and stop conditions

- Stop for human input before changing strategic scope, final acceptance, a
  public contract or architecture boundary, directive semantics, duration
  tolerance, a material data/security risk, or dependency/license policy.
- Stop if complete structured scores cannot fit supported model limits, if
  deterministic realization cannot preserve requested intent, or if migration
  would leave two selectable production architectures at final acceptance.
- Never implement section-by-section generation, random canonical timing,
  generative instrumental audio, or speculative deferred adapters as fallback.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#52](https://github.com/cblack34/Melos/issues/52) — Semantic composition foundation | Parent execution tracker for this slice. | Active strategic pack |
| [#53](https://github.com/cblack34/Melos/issues/53) — Select the semantic music representation | Representation research gate. | None |
| [#54](https://github.com/cblack34/Melos/issues/54) — Deterministic guitar strumming | Guitar feasibility gate and manual evidence. | None; reviewed with #53 |
| [#57](https://github.com/cblack34/Melos/issues/57) — Establish the canonical semantic score kernel | Canonical identity, validation, patterns, and lyric ownership. | #53, #54 |
| [#59](https://github.com/cblack34/Melos/issues/59) — Deterministically realize semantic scores | Semantic-score-to-`Song` realization and playback evidence. | #57 |
| [#61](https://github.com/cblack34/Melos/issues/61) — Establish the whole-song semantic composer boundary | Current leaf: complete-song model operation and retry seam. | #57, #59 |
| [#27](https://github.com/cblack34/Melos/issues/27) — Song length as a verified constraint | Acceptance-required target-duration contract through the semantic path. | Whole-song composition boundary |
| [#39](https://github.com/cblack34/Melos/issues/39) — Distributed lyric completeness | Production use of canonical primary lyric assignments across vocal parts. | Whole-song composition boundary |

## Delivery shape

- **Topology:** one feature spine with bounded leaf PRs
- **Spine:** `spine/semantic-composition`
- **Current leaf:** `feat/61-whole-song-composer-boundary`
- **Final PR:** pending final acceptance
- **Human merge gate:** only the human may physically merge the final PR to
  `main`; agents stop when it is ready

## Amendments

None.

## Delivery record

Complete once when the final spine PR is ready for the human to merge.

- **Outcome:** pending
- **Verification:** pending
- **Deviations:** pending
- **Unresolved gates or risks:** pending
- **Final PR:** pending
- **Merge state:** not ready
