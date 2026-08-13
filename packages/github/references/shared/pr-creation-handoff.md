# PR Creation Handoff Contract

This is the canonical contract for how PRs get created across the github plugin. All workflows that need a PR created delegate to the create-pr procedure; none call `gh pr create` themselves.

## CRITICAL: create-pr is the plugin's ONLY PR-creating path

No other procedure calls `gh pr create`. Other workflows (resolve-issues, and any future caller) delegate via the create-pr procedure with the issue reference so no PR escapes the quality gate or the mandatory `review-pr procedure` handoff. **Do not add a bypass.**

## Duties owned by create-pr (not duplicated by callers)

1. **Pre-creation quality + security gate** — lint/test/build/type-check + secret scan, all must pass before `gh pr create`.
2. **Auto-closing-keyword linkage + non-default-branch warning** — see `./auto-closing-keywords.md`.
3. **Mandatory handoff to `review-pr procedure`** — the review → fix → commit+push → wait-for-review loop, until CI is green and every comment is triaged, then asks the user in the conversation whether to merge (merge commit/squash/rebase/don't) and waits for the reply **before** the closeout ceremony — the summary comment and body rewrite run only on a merge choice. This handoff is default-on; skipped only on explicit `--no-monitor` or user opt-out.
4. **Post-merge branch + worktree hygiene** — delegated onward to `review-pr procedure` (Phase 5 closeout), which deletes the remote + local head branches (when stack-safe and in the main worktree), removes the linked worktree (``git worktree remove` on the `.pi/worktrees/` path`), switches to `main`, fast-forwards local `main`/`develop` with origin, drops all other already-merged locals, runs `git worktree prune`, and scans for stale worktree directories. See `../review-pr/closeout.md`.

## Caller contract (resolve-issues and any future caller)

- Invoke ``create-pr procedure Closes #<n>`` with the issue reference **verbatim** — do not re-derive or second-guess the auto-closing keyword.
- Pass `--draft` through if early feedback is needed.
- Pass `--no-monitor` through **only** on an explicit user opt-out (never infer it).
- Pass `--auto-merge` through **only** on an explicit user opt-in (never infer it). create-pr forwards it to `review-pr procedure` as ``review-pr procedure <PR#> --auto-merge``; review-pr then skips the merge question — the closeout ceremony (summary comment + body rewrite) still runs first — and runs `gh pr merge --merge` once CI is green and every non-escalate comment is triaged. `escalate` items suspend the opt-in and fall back to asking the user in the conversation — see `review-pr/../review-pr/closeout.md` (Auto-merge branch).
- Do NOT wait inline for the PR URL; do NOT re-report the PR; do NOT call `gh pr create`.
- Creating the PR directly skips the quality gate, the auto-closing-keyword linkage, the non-default-branch warning, and the review-pr loop — all of it.

## Protected PR workflow

- No direct pushes to `main`/`develop`.
- All changes go through PR + review + CI.
- Every PR enters the `review-pr procedure` loop after creation — review, fix what is verified, commit+push, wait for the next review round — until CI is green and every comment is triaged, then the user is asked whether to merge before the closeout ceremony.
- Use worktrees to isolate development work; clean up after successful merge.

This file consolidates the four copies of the "only PR-creating path" contract that had drifted in their enumerated sub-items (duty order, `--no-monitor` placement, owned-duties list).
