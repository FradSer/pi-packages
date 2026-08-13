# Git Plugin

GitFlow workflow automation for feature, hotfix, and release branches with post-finish cleanup. Native `/git` command menu — **no skill surface**.

## Features

- **GitFlow Branch Lifecycles**: Standardized `start` and `finish` workflows for `feature`, `hotfix`, and `release` branches.
- **Full-Auto Inference**: Derives branch names or SemVer increments automatically when arguments are omitted.
- **Strict Invariants**: Pre-flight clean tree checks, testing requirements, changelog updates, and post-finish branch/worktree cleanup.

## Usage

Type `/git` to open the native menu:

```
GitFlow workflows:
❯ 1. Start feature
  2. Start hotfix
  3. Start release
  4. Finish feature
  5. Finish hotfix
  6. Finish release
  7. Commit changes        (standard Conventional Commit)
  8. Commit and push       (standard Conventional Commit + push)
```

Shorthand — pass a workflow keyword on the command line to skip the menu:

```bash
/git start-feature dark-mode       # create feature/dark-mode from develop
/git start-hotfix                  # auto-bump patch, create hotfix/<version> from main
/git start-release 1.3.0           # create release/1.3.0 from develop
/git finish-feature                # tests, changelog, merge into develop, cleanup
/git finish-release                # tests, changelog, merge to main & develop, tag, GitHub Release
/git commit                        # standard Conventional Commit
/git commit-and-push
```

Each selection embeds the full procedure (`procedures/*.md`) into a follow-up
message via `pi.sendUserMessage` — the start/finish procedures point at the
shared pipelines in `references/` (`gitflow-start-pipeline.md`,
`gitflow-finish-pipeline.md`). Natural-language phrasing of a branch lifecycle
is handled by the agent following those procedures.

## Reference Documentation

- `references/gitflow-start-pipeline.md` — Shared start pipeline logic & version inference
- `references/gitflow-finish-pipeline.md` — Shared finish pipeline logic (test, changelog, merge, release, cleanup)
- `references/invariants.md` — Pre-operation checks and testing invariants
- `references/cleanup.md` — Post-finish workspace & remote cleanup
- `references/coauthor-attribution.md` — Conventional commit standards & co-author trailers

## Files

```
git/
├── extensions/
│   ├── menu.ts               # /git command menu
│   ├── worktree.ts           # rewrites git worktree add into .pi/worktrees/
│   └── risky-gate.ts         # tool_call hook: model-generated option dialog for destructive git commands
├── procedures/
│   ├── start.md              # GitFlow start ({{WORKFLOW_TYPE}} substituted by the menu)
│   ├── finish.md             # GitFlow finish ({{WORKFLOW_TYPE}} substituted by the menu)
│   ├── commit.md             # standard Conventional Commit
│   └── commit-and-push.md    # standard Conventional Commit + push
└── references/               # shared pipelines, invariants, cleanup, changelog rules
```
