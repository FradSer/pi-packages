---
name: review-pr
description: 'Reviews a pull request: baseline review of the PR diff, then a bash poll loop watches CI and incoming reviewer comments, triages each comment skeptically, applies only verified fixes, and commits+pushes via /skill:commit-and-push until CI passes and no comments remain to adopt — then asks whether to merge. Use when the user asks to "review a PR", "monitor PR review comments", "address reviewer feedback on #123", or "watch CI on a pull request".'
---

# Review a Pull Request

Run the baseline review of the PR diff, then keep a watch over CI and new reviewer comments until the PR settles.

## Pi tools

Use only Pi built-ins: `bash` (for `gh` / `git` / poll script), `read`, `edit`, `write`.

There is no Monitor, Task, TaskStop, AskUserQuestion, PushNotification, or ExitWorktree tool. Equivalents:

| Claude-era concept | Pi practice |
|--------------------|-------------|
| Task independent agent | Run a **clean reasoning pass** on the diff/comments (no authorship bias); do not reuse prior justifications |
| Monitor | Bounded poll with `scripts/review-loop.sh` via `bash` (or re-run on each user turn) |
| TaskStop | Stop re-invoking the poll script |
| AskUserQuestion | Ask the user in the normal conversation and wait for their reply |
| PushNotification | Surface escalate items clearly in the conversation |
| ExitWorktree | `git worktree remove` under `.pi/worktrees/` |
| Skill("…") | `/skill:<name>` |

## Invocation args

When invoked as `/skill:review-pr <args>`, the text after the skill block is the PR number/URL plus optional `--auto-merge`. Pi does not expand `$ARGUMENTS` placeholders inside skill bodies; use the trailing invocation text.

## Bootstrap (run with bash)

```bash
# Replace <args> with the PR number or URL from invocation
gh pr view "<args>" --json number,title,headRepository,headRepositoryOwner,additions,deletions,headRefName
git remote -v | head -2
gh auth status 2>&1 | head -3
```

## Phase 1: Baseline Review and Sizing

**Goal**: Initial review, resolve repo, pick poll interval.

**Actions**:
1. Parse PR number or URL from invocation args. If absent, `gh pr list` and ask the user. **Normalize `PR` to the bare number**: `PR=$(gh pr view "<args>" --json number -q .number)`. Strip `--auto-merge` before resolving the number — default is explicit merge ask.
2. **Baseline review** — pull `gh pr diff <PR>` and review with a clean skeptical pass (as if you did not author the code). Findings as `path:line: issue` (prompt in `references/review-loop.md`). Treat as the first `[comment]` batch into Phase 3 triage — same gatekeeping as live comments.
3. Resolve `REPO=<owner>/<repo>` from PR metadata (fallback: parse `git remote get-url origin`).
4. Size from `additions+deletions` → `INTERVAL` seconds per `references/review-loop.md`: 180 / 300 / 480; floor 60s, cap 7200s.

## Phase 2: Launch the Poll Watch

**Goal**: Stream CI + comment events.

**Action**: Run `scripts/review-loop.sh` with `PR`, `REPO`, and `INTERVAL` (script also accepts `--pr`/`--repo`/`--interval`). Prefer short bounded runs per turn rather than an infinite foreground loop that blocks the session. Re-enter the poll on subsequent turns until stop conditions hold.

```bash
# resolve skill dir from this skill's location when needed
bash scripts/review-loop.sh --pr "$PR" --repo "$REPO" --interval "$INTERVAL"
```

**CRITICAL: Do NOT skip the watch based on a launch-time snapshot.** Empty `.github/workflows/` does not mean no comments — bots and humans post later. Only skip on explicit user opt-out ("just baseline review, don't watch").

## Phase 3: React to Each Event

**Goal**: Fix actionable items, reject noise, escalate ambiguity. Full rules in `references/review-loop.md`.

- `[ci] <name>: fail|cancel` → `gh run view <run-id> --log-failed`, fix, then `/skill:commit-and-push`. **Do NOT auto-fix** auth/permission, missing-secret, flaky, or infrastructure failures — stop and report.
- `[comment]` batch → **clean skeptical triage pass**. Apply ONLY `fix` verdicts. Reply by type: inline → `gh api repos/$REPO/pulls/$PR/comments/<id>/replies`; issue-level → `gh pr comment`; review summary → skip reply. Commit+push all `fix` changes in one round via `/skill:commit-and-push`; hide addressed comments as `OUTDATED` via `minimizeComment`; resolve inline threads via `resolveReviewThread`. Leave `escalate` open and surface them to the user.
- Ambiguous comments → report to user; do not guess.

**CRITICAL mindset**: Default to skepticism. Rejecting noise is normal.

## Phase 4: Stop Conditions

Stop re-polling when EITHER holds — details in `references/review-loop.md`:
- **Normal stop**: every CI check terminal + passing; every comment reflected on (only `escalate` remain); user signals done.
- **Hard cap**: ~2h wall-clock or explicit opt-out — surface unsettled state, then stop.

A temporarily empty comment queue is **not** a stop signal.

## Phase 5: Closeout — Merge Decision First, Then Ceremony

**Goal**: Ask whether to merge FIRST; ceremony only on a merge choice. Full steps in `references/closeout.md`.

**CRITICAL constraints**:
1. Arm closeout when Phase 4 holds: `bash scripts/arm-closeout.sh "$PR"` (append `--auto-merge` if opt-in). Clears with `bash scripts/clear-closeout.sh "$PR"` after any decision.
2. Ask the merge question immediately (merge [Recommended] / squash / rebase / don't) in the conversation — do not post summary/body first.
3. Ceremony only on a merge choice: capture summary URL from `gh pr comment` stdout.
4. Review-cycle line in rewritten body must contain that literal URL.
5. Order: summary first, body second.
6. Do not sign summary as AI-generated.
7. Do not merge or run ceremony while CI is red or comments remain open; never auto-merge past open `escalate`.
8. Merge only after explicit user choice; never `gh pr merge --auto`. **`--auto-merge`**: when set in Phase 1, skip the ask but still run ceremony first, then `gh pr merge --merge` once green and non-escalate comments triaged. Open `escalate` suspends auto-merge — re-arm without the flag and ask explicitly.
9. Post-merge hygiene: remove linked worktree under `.pi/worktrees/` if present (`git worktree remove …`), switch to `main`, fast-forward-sync `main`/`develop` with origin — see `references/closeout.md`.

Stop the poll after closeout completes and closeout state is cleared.

## References

- **Review Loop**: `references/review-loop.md`
- **Closeout**: `references/closeout.md`
- **Commit Standards**: `references/commit-standards.md` (rounds use `/skill:commit-and-push`)
- **Repository Templates**: `references/repository-templates.md`
- **Examples**: `references/examples.md`
