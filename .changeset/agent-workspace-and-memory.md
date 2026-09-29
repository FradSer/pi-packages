---
"@fradser/pi-subagents": minor
"@fradser/pi-agent-teams": minor
---

Spawned Agents now have their own durable workspace and their own memory. Two of the three requirements behind the subagents / task / agent-teams split; the third, peer coordination, already existed.

**Durable per-Agent workspaces**

Isolation is now the default rather than opt-in. Each Agent gets a linked worktree at `~/.pi/agent/workspaces/<agent>/<project-slug>/`, reused across attempts instead of created per task and deleted on completion.

This is not cosmetic. Pi stores sessions under the agent directory grouped by working directory, and `--continue` reopens the most recent session for the current working directory, so the working path *is* the memory key. The previous per-task worktree was removed on completion, which orphaned its session group every attempt — fragmentation that looks like amnesia and also accumulates storage without bound.

- `worktree: false` in a definition opts out explicitly and shares the leader's tree. A definition that omits the field is now isolated, which is a behaviour change for existing definitions.
- A working directory that is not a git repository, or a repository with no commit, falls back to the shared tree and records a `reason`. Nothing claims the child was isolated when it was not.
- Completion calls `preserveAgentWorkspace`: it commits the attempt's output onto the Agent's durable branch and leaves the directory in place. Only an explicit `releaseAgentWorkspace` removes one, and the branch survives so preserved work stays retrievable.
- A failed spawn removes a workspace only when that spawn created it and nothing ran in it. A reused workspace holds earlier attempts' work and session history and is never discarded.
- The leader now receives a "Workspace preserved" report instead of a worktree diff. A durable branch accumulates across attempts, so a per-attempt diff against a base commit is no longer meaningful.

`src/worktree.ts` is deleted. It implemented the disposable per-task model that `src/workspace.ts` replaces, no consumer imported it, and its three git-mechanics tests tested behaviour the product no longer has; `tests/test_agent_workspace.py` covers the durable model instead, including preserve-commits-and-keeps-directory, release-removes-only-on-explicit-request, and a-failed-spawn-never-removes-a-reused-workspace.

**A blocker this surfaced, and its fix.** Pi's `defaultProjectTrust` setting is `"ask"`, and a freshly created directory is an untrusted project. A child started in a new workspace therefore blocked forever waiting for a trust decision that `--mode rpc` has no UI to make — the spawn succeeded, the process lived, and nothing was ever reported. `spawnResident` gained `approveProjectTrust`, which passes `-a`, and `agent-teams` sets it only when the workspace is one the harness created. Approving is correct there and only there: the workspace is a linked checkout of a repository the leader session already trusts. A child sharing the caller's directory inherits that directory's existing trust record and is deliberately not force-approved, which is also why the shared path never showed this bug.

**Working memory is Pi's own session storage**

No session scheme is implemented here, on purpose. `spawnResident` gained `session: "none" | "persist" | "resume"`:

- `persist` for a newly created workspace, so Pi stores the session under that Agent's own working path.
- `resume` (`--continue`) for a reused workspace, reopening the Agent's working memory.
- `none` (`--no-session`) when the child shares the leader's tree, because persisting there would put the child's turns into the user's own session group.

A supplied fork `context` still wins: `--session` cannot be combined with `--continue`, and a fork is a new session by definition. This reuses Pi's compaction, branching (`/tree`, `/fork`, `/clone`), `/resume` picker, and `/export` rather than rebuilding them, and no `--session-dir` is introduced to compete with Pi's storage.

**Agent Memory**

A persisted Agent can own a capability record at `~/.pi/agent/agents/<name>/`, user scope only. There is no per-project Agent Memory: a project-scoped capability folder cannot serve a cross-project Agent, and an existing project directive already requires local memory to live under `~/.pi/`.

- Opt-in through `memory: true` in the definition. A session-scoped (Temporary) Agent resolves to `memory: false` whatever it asked for; Agent Promotion is what creates a folder, and that is a separate decision from approving any entry.
- Content is capability, not project fact. Injection follows ADR-0003: a bounded index of filenames and one-line descriptions, never entry bodies, with the root declared once and all content marked as untrusted reference data. Descriptions are shortened with a visible marker before entries are dropped, and dropped entries are counted and reported rather than silently lost.
- Writing is gated by the tool grant. A `bash` or `powershell` grant counts as write-capable because a shell can write; a read-only Agent is told to report the lesson in its result instead. Entry names cannot escape the memory root, an oversized body is refused rather than truncated, and an entry without a description is refused because the description is what the index carries.
- `MEMORY.md` is derived from the folder on every write, so it cannot drift from what it describes.
- A generalizing lesson is recorded as a **Memory Proposal** under `proposals/`, never merged directly. Review and merge stay with `pi-continual-learning`; absent that package proposals accumulate for human review, which is a safe degradation. A read-only Agent may still propose, because proposing is reporting.

**Two worker extensions in one child**

`agent-teams` now contributes `[SUBAGENT_WORKER_EXTENSION_PATH, WORKER_EXTENSION_PATH]` and the union of both capability sets. `--extension` is repeatable and `--no-extensions` still loads explicit paths, so neither package has to know about the other. This is the first real use of the contributed-extension seam, and it adds one tool, `agent_memory`, registered by `pi-subagents` and refused with a clear reason when the Agent has no memory folder or a read-only grant.

The subagent extension reads `PI_SUBAGENT_ROLE`, `PI_SUBAGENT_TOOLS`, and `PI_SUBAGENT_MEMORY` — named for its own package rather than reusing `PI_TEAMMATE_*`, so the execution layer never has to learn the coordination package's vocabulary.

**Not included**

Kernel write confinement (Seatbelt/Landlock sandbox profiles), tool and usage budgets, the nesting depth guard, `Handoff` as an atomic transfer, and a durable `Agent Inbox`. A linked worktree separates the filesystem; it does not confine what a `bash` grant can touch, and no confinement is claimed.

Contracts: `packages/subagents/features/agent-memory.feature`, `packages/subagents/features/agent-workspace.feature`.
