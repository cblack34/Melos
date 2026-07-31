# Workflow — strategic handoff and delivery

The active build pack is the durable strategic contract. It defines the outcome, scope, non-negotiables, architecture boundaries, research gates, risks, causal dependencies, final acceptance, and a high-level suggested implementation approach. The implementation lead owns tactical decomposition with the user.

Treat suggested order as informed guidance, not a command. Preserve hard causal dependencies, but revise advisory sequencing when current code, tests, or unforeseen constraints justify a better route.

## Authority model

- **Strategic lead:** sets outcomes, guardrails, company-wide delivery governance, and final acceptance.
- **Implementation lead:** proposes and manages slices, actual order, integration, replanning, and delegation.
- **Execution agents:** complete bounded assignments and surface surprises; they do not change wider scope or architecture.
- **Human:** approves the tactical plan and is the only authority that merges to `main`.

## Before implementation

1. Read `AGENTS.md` and every active strategic document in order.
2. Inspect current code, tests, manifests, CI, branch state, and repository rules.
3. Resolve required research gates or return them to the user; do not adopt an irreversible design while its gate is open.
4. Evaluate the suggested implementation approach against repository reality.
5. Propose execution-sized slices, actual order and rationale, verification per slice, risk checkpoints, and useful delegation.
6. Discuss and revise the plan with the user before coding or creating issues, branches, PRs, or sub-agent assignments.

When evidence invalidates the plan, stop affected work, explain the impact, and propose a revision. Do not force reality to match the original suggestion.

## Delivery topology — feature spine with leaf PRs

1. Create one feature spine from current `main` for the user-approved active scope.
2. Create each leaf branch from the current spine for a tactical unit chosen by the implementation lead. Use `feat/<issue#>-<slug>`, `fix/<issue#>-<slug>`, or `chore/<issue#>-<slug>` when an issue exists.
3. Implement the unit, tests, and affected docs; run self-verification and self-review.
4. Sync the leaf with the spine; stop on a non-trivial conflict.
5. Open a leaf PR to the spine, run the review loop, and require green CI.
6. The implementation lead may squash-merge a clean leaf PR into the spine and must confirm the spine remains green.
7. Replan and repeat leaves as needed; leaf count and order remain tactical and adaptable.
8. When final acceptance passes on the spine, sync it with `main`, resolve only trivial conflicts, and open the spine PR to `main`.
9. Stop for the human to review and merge the spine PR.

The agent never merges to `main`. Do not run multiple spines for the same active scope unless the user approves that coordination cost.

## Delegation

The implementation lead retains plan, ordering, integration, and verification ownership. Delegate only concrete bounded assignments after the relevant plan is agreed. Give each execution agent its scope, constraints, interfaces, expected result, and checks. Use the least expensive capable model and reasoning effort for bounded execution and review work. Require agents to return unexpected dependencies or contradictions instead of expanding scope, and review delegated work before integration.

## Build and self-verify

For each tactical unit:

1. Research unfamiliar or drift-prone APIs in current official documentation.
2. Implement only approved active scope and preserve strategic invariants.
3. Add or update tests and affected docs in the same change.
4. Run every command in the `AGENTS.md` definition of done until green.
5. Review the diff against [`code-quality.md`](code-quality.md), strategic acceptance, and the unit's derived checks.

## Pull request mechanics

- Use one PR for a complete, reviewable delivery unit chosen by the implementation lead; this rule does not predetermine feature slicing.
- Use a Conventional Commits PR title.
- In the PR body, state scope, verification evidence, material risks or deviations, documentation changes, and related issues.
- Use `Closes #N` only on the final PR whose base is `main`. A leaf PR to the spine references its issue without closing it. Confirm closure after the human merges to `main`.
- Re-sync the PR base and re-run relevant checks before review. Stop on non-trivial conflicts and never force-push a protected or shared branch.

## PR review loop

Use this reviewer precedence:

1. **GitHub Copilot first.** It is enabled for this repository and produced review threads on PR #51. Request it on an existing PR with `gh pr edit PR-NUMBER --add-reviewer @copilot`.
2. **`review-pr` fallback** when Copilot is unavailable or cannot produce a usable review. Use `address-pr-review` for actionable comments when available; otherwise follow the same reply/resolve mechanics manually.
3. **Fresh review sub-agent fallback** only when neither Copilot nor `review-pr` is usable. Give it the PR diff, relevant strategic constraints, acceptance criteria, and verification evidence. If delegation is unavailable, stop for human review; author self-review is not independent review.

The selected reviewer changes the review source, not the quality gate:

- Wait for a complete review and count all unresolved threads. A trusted review must match PR `HEAD`; a stale review does not count.
- Evaluate every comment. Fix in-scope issues; return scope-changing feedback to the user. Record valid deferred work in the handoff unless issue creation is authorized.
- Reply in every thread, then resolve it after pushing the fix or explaining the disposition.
- Re-run self-verification and CI after every code change prompted by review.
- Re-request review and require a zero-new-comment, HEAD-matched pass before any permitted merge.
- Allow at most three request/address cycles total. Switch reviewer when Copilot is unavailable or unusable; changing reviewers does not reset the bound. Never merge with a genuine unresolved issue.

## CI

`.github/workflows/ci.yml` runs the `AGENTS.md` backend and frontend commands on pull requests and pushes to `main` or `spine/**`. Keep it aligned with the canonical commands. Every integration requires green CI even if repository rules do not enforce required checks server-side.

## Final verification

Slice checks prove progress but never replace [`../features/semantic-composition/acceptance.md`](../features/semantic-composition/acceptance.md). Before the human `main` merge, run every final command and acceptance check on the completed spine. Reconcile shipped behavior with strategic and descriptive docs. Report unresolved gates, accepted risks, deviations from suggested order, and deferred scope.

## Stop and return to the user

Stop affected work when:

- a directive, non-negotiable, or final criterion conflicts with implementation;
- a representation or feasibility gate is unresolved;
- current code requires an unapproved public-contract, architecture-boundary, scope, or material-risk change;
- a paid service, incompatible license, destructive action, secret, production write, or broad refactor is required;
- two consecutive PRs fail, or the same test flakes across two runs;
- review finds a genuine unresolved issue or exhausts the fallback;
- integration needs a non-trivial conflict resolution or force-push;
- an external action exceeds the recorded authority;
- a bad merge already landed on `main`; open a revert PR, then stop and report.

Everything else within the approved plan: keep going until the current delivery gate is reached.
