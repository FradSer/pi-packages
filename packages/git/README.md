# Git Plugin

GitFlow workflow automation for feature, hotfix, and release branches with post-finish cleanup.

## Features

- **GitFlow Branch Lifecycles**: Standardized `start` and `finish` workflows for `feature`, `hotfix`, and `release` branches.
- **Full-Auto Inference**: Derives branch names or SemVer increments automatically when arguments are omitted.
- **Strict Invariants**: Pre-flight clean tree checks, testing requirements, changelog updates, and post-finish branch/worktree cleanup.

## Available Skills

| Skill | Intent / Trigger | Description |
|-------|------------------|-------------|
| `/commit` | Commit changes | Stages files and creates a Conventional Commit via standard `git` |
| `/commit-and-push` | Commit and push | Creates a Conventional Commit and pushes current branch to origin |
| `/start-feature` | Start a new feature | Creates `feature/<name>` from `develop` |
| `/finish-feature` | Complete a feature | Tests, updates changelog, merges into `develop`, and cleans up |
| `/start-hotfix` | Start a production fix | Auto-bumps patch version, creates `hotfix/<version>` from `main` |
| `/finish-hotfix` | Complete a hotfix | Tests, updates changelog, merges to `main` & `develop`, tags, and cleans up |
| `/start-release` | Start a version release | Auto-derives version bump, creates `release/<version>` from `develop` |
| `/finish-release` | Complete a release | Tests, updates changelog, merges to `main` & `develop`, tags, creates GitHub Release, and cleans up |

## Reference Documentation

- `references/gitflow-start-pipeline.md` — Shared start pipeline logic & version inference
- `references/gitflow-finish-pipeline.md` — Shared finish pipeline logic (test, changelog, merge, release, cleanup)
- `references/invariants.md` — Pre-operation checks and testing invariants
- `references/cleanup.md` — Post-finish workspace & remote cleanup
- `references/coauthor-attribution.md` — Conventional commit standards & co-author trailers
