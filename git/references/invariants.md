# GitFlow Plugin Invariants

Core rules enforced by this plugin.

## Pre-operation Checks

Before any start or finish operation:
- Working tree must be clean (`git status --porcelain` is empty)

Finish operations additionally require:
- Current branch must match the operation type (`feature/*`, `hotfix/*`, `release/*`)

Start operations create the branch from its base (`develop` for feature and release, `main` for hotfix), so the current branch is NOT required to match the operation type — only the clean-tree check applies.

## Worktree Placement Invariants

When creating new Git worktrees:
- All new worktrees MUST be created inside `.pi/worktrees/<name>` (e.g. `.pi/worktrees/feature-foo`).
- The `git` extension automatically intercepts and rewrites `git worktree add` commands to ensure target paths are placed inside `.pi/worktrees/`.
- Ensure `.pi/worktrees` is included in `.gitignore` if not already present.

## Testing Requirements

Before finishing any branch:
- Run available test commands (`npm test`, `pytest`, `cargo test`, etc.)
- Exit if tests fail; user must fix issues first

## Changelog Generation

When updating CHANGELOG.md during finish operations:

**Core principle:** Include commits representing **user-facing changes** since the previous version tag.

**Include types:**
- feat, fix, refactor, docs, perf
- Security-related changes
- Deprecation and removal notices

**Exclude types:**
- chore, build, ci, test
- Merge commits and release commits

See `changelog-generation.md` for complete mapping rules.

## Committing

All commits go through the `/commit` skill with a Conventional Commit intent (`feat`, `fix`, `chore`, `docs`, etc.). The working tree is verified clean before start/finish, so the skill stages and commits the intended files atomically.

## Cleanup

After every `finish` operation, run the cleanup procedure in `cleanup.md`:

- Prune stale remote-tracking branches (`git fetch --prune`)
- Prune stale worktrees (`git worktree prune`)
- Confirm the just-finished branch is gone locally and on origin
- Sweep other already-merged `feature/*`, `hotfix/*`, `release/*` branches

Never delete `main`, `develop`, `master`, `production`, or the current branch. Prefer `git branch -d` over `-D` for the merged-branch sweep.

## External References

- [git-flow-next Documentation](https://git-flow.sh/docs/)
- [git-flow-next Commands](https://git-flow.sh/docs/commands/)