# Code quality

Write code a strict senior engineer would approve on the first read. Two named foundations, treated as **one spine** (they overlap ~80%, so don't juggle multiple vocabularies): **Robert C. Martin** (Clean Code, SOLID, Clean Architecture) and **ArjanCodes** (cohesion/coupling, program-to-abstractions, composition over inheritance, separate creation from use, data-first, simplicity/YAGNI). Apply as judgment tools **only when you touch the code** — one focused change at a time, never a big-bang refactor.

## Design (module / type level)

- **High cohesion, one reason to change** (SRP): a module/component/function does one job. If you can extract another well-named function, it was doing more than one thing.
- **Low coupling, depend on abstractions** (DIP): depend on interfaces/protocols, not concretions; inject external dependencies (clock, storage, logger, network) so they can be swapped and tested.
- **Open for extension, not modification** (OCP): adding a variant should touch a known, small set of places the compiler or type-checker can flag — never a scattered hunt. Reach for runtime registries only for genuinely open-ended, plugin-style extension points.
- **Composition over inheritance**; **separate creation from use** (build objects in one spot, use them elsewhere); **data-first** — a single in-memory source of truth, with UI and derived values computed from it.
- **Dependency rule / IO at the edges:** pure domain logic imports no UI, framework, or IO code; side effects (storage, clock, network, DOM) live in a thin outer ring. This is what makes the fast unit-test self-check possible.

## Clean code (unit level)

Intention-revealing names that encode the domain **and** unit where units exist (`widthInches`, `isRetryEnabled`); booleans read as questions. Small functions that do one thing at one level of abstraction, few params (group data clumps into typed objects). Queries return and don't mutate; commands mutate and return nothing meaningful. One home per concept (**DRY**). Comments explain **why**, not what — refactor confusing code instead of narrating it. Delete dead and commented-out code; don't add generality for a hypothetical second case.

## Project-specific rules

- **Pydantic over dataclasses** — domain and request/response models use Pydantic V2 exclusively so validation and serialization stay consistent.
- **LLM output is data, not files** — the MIDI generation call returns structured data only; binary MIDI is produced by a pure exporter after validation.
- **Interfaces for most libraries** — wrap third-party services (MIDI writers, LLM clients, etc.) behind protocols so tests and future swaps stay cheap. Core stable libraries may be used directly when abstraction cost exceeds benefit.
- **License gate** — dependencies must be compatible with keeping Melos source closed. Prefer MIT, Apache 2.0, BSD, ISC, or equivalent permissive licenses. Weak, file-level copyleft (for example MPL-2.0) requires review confirming that obligations remain confined to covered dependency files, plus an entry in [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md). Reject AGPL, GPL, strong/network copyleft, and any license that could require disclosure of Melos source.
- **No secrets in the repo** — API keys and env-specific config live in environment / secret stores, never in source.

## Smells to hunt (in self-review)

- **Universal:** long function, God component / large class, duplicated code, primitive obsession, long parameter list / data clumps, feature envy, shotgun surgery (one change touching many files → centralize the knowledge), message chains (walking `a.b.c.d` instead of asking the source of truth), unclear names, dead / speculative code.
- **Project-specific:** LLM response parsed without Pydantic validation; MIDI bytes constructed inside an agent/tool call; new dependency without a license check; dataclass used for a domain concept that already has (or should have) a Pydantic model.

## Testing

Unit-test the **pure logic** where it pays off — domain rules, conversions, serialization round-trips, validation. The acceptance doc's self-check is the definition of done. Verify UI and feel by running the app, not by building heavy component-test scaffolding. If something is hard to test, that's a design smell — fix the coupling, don't test around it.
