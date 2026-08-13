# GitHub — Resolve Issues procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/github` menu ("Resolve issue(s)") via `pi.sendUserMessage` — it is not a
> skill and the menu delivers it inline. `{{PKG_DIR}}` is
> substituted with the package dir at send time.

Execute issue resolution workflow using isolated worktrees, TDD methodology, and agent collaboration.

## Pi tools

Use only Pi built-ins: `bash` (for `gh` / `git` / worktrees), `read`, `edit`, `write`.

Worktrees live under `.pi/worktrees/` (rewritten by the `git` package extension when present). There is no EnterWorktree / ExitWorktree tool — use `git worktree` via `bash`.

## Invocation args

Arguments come from the `/github` command line (e.g. `/github resolve-issues 456`) — the issue number or description. Otherwise select from open issues.

## Bootstrap (run with bash)

```bash
git status
git branch --show-current
git worktree list
gh issue list --state open --limit 10
gh auth status
```

## Requirements Summary

Use isolated worktrees to avoid disrupting main development. Follow TDD cycle (red → green → refactor). Reference issues in commits using auto-closing keywords. See `{{PKG_DIR}}/references/resolve-issues/requirements.md`.

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

4. Ensure branch naming: `<type>/<issue>-<description>` (see `{{PKG_DIR}}/references/resolve-issues/workflow-details.md`)
5. Verify issue acceptance criteria and dependencies
6. Ensure `.pi/worktrees/` is ignored in the tracked `.gitignore` (`git check-ignore -v .pi/worktrees`)

## Phase 2: TDD Implementation

**Goal**: Implement fix using test-driven development.

**Actions**:
1. Plan implementation approach and assess architectural impact
2. Write failing tests that verify issue is resolved (RED)
3. Implement minimal code to make tests pass (GREEN)
4. Refactor while keeping tests green (REFACTOR)
5. Run quality validation for local feedback (see `{{PKG_DIR}}/references/resolve-issues/workflow-details.md`). The create-pr procedure re-runs the full gate and is the authoritative pre-PR check.

## Phase 3: PR Creation and Cleanup

**Goal**: Hand PR creation to the create-pr procedure so the quality gate and review loop run.

**Actions**:
1. Push branch: `git push -u origin <branch-name>`
2. **CRITICAL: Do NOT call `gh pr create` here.** Continue with the create-pr procedure (`{{PKG_DIR}}/procedures/create-pr.md`) with `Closes #<n>` (or `Fixes #<n>`). That procedure owns the quality/security gate, auto-closing keywords, non-default-branch warning, and mandatory review-pr handoff. See `{{PKG_DIR}}/references/shared/pr-creation-handoff.md`.
   - Append `--draft` if further feedback is needed
   - Append `--no-monitor` only on explicit user opt-out
   - Append `--auto-merge` only on explicit user opt-in
3. **This workflow does not resume here.** The create-pr procedure reports the PR URL; the review-pr procedure owns the PR through merge. Do NOT wait inline or re-report the URL.

## Phase 4: Post-Merge Cleanup (later turn, fallback)

**Trigger**: PR actually merged — normally after the review-pr closeout. That workflow owns post-merge cleanup; this phase is a **fallback** when cleanup was skipped ("Don't merge", interrupt, or fresh session). Verify first.

**Actions**:
1. Verify merge: `gh pr view <PR#> --json state -q .state` must be `MERGED`
2. Check `git worktree list`. If the review-pr closeout already removed it, skip to `git fetch --prune`
3. If it persists: **confirm still on the issue branch** before removing. If checkout drifted onto `main`/`develop`, stop — removing would delete a long-lived branch.

```bash
# remove worktree (from main repo root)
git worktree remove ".pi/worktrees/<name>"
# or if dirty, ask the user in the conversation first, then discard:
git worktree remove --force ".pi/worktrees/<name>"
git branch -d "<branch>" 2>/dev/null || true
```

4. `git fetch --prune`
5. Document resolution and follow-ups

## References

- **Requirements**: `{{PKG_DIR}}/references/resolve-issues/requirements.md`
- **PR Creation Handoff**: `{{PKG_DIR}}/references/shared/pr-creation-handoff.md`
- **Workflow Details**: `{{PKG_DIR}}/references/resolve-issues/workflow-details.md`
- **Quality Validation**: `{{PKG_DIR}}/references/shared/quality-validation.md`
- **Examples**: `{{PKG_DIR}}/references/shared/examples.md`
