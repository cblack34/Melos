# Workflow — how the agent plans and ships

You work on **spine/integration branches** per milestone. You may squash-merge completed work into the spine branch. A **human** merges the spine branch into `main`. You do not merge to `main` yourself.

## Two methods: the backbone (horizontal) and milestones (vertical)

- **Backbone (horizontal)** — the left-to-right sequence of activities the end user performs with the product. Mapping the backbone gives the whole picture "mile-wide, inch-deep."
- **Milestone (vertical slice)** — a thin, end-to-end, **working** increment cut down through the backbone. The agent is free to define the milestone breakdown. The MVP (prompt → downloadable multi-track MIDI) is the first meaningful working increment; intermediate walking-skeleton slices are encouraged.

## Hierarchy: Milestone ▸ Epic ▸ Story ▸ Task

- **Milestone** — a shippable vertical slice. Maps to a GitHub Milestone.
- **Epic** — a backbone activity / feature-area theme. A GitHub Issue labeled `type: epic`.
- **Story** — one theme at one milestone, in agile story form with acceptance criteria. A GitHub Issue labeled `type: story`, sub-issue of its Epic, assigned to its Milestone. Non-user work is `type: chore`.
- **Task** — checklist item in the story body by default; promote to its own sub-issue only when it needs its own branch/PR.

**Where PRs happen:** usually a Story, occasionally a Task. PRs target the current spine/integration branch, not `main`.

## GitHub mapping

- Branch per story: `feat/<issue#>-<slug>` (or `fix/…`, `chore/…`) off the spine branch (or off `main` only if no spine exists yet).
- `Closes #N` in the PR body.
- Squash-merge into the spine branch once CI is green and review is clean.
- Human merges spine → `main`.

## The loop (per story)

1. Pick the next story (lowest-numbered open story in the current milestone whose dependencies are done).
2. Branch off the spine (or `main` if appropriate).
3. Research best-practice approach and verify library/API syntax against current official docs before writing code.
4. Build + tests + any affected docs (docs ship in the same PR).
5. Run every self-verify command until green.
6. Sync with the target branch; non-trivial conflicts → STOP and flag.
7. Adversarial self-review against [`code-quality.md`](code-quality.md).
8. Open PR into the spine branch with `Closes #N`.
9. Address review until clean and HEAD-matched.
10. Squash-merge into spine. Loop.

## PR review

Prefer dedicated review skills if available. Otherwise: request review, address every in-scope thread, resolve threads after pushing fixes, re-request until a zero-new-comment HEAD-matched pass. Bound: 3 cycles; if the reviewer never posts on HEAD, proceed on thorough self-review and note it in the PR.

## CI

CI from day one. The first chore story scaffolds the project and adds a GitHub Actions workflow that runs the self-verify commands (typecheck, lint, test, build) on every PR. Keep CI minimal.

Every PR after the initial scaffold requires green CI. "Never merge on red CI" is agent discipline.

## STOP conditions (halt and report to the human)

- Schema change that alters the public compact-JSON contract, or a new pattern/refactor beyond the task.
- Non-trivial merge conflict, or any situation that would need a force-push.
- 2 consecutive failed PRs, or the same test flaking across two runs.
- Review loop exhausts its bound with a genuine unresolved issue.
- Anything ambiguous, risky, or that would break the spine/`main`.
- Request to force-push without prior human approval.
- Introduction of a paid service other than OpenRouter, or a dependency with a disallowed license.

Everything else: keep going.
