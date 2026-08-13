# GitHub — Create PR procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/github` menu ("Create pull request") via `pi.sendUserMessage` — it is not
> a skill and the menu delivers it inline. `{{PKG_DIR}}` is
> substituted with the package dir at send time.

Execute the automated PR creation workflow with comprehensive quality validation and security scanning.

## Pi tools

Use only Pi built-ins: `bash` (for `gh` / `git` / project checks), `read`, `edit`, `write`.

## Invocation args

Arguments come from the `/github` command line (e.g. `/github create-pr Closes #456 --draft`). May include, in any combination:

- Issue reference (`Closes #456`, `Fixes #12`, or bare `#456`)
- Free-text description
- `--draft`
- `--no-monitor` (Phase 4 opt-out)
- `--auto-merge` (passthrough to the review-pr procedure)

Strip flags before treating the remainder as description/issue text.

## Bootstrap (run with bash)

```bash
git status
git branch --show-current
git log --oneline -5
gh auth status
git diff --stat HEAD~1..HEAD 2>/dev/null || true
```

## Requirements Summary

Ensure repository readiness with clean state and authentication. Complete all quality checks (lint, test, build, security) before PR creation. Link related issues with auto-closing keywords and apply accurate labels. See `{{PKG_DIR}}/references/create-pr/requirements.md`.

## Phase 1: Validation and Analysis

**Goal**: Validate repository state, analyze changes, detect templates, and identify blockers.

**Actions**:
1. Verify GitHub authentication
2. Check branch status and unpushed commits
3. Analyze commit history for conventional commit compliance
4. Identify changed files and determine PR scope
5. Check for contributing guidelines (`CONTRIBUTING.md`)
6. Detect PR templates (`.github/PULL_REQUEST_TEMPLATE.md` or root/docs locations)
7. Detect potential blockers (merge conflicts, missing tests, etc.)

See `{{PKG_DIR}}/references/shared/repository-templates.md`.

## Phase 2: Quality and Security Checks

**Goal**: Execute comprehensive quality validation and security scanning.

**Actions**:
1. Run project-specific quality checks (see `{{PKG_DIR}}/references/shared/quality-validation.md`)
2. Execute security scanning for sensitive files and hardcoded secrets
3. Validate commit message format against standards
4. If checks fail: follow `{{PKG_DIR}}/references/create-pr/failure-resolution.md`
5. Re-run all checks until passing

## Phase 3: PR Assembly and Creation

**Goal**: Create pull request with proper structure, metadata, and links.

**Actions**:
1. **Consume invocation args before deriving anything.** Issue references go into the PR body verbatim. Free-text becomes title/What-Why basis. Flags stay flags.
2. Identify and link any further related issues with `gh`
3. Generate PR title (≤70 chars, imperative, no emojis)
4. Assemble PR body following `{{PKG_DIR}}/references/create-pr/pr-structure.md`
5. Apply automated labels based on file changes
6. **CRITICAL: auto-closing keywords only fire when the PR merges into the repository's default branch.** If targeting a non-default branch (e.g. `develop`), warn the user — see `{{PKG_DIR}}/references/shared/auto-closing-keywords.md`
7. Create PR with `gh pr create`
   - Use `--draft` when requested or when incomplete
   - Set `--reviewer` / `--assignee` when requested
8. Report final PR URL. Do NOT run foreground `gh pr checks --watch` — Phase 4 owns CI watch.
9. **CRITICAL: Proceed to Phase 4** unless args contain `--no-monitor` or the user opts out.

## Phase 4: Post-PR Handoff (default on)

**Trigger**: Default — hand off unless `--no-monitor` or explicit user opt-out.

**Goal**: Delegate CI monitoring and reviewer-comment triage.

**Action**: After the PR is created, continue with the review-pr procedure (`{{PKG_DIR}}/procedures/review-pr.md`) for PR `<PR#>` (append `--auto-merge` only when the user explicitly set it). Load and follow that procedure: baseline review, poll loop via `{{PKG_DIR}}/scripts/review-loop.sh` (bundled in the `@fradser/github` package), triage, fix, commit+push via the commit-and-push procedure, merge decision, closeout.

**CRITICAL: this procedure is the package's only PR-creating path.** Other workflows (e.g. resolve-issues) must delegate here instead of calling `gh pr create` themselves. See `{{PKG_DIR}}/references/shared/pr-creation-handoff.md`. Do not add a bypass.

## References

- **Requirements**: `{{PKG_DIR}}/references/create-pr/requirements.md`
- **Repository Templates**: `{{PKG_DIR}}/references/shared/repository-templates.md`
- **Quality Validation**: `{{PKG_DIR}}/references/shared/quality-validation.md`
- **PR Structure**: `{{PKG_DIR}}/references/create-pr/pr-structure.md`
- **Auto-Closing Keywords**: `{{PKG_DIR}}/references/shared/auto-closing-keywords.md`
- **PR Creation Handoff**: `{{PKG_DIR}}/references/shared/pr-creation-handoff.md`
- **Failure Resolution**: `{{PKG_DIR}}/references/create-pr/failure-resolution.md`
- **Examples**: `{{PKG_DIR}}/references/shared/examples.md`
