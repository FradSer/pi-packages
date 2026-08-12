---
name: create-issues
description: Creates GitHub issues following test-driven development principles and proper labeling conventions. Use when the user asks to "create an issue", "file a bug", or needs to document new requirements, epics, or PR-scoped tasks.
---

# Create GitHub Issues

Execute automated GitHub issue creation workflow following TDD principles and conventional commit standards.

## Pi tools

Use only Pi built-ins: `bash` (for `gh` / `git`), `read`, `edit`, `write`. No Claude-only tools.

## Invocation args

When invoked as `/skill:create-issues <args>`, the text after the skill block is the user-provided arguments (issue description(s)). Parse that trailing text — Pi does not expand `$ARGUMENTS` placeholders inside skill bodies.

## Bootstrap (run with bash)

```bash
git status
git branch --show-current
gh issue list --state open --limit 10
gh auth status
```

## Requirements Summary

Follow TDD principles, conventional commits, and protected branch workflows. Use proper labels, auto-closing keywords, and atomic commits. See `references/requirements.md` for complete standards.

## Phase 1: Repository Analysis

**Goal**: Assess repository state, detect templates, and determine issue scope and type.

**Actions**:
1. Analyze current branch (main/develop vs PR branch)
2. Review open issues to identify duplicates or related work
3. Check for contributing guidelines (`CONTRIBUTING.md`) and follow its requirements
4. Detect issue templates in `.github/ISSUE_TEMPLATE/`
5. If templates exist: select appropriate template using `gh issue create --list`
6. Determine issue type (epic, PR-scoped, or review) from the user-provided arguments
7. Apply branch-based decision logic from `references/decision-logic.md`

See `references/repository-templates.md` for template detection and compliance details.

## Phase 2: Issue Creation

**Goal**: Create GitHub issue with proper structure, labels, and links.

**Actions**:
1. Create or verify required priority labels exist (see `references/decision-logic.md` for commands)
2. Draft issue following structure requirements in `references/issue-structure.md`
3. Apply appropriate labels (priority, type) using `--label`
   - Assign owners using `--assignee`
   - Link milestones using `--milestone` or projects using `--project` if requested
4. Add auto-closing keywords if PR-scoped issue (NOT for epics)
   - **CRITICAL: auto-closing keywords only fire when the PR merges into the repository's default branch.** If the issue will be resolved by a PR targeting a non-default branch, warn the user that the issue will NOT close automatically and must be closed manually — see `references/auto-closing-keywords.md`
5. Link to related issues or epics if applicable

## Phase 3: Documentation and Handoff

**Goal**: Document decisions and communicate follow-up actions.

**Actions**:
1. Document branch strategy decision and rationale
2. Report created issue number and URL to user
3. If on PR branch and blocking: add detailed comment to PR instead of creating issue
4. Share next steps (create PR, assign to team member, etc.)

## References

- **Requirements**: `references/requirements.md`
- **Decision Logic**: `references/decision-logic.md`
- **Issue Structure**: `references/issue-structure.md`
- **Auto-Closing Keywords**: `references/auto-closing-keywords.md`
- **Repository Templates**: `references/repository-templates.md`
- **Examples**: `references/examples.md`
