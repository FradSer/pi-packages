---
name: public-memory-project-root
description: Public .memory mirrors are only for canonical Git worktree roots; harness memory remains authoritative for every cwd scope
type: project
---

## Why

The canonical memory store is the full harness scope at `~/.pi/agent/memory/<scope-key>/`. A public `.memory/` is an optional, project-local synchronization target, not a second universal memory root. Parent workspaces, configuration directories, and repository subdirectories must not accumulate public mirrors simply because a session starts there.

## How to apply

Enable `<cwd>/.memory/` only when `git -C <cwd> rev-parse --show-toplevel` resolves to the canonical cwd itself. Do not hardcode paths such as `~/.pi` or a particular workspace parent: their exclusion follows from not being Git worktree roots. Keep the general exclusion for the agent configuration directory itself, because it is harness configuration rather than a project. When the public mirror is disabled, consolidation and injection use only the harness scope and never create `.memory/`.

## Related

[[project_continual_learning_autonomous_consolidation]]
