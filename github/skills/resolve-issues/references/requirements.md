# Requirements

## Worktree and TDD Workflow

- Use the mkdir -p .pi/worktrees && git worktree add .pi/worktrees/under `.pi/worktrees/`/`git worktree remove` under `.pi/worktrees/`s for isolated development.
- Apply a TDD cycle (red → green → refactor) with appropriate sub-agent support.
- Reference resolved issues in commits and PR descriptions using auto-closing keywords — only fire on the default branch; see `references/auto-closing-keywords.md`.
- Delegate PR creation to `/skill:create-pr` (the plugin's only PR-creating path) — see `references/pr-creation-handoff.md` for the full contract and protected-PR workflow.
