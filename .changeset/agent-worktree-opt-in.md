---
"@fradser/pi-subagents": minor
"@fradser/pi-agent-teams": minor
---

Agent startup is no longer bound to a Git worktree. An Agent starts in the leader's working directory unless its definition declares `worktree: true`.

**@fradser/pi-subagents**

`resolveIsolation` in `src/agents.ts` now resolves an absent `worktree` field to `shared` rather than `isolated`, and the two default sites follow it: `normalizeAgentInput` defaults a generated role to `worktree: false`, and `loadDir` reads `worktree: true` as the only opt-in instead of `worktree: false` as the only opt-out. `worktree: false` stays valid and means the same thing it always did.

The default was the wrong way round. Most Agents only read, or edit files nobody else is working on, and a linked worktree bought them nothing but a full checkout of the repository — `~/.pi/agent/workspaces` had reached 1.0 GB, most of it under `*-review` and `*-reviewer` role names. It also cost correctness: a reused workspace is never synchronized with the leader's tree or HEAD. `ensureAgentWorkspace` returns a usable worktree as-is, the `agent/<name>` branch is cut once at first use, and nothing in either package fetches, merges, or resets it — so a role pointed at a workspace to read the current state read the state of its own first spawn. The leader's uncommitted changes were never in there at all.

`worktree: true` keeps everything it had: a durable per-Agent workspace, `session: "persist"`/`"resume"`, `setTaskContext` recording the path, and completion committing onto the branch. Use it for a role whose output must not share files with the leader or with other Agents running at once. The one thing to know is that a reused workspace is still pinned to first-use HEAD, so point a role at a worktree for its own output, not for the leader's state.

Write isolation remains unimplemented and unclaimed. A linked worktree separates the filesystem; a shared tree separates nothing at all.

**@fradser/pi-agent-teams**

`team-machine.ts` passes `agent.isolation` through unchanged, so the spawn path follows the role. The `liveWorkspaces` map, the `session` policy, `approveProjectTrust`, `setTaskContext`, and the completion-time `preserveAgentWorkspace` call were all already conditional on the worktree actually being provisioned, so a shared child inherits the leader's directory and its existing trust record instead of being force-approved for a directory this harness never created.

A shared child runs with `--no-session`, because a child persisting into the leader's own session group would put its turns among the user's. That is the real cost of not giving it a directory of its own: a shared child is not resumable after a crash or a Pi restart. It is the pre-existing `worktree: false` behavior, unchanged.

Contract: `packages/subagents/features/agent-workspace.feature`.
