---
name: project-agent-worktree-opt-in
description: Agent startup is not bound to a Git worktree; a role opts in with worktree: true, and sharing the leader's tree is the default because an isolated workspace is never synchronized with the leader's state.
type: project
---

# Agent startup is not bound to a worktree

**Why:** The default was inverted. Most Agents only read, or edit files nobody
else is working on, and a linked worktree bought them nothing but a full checkout
of the repository — `~/.pi/agent/workspaces` reached 1.0 GB, most of it under
`*-review` and `*-reviewer` role names. Worse, a reused workspace is never
synchronized with the leader's tree or HEAD: `ensureAgentWorkspace` returns a
usable worktree as-is, the `agent/<name>` branch is cut once at first use, and
nothing in either package fetches, merges, or resets it. A role pointed at a
workspace to read the current state read the state of its own first spawn, and
the leader's uncommitted changes were never in there at all.

**How to apply:** `resolveIsolation` resolves an absent `worktree` field to
`shared`; only `worktree: true` asks for a linked worktree. Reach for it when a
role must not share files with the leader or with other Agents running at once —
not to keep a role's reads fresh, which isolation does not deliver. A shared
child inherits the leader's directory and its existing trust record, and runs
with `--no-session`, because a child persisting into the leader's own session
group would put its turns among the user's. That is the cost of not giving it a
directory of its own: a shared child is not resumable after a crash or a Pi
restart.

Write isolation stays unimplemented and unclaimed. A linked worktree separates
the filesystem; a shared tree separates nothing at all.

Contract: `packages/subagents/features/agent-workspace.feature`.