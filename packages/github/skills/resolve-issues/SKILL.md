---
name: resolve-issues
description: Resolves GitHub issues using isolated worktrees and test-driven development, then delegates PR creation to /skill:create-pr so the quality gate and the /skill:review-pr loop always run. Use when the user asks to "resolve an issue", "fix issue #123", or needs to implement a solution for a specific GitHub ticket using a structured workflow.
---

# Resolve GitHub Issues

Execute issue resolution workflow using isolated worktrees, TDD methodology, and agent collaboration.

## Pi tools

Use only Pi built-ins: `bash` (for `gh` / `git` / worktrees), `read`, `edit`, `write`.

Worktrees live under `.pi/worktrees/` (rewritten by the `git` package extension when present). There is no EnterWorktree / ExitWorktree tool — use `git worktree` via `bash`.

Handoffs use `/skill:<name>`.

## Invocation args

When invoked as `/skill:resolve-issues <args>`, the text after the skill block is the issue number or description. Pi does not expand `$ARGUMENTS` placeholders inside skill bodies; use the trailing invocation text.

## Bootstrap (run with bash)

```bash
git status
git branch --show-current
git worktree list
gh issue list --state open --limit 10
gh auth status
```

## Requirements Summary

Use isolated worktrees to avoid disrupting main development. Follow TDD cycle (red → green → refactor). Reference issues in commits using auto-closing keywords. See `references/requirements.md`.

## Phase 1: Issue Selection and Worktree Setup

**Goal**: Select target issue and prepare isolated development environment.

**Actions**:
1. Review open issues and select based on priority and invocation args
2. Check existing worktrees to determine if reuse is possible
3. Create an isolated worktree under `.pi/worktrees/`:

```bash
NAME="fix-456-auth-redirect"   # descriptive slug
mkdir -p .pi/worktrees
git worktree add -b "fix/${NAME}" ".pi/worktrees/${NAME}"
# then work inside that path (cd or open files under it)
```

4. Ensure branch naming: `<type>/<issue>-<description>` (see `references/workflow-details.md`)
5. Verify issue acceptance criteria and dependencies
6. Ensure `.pi/worktrees/` is ignored in the tracked `.gitignore` (`git check-ignore -v .pi/worktrees`)

## Phase 2: TDD Implementation

**Goal**: Implement fix using test-driven development.

**Actions**:
1. Plan implementation approach and assess architectural impact
2. Write failing tests that verify issue is resolved (RED)
3. Implement minimal code to make tests pass (GREEN)
4. Refactor while keeping tests green (REFACTOR)
5. Run quality validation for local feedback (see `references/workflow-details.md`). `/skill:create-pr` re-runs the full gate and is the authoritative pre-PR check.

## Phase 3: PR Creation and Cleanup

**Goal**: Hand PR creation to `/skill:create-pr` so the quality gate and review loop run.

**Actions**:
1. Push branch: `git push -u origin <branch-name>`
2. **CRITICAL: Do NOT call `gh pr create` here.** Invoke `/skill:create-pr Closes #<n>` (or `Fixes #<n>`). That skill owns the quality/security gate, auto-closing keywords, non-default-branch warning, and mandatory `/skill:review-pr` handoff. See `references/pr-creation-handoff.md`.
   - Append `--draft` if further feedback is needed
   - Append `--no-monitor` only on explicit user opt-out
   - Append `--auto-merge` only on explicit user opt-in
3. **This skill does not resume here.** `/skill:create-pr` reports the PR URL; `/skill:review-pr` owns the PR through merge. Do NOT wait inline or re-report the URL.

## Phase 4: Post-Merge Cleanup (later turn, fallback)

**Trigger**: PR actually merged — normally after `/skill:review-pr` closeout. That skill owns post-merge cleanup; this phase is a **fallback** when cleanup was skipped ("Don't merge", interrupt, or fresh session). Verify first.

**Actions**:
1. Verify merge: `gh pr view <PR#> --json state -q .state` must be `MERGED`
2. Check `git worktree list`. If review-pr already removed it, skip to `git fetch --prune`
3. If it persists: **confirm still on the issue branch** before removing. If checkout drifted onto `main`/`develop`, stop — removing would delete a long-lived branch.

```bash
# remove worktree (from main repo root)
git worktree remove ".pi/worktrees/<name>"
# or if dirty, ask first via the gh_confirm tool, then discard:
git worktree remove --force ".pi/worktrees/<name>"
git branch -d "<branch>" 2>/dev/null || true
```

4. `git fetch --prune`
5. Document resolution and follow-ups

## References

- **Requirements**: `references/requirements.md`
- **PR Creation Handoff**: `references/pr-creation-handoff.md`
- **Workflow Details**: `references/workflow-details.md`
- **Quality Validation**: `references/quality-validation.md`
- **Examples**: `references/examples.md`
