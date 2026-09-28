# @fradser/pi-subagents

The subagent execution layer: what it takes to spawn one Agent child process,
give it an identity, a workspace, a context, and an environment it can be
trusted with, and get its reports back.

This is an internal workspace runtime library in the `pi-packages` monorepo, in
the same category as `@fradser/pi-kit`. It declares no `pi` manifest key and is
not installed as a Pi extension on its own. `@fradser/pi-agent-teams` consumes
it; the planned `@fradser/pi-tasks` package does not.

## Boundary

Everything here describes **one child**. Nothing here knows about Work Items,
peer messaging, task boards, or team presence.

| Module | Owns |
| --- | --- |
| `src/agents.ts` | Agent definitions: discovery scopes, frontmatter, inline session roles, explicit persistence |
| `src/spawner.ts` | Resident child spawn in RPC mode, the control stream, JSONL stream parsing, termination, and the grantable tool universe |
| `src/child-env.ts` | The spawn environment policy: what a child inherits from the leader |
| `src/work-context.ts` | Snapshotting a live session and materializing it as a child session file |
| `src/leader-reports.ts` | The child-to-parent report record and its rendering shape |
| `src/worker-tools.ts` | The canonical pi built-in tool ids a bare child can be granted |
| `src/workspace.ts` | Durable per-Agent workspaces and their preserve/release lifecycle |
| `src/memory.ts` | Agent Memory: the Agent's own capability record, its bounded index, and Memory Proposals |
| `src/worker-extension.ts` | This package's worker extension, contributed to a child with `-e` |
| `src/types.ts` | `WorkerUsage` |

Coordination vocabulary deliberately stays out. A consumer that installs only
this layer gets a spawnable child with pi built-ins and nothing else.

## Contributed capabilities

The spawner hardcodes no worker extension path and no capability tool set. Both
are supplied per spawn:

```ts
spawnResident({
  workerName: "reviewer",
  extensions: [WORKER_EXTENSION_PATH],       // the consumer's own worker entry
  capabilityTools: ["agent_event", "work"],  // what that extension registers
  tools: ["read", "bash"],                   // the role's grant
  ...
});
```

`--extension` is repeatable and `--no-extensions` still loads explicit paths, so
several packages can each contribute their own worker extension to one child.
`resolveWorkerTools`, `workerToolUniverse`, and `unknownWorkerTools` all take the
contributed set, and declaring capability tools with no extension to register
them is refused rather than silently granting ids the child's `--tools` filter
would drop.

## Agent Memory

A persisted Agent can have its own capability record at
`~/.pi/agent/agents/<name>/`, at user scope only. There is deliberately no
per-project Agent Memory: a project-scoped capability folder cannot serve a
cross-project Agent, and an existing project directive already requires local
memory to live under `~/.pi/`.

It is opt-in through `memory: true` in the definition, and a session-scoped
(Temporary) Agent never gets one — Agent Promotion creates the folder, and that
is a separate decision from approving any individual entry.

Content is capability, not project fact: methods, judgment criteria, operating
patterns. Project facts, decisions, and history belong to Project Memory, which
`pi-continual-learning` owns.

Injection follows ADR-0003 — a bounded index of filenames and one-line
descriptions, never entry bodies; the Agent reads a full entry with `read` when
the task needs it. Writing is gated by the tool grant, and a `bash` grant is not
read-only because a shell can write. An Agent generalizing a lesson records a
**Memory Proposal**; review and merge stay with `pi-continual-learning`.

## Working memory

This package implements no session scheme. Pi stores sessions grouped by working
directory and `--continue` reopens the most recent one for that directory, so the
working path *is* the memory key. A durable per-Agent workspace is what makes that
usable: `session: "persist"` for a new workspace, `"resume"` for a reused one, and
`"none"` when the child shares the leader's tree — persisting there would put the
child's turns into the user's own session group.

Completion therefore never removes a workspace. It commits the attempt's output
onto the Agent's durable branch and leaves the directory in place, which is both
the Agent's home and its Pi session group.

Write isolation is a separate, unimplemented layer. A linked worktree separates
the filesystem; it does not confine what a `bash` grant can touch. No kernel write
confinement is claimed.

## Child environment

A child receives an explicit allowlisted environment, never the leader's complete
one. `PI_CODING_AGENT_DIR` passes through so the child resolves the same
`auth.json` and `models.json`; `PI_TEAMMATE_ENV_ALLOW` opts additional exact
names back in. This is leakage defense, not containment — a child granted `bash`
can still read credential files from disk. See `src/child-env.ts`.

## Status

Extracted from `@fradser/pi-agent-teams` as part of splitting that package into
subagents / task / agent-teams. The design and remaining sequence are in
`docs/spec-agent-teams-three-package-split.md` at the repository root.

This package now owns Agent Memory and durable per-Agent workspaces as well as
the execution layer, and contributes its own worker extension to a spawned child
alongside the consumer's.

Still to come: the `agent` tool and the roster/incarnation state, which need the
`ChildHost` seam before they can move. Until then this package is a library, not
an installable Pi extension.

## License

MIT
