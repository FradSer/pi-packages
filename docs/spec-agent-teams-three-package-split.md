# Specification: Split Agent Teams into subagents / task / agent-teams

## Problem Statement

`@fradser/pi-agent-teams` (v0.10.0) is one package that simultaneously owns four
concerns: child-process spawning, Work Item state, peer communication, and the
leader console. Its `src/team-machine.ts` is 2435 lines and every concern
touches it. Three consequences are already visible:

1. **A subagent has no memory.** `spawnResident` launches
   `pi --mode rpc --no-extensions --extension <own index.ts>` with
   `--no-session` (or a throwaway temp session for `fork`). The child therefore
   loads no memory extension, persists no history, and dies with its attempt.
   This directly contradicts `CONTEXT.md`, which defines an **Agent** as "a
   persisted AI coworker with a stable identity, capability-focused Agent
   Memory, and work history that may span projects", and contradicts ADR-0001,
   which states the agent-first model "replaces the session-bound
   teammate/process model".
2. **Task context is not a first-class object.** A Work Item stores
   `description`/`verify`/`resources`/`result`, but the context a successor
   needs is rebuilt ad hoc: `snapshotWorkContext` exists only for `fork`, and
   `buildSuccessorHandoff` is prose concatenation, not a bounded handoff
   artifact.
3. **Nothing is reusable alone.** A user who wants one subagent with memory, or
   one task board for their main session, must install the whole team runtime.

`packages/agent-teams/features/agent-memory-abstraction.feature` and
`features/unified-work-interface.feature` were both tagged
`@design @unimplemented`. The split is the vehicle that makes them
implementable in bounded increments. `agent-memory-abstraction.feature` has
since been deleted: `packages/subagents/features/agent-memory.feature` states the
same content contract as executable scenarios, and the proposal review and merge
process it referenced belongs to `pi-continual-learning`, not to this package.

## Reference comparison: `nicobailon/pi-subagents`

Reviewed at commit `2f37edb`, package version `0.71.0`.

| Dimension | `pi-subagents` | `agent-teams` |
| --- | --- | --- |
| Child model | In-host `AgentSession` (foreground) / detached runner (background) | Separate `pi --mode rpc` process |
| Tool surface | One large `subagent` tool (~30 actions) + `subagents_enable` + `bg_wait` + supervisor pair | Three orthogonal tools: `agent`, `work`, `agent_event` + `/agent-teams` |
| Context | `fresh` / `fork` via `createBranchedSession`; strips signed `thinking` blocks | `fresh` / `fork` via `snapshotWorkContext` + temp session file; default `--no-session` |
| **Memory** | **Yes.** Per-agent `memory` frontmatter; first 200 lines / 16 KiB of `MEMORY.md` injected into the child system prompt; write-capable agents append dated entries; read-only agents get a read-only block; traversal and symlink escape rejected | **None** |
| Task tracking | Heavy: `status.json`, `events.jsonl`, `run-history.jsonl`, missions, schedules, workflows, lanes | Converged: single-writer board file + atomic claim/submission intent dirs + `dependsOn`/`resources`/`verify` |
| **Child↔child** | **None.** Parent-mediated only: `contact_supervisor` up, `reply`/steer down; scoped to the exact spawning session | **Yes.** Real peer inboxes (`inbox-*.jsonl`), harness routing, `spawnId`-bound delivery |
| Isolation | Worktree, tool allowlist, `excludeTools`, capability ceilings, depth guard (default 2) | Worktree, tool allowlist (8 built-ins + capability tools); no nesting |
| Budgets | `toolBudget`, `usageBudget` | None |
| Completion | Evidence closes work, fail-closed | Attempt-bound authority + verify gate; automatic and explicit submission share one acceptance pipeline |
| TUI | Persistent FleetView + `/subagents-fleet` full-screen + inline streaming | Passive widget + `/agent-teams` console + pi-kit lifecycle rows |
| Packaging | `private: true`, 16 subpath exports, all core peers optional | Single package, `files: [index.ts, src, references, .memory]` |

**Judgement: the two are complementary, not competing.** `pi-subagents` is
strong on *single-subagent capability* (memory, worktree, workflow, mission,
budgets, depth guard, FleetView) and explicitly weak on *peer collaboration*
(no child↔child channel exists). `agent-teams` is strong on the *collaboration
contract* (P2P mail, contested board claims, attempt-bound authority, verify
gate) and weak on the *individual subagent*. The requested three-way split falls
exactly on those seams — and independently matches `pi-subagents`' own internal
layering (`agents/`, `runs/`, `missions/`, `intercom/`), which is evidence the
cut is natural rather than arbitrary.

Two ideas are worth borrowing explicitly, and two are worth refusing:

- Borrow: **per-agent memory injection with a bounded budget and a
  write-capability gate** (design input for Package 1).
- Borrow: **tool/usage budgets and a nesting depth guard** (currently absent
  from `agent-teams`; belongs in Package 1).
- Refuse: **one mega-tool with ~30 actions**. ADR-aligned `agent-teams` already
  converged on three orthogonal tools; `features/unified-work-interface.feature`
  makes "each operation has one owner" an explicit rule.
- Refuse: **in-process `AgentSession` children**. Separate processes are what
  make `Process Incarnation` replaceable in `CONTEXT.md`, and what the existing
  crash/close diagnostics, workspace isolation, and RPC control stream assume.
  A separate process is necessary but not sufficient — it is the boundary the
  sandbox profile in Package 1 §3 then enforces writes against.

## Reference comparison: Muse and Grok Bot workspace isolation

Both are containment-first, but they isolate at *different granularities*, and
the distinction is the useful part.

**Grok Bot (xAI)** runs one Firecracker microVM **per account**, and within it
"all active Grok Bots share the same cloud computer" so teammates share
installed dependencies and authenticated logins without re-authenticating.
Per-agent isolation is therefore *not* a separate machine — it is a **kernel
write-confinement profile** (Landlock on Linux, Seatbelt on macOS, seccomp)
applied per process: `workspace` (writes confined to CWD, `~/.grok/`, tmp),
`strict` (reads confined, child-process network blocked), `read-only` (writes and
child outbound network blocked), `devbox` (disposable, broader writes). It also
applies environment-variable policy so spawned shells cannot read secrets from
the global env.

**Muse (Meta)** provisions a dedicated Secure VM per agent instance, splits a
containerized Runtime Cell from a Host Domain, and makes the agent
**propose-and-permit**: a host-side Sentinel evaluates every proposed action
against policy and escalates to human approval, an Auth Daemon swaps surrogate
tokens for real credentials so the model never sees them, and eBPF taint tracking
revokes automatic egress from any process that read sensitive or untrusted data.

Three conclusions for this design:

1. **Machine isolation and workspace isolation are different knobs.** Grok
   shares the machine and confines writes. For a local coding tool the machine
   is already the developer's, so the borrowable layer is the *profile*, not the
   VM. Package 1 §3 derives the profile from the tool grant that already exists.
2. **Sharing dependencies while isolating writes is the right trade.** It is why
   a durable per-Agent workspace beats a per-task one: provisioning is paid once.
3. **Propose-and-permit needs no new subsystem here.** `continual-learning`
   guardrails' `bash` rule with `action: "confirm" | "block"` is already a
   pre-execution gate at the command boundary, and `CONTEXT.md` already defines
   **Attention Request** and **Capability Grant**. Muse's Sentinel maps onto
   wiring those two together; its credential surrogation and eBPF taint tracking
   do not transfer to a local tool and are out of scope.

## Solution

Three packages with a strictly one-way dependency graph and no cycles.

```text
@fradser/pi-kit            shared primitives
                           + new worker-runtime: env binding, attempt authority,
                             intent files, outbox append, jsonl batch read
        ^
        |
@fradser/pi-subagents      ONE Agent: definition, spawn, tool grant, worktree,
                           context, Agent Memory, lifecycle, report channel
                           tool: agent(delegate|start|inspect|stop)
                           knows nothing about Work Items or peers
        ^
        |
@fradser/pi-tasks                    Work Items and their context: board state machine,
                           claim/submit intents, verify gate, per-Work context
                           snapshot and handoff, result evidence
                           tool: work (leader slice + worker slice)
                           knows nothing about processes; usable by one session
        ^
        |
@fradser/pi-agent-teams    composition: roster + board + mailbox
                           peer Agent Events, claim races, notices, wake-ups,
                           Agent Presence, Team Console
                           tool: agent_event; command: /agent-teams
                           the only package importing both layers below
```

Why `@fradser/pi-tasks` must not import `pi-subagents`: a task board that only works when
a child process exists cannot serve the stated requirement "让 pi 管理任务的上下
文". Installed alone, `@fradser/pi-tasks` gives one ordinary Pi session a durable Work
board with per-Work context — no subagents involved. Conversely `pi-subagents`
installed alone gives one delegated Agent with its own memory and no board.
Both are coherent products; `agent-teams` is their composition plus peer mail.

### The seam that makes it work

Today `WORKER_EXTENSION` is hardcoded to `agent-teams`' own `index.ts`, and that
one file branches on `workerBinding()` to become either the leader extension or
the worker extension. That single file is the blocker.

`--extension` is repeatable and `-ne/--no-extensions` still loads explicit `-e`
paths (`docs/cli.md`, Resource options). So the child command becomes:

```text
pi --mode rpc -ne \
   -e <pi-subagents>/src/worker.ts \
   -e <@fradser/pi-tasks>/src/worker.ts \
   -e <pi-agent-teams>/src/worker.ts \
   --tools <grant>
```

Each package ships its own worker extension and reads its own env binding.
`SpawnRequest.extensions: string[]` replaces the hardcoded constant, and that
array is the entire contract between the layers at the process edge. Shared
worker-side state (attempt authority) moves to `@fradser/pi-kit` so all three
worker extensions authorize against one implementation instead of three copies.

One coupling trap found while reading `spawner.ts`: `WORKER_CAPABILITY_TOOLS`
is hardcoded to `["agent_event", "work"]` and feeds both `resolveWorkerTools`
(the child's `--tools` allowlist) and `WORKER_TOOL_UNIVERSE` (the pre-spawn
validation that rejects ungrantable ids). After the split, `pi-subagents` alone
would advertise and grant two tools it does not ship. The capability set must
therefore become **contributed per loaded worker extension**, not enumerated in
the spawner: each worker extension declares the tool ids it registers, and
`resolveWorkerTools` unions the declarations of the extensions actually being
passed via `-e`. `WORKER_BUILTIN_TOOLS` (the eight Pi built-ins) stays in
`pi-subagents`, since that is the layer that owns the tool grant.

### Module migration

| Current `packages/agent-teams/src/` | Target | Notes |
| --- | --- | --- |
| `agents.ts` | subagents | Add `memory` frontmatter + Agent Definition versioning per `CONTEXT.md` |
| `spawner.ts` | subagents | `extensions: string[]`; session policy; budgets; depth guard |
| `worktree.ts` | subagents | `Computer Lease`. Reworked: durable per-Agent workspace at user scope, not per-task inside the repo (see Package 1 §3) |
| *new* `workspace.ts` | subagents | Workspace provisioning, env policy, sandbox profile selection and honest capability reporting |
| `work-context.ts` | **task** | Generalize from fork-only to per-Work context snapshot |
| `agent-actions.ts` | subagents | `agent` action dispatch |
| `leader-reports.ts` | subagents | Worker→parent report channel and rendering |
| `recipient.ts` | teams | Routing is peer mail |
| `state.ts` (teammates, roster) | subagents | |
| `state.ts` (tasks, board) | task | |
| `state.ts` (mailboxes, peer offsets) | teams | |
| `statefile.ts` (state/roster/outbox) | kit `worker-runtime` | DONE in kit as `readJsonlBatch`, `appendJsonlLine`, `writeJsonAtomic`, `createExclusiveJsonFile`, `takeJsonIntent`, `readRequiredEnvBinding`, `safeFileName`. Agent-teams still holds its own copies until step 2b rewires it |
| `statefile.ts` (board/claims/submissions) | task | Intent *validation* stays domain-specific: kit's `takeJsonIntent` takes a callback and knows no intent shape |
| `statefile.ts` (inbox) | teams | |
| `team-machine.ts` spawn/readiness/close | subagents | |
| `team-machine.ts` verify gate, submission acceptance | task | |
| `team-machine.ts` notices, wake-ups, peer routing, live poll | teams | |
| `worker.ts` attempt authority + automatic result | kit `worker-runtime` | One implementation, three consumers. **Deferred past step 2**: authority reads the roster, whose shape is teams-specific, and both consumers are not visible until the split lands. Extracting it blind would be an abstraction without a second known user |
| `worker.ts` `agent_event` peer branch | teams | |
| `worker.ts` `work` claim/submit | task | |
| `tools.ts` `agent` | subagents | |
| `tools.ts` `work` | task | |
| `tools.ts` `agent_event`, `/agent-teams` | teams | |
| `guidance.ts` | split three ways | Each package injects only its own guidance |
| `ui.ts` | teams | Agent Presence + Team Console |
| `tool-copy.ts`, `tool-render.ts` | kit | Already generic row language |
| `worker-tools.ts` | subagents | The tool universe |

`team-machine.ts` is the hard part: it is one module holding all four concerns
in shared closures (`leaderCwd`, `boardFile`, `sendUpdate`, `notifyChange`,
`generation`). The split replaces those closures with three explicit injected
interfaces (`ChildHost`, `WorkStore`, `Coordinator`), which is also what makes
each layer independently testable.

## Package 1 — `@fradser/pi-subagents`: an Agent with its own workspace and memory

Requirements: *sub agent 必须支持 agent 能够有自己的记忆*; *sub agent 应该有自己
的隔离的 workspace*（参考 Muse 与 Grok Bot）.

The two are coupled, not parallel: because Pi keys session storage by working
path, a durable isolated workspace is what makes Pi's own sessions usable as the
Agent's working memory.

Memory is **two** layers, and only one of them is this package's business. The
other is Pi's own.

| Layer | What it is | Who owns it | Scope |
| --- | --- | --- | --- |
| **Working memory** | The Pi session of a Work Session, stored by Pi in its own working-path-keyed location | **Pi** — `pi-subagents` only supplies a stable working path and stops passing `--no-session` | One Agent's workspace |
| **Agent Memory** | Distilled general task capability: methods, judgment criteria, operating patterns | `pi-subagents` | The Agent, cross-project |

There is deliberately **no work-history index**. A separate index would
duplicate what the Pi session already records, and would drift from it.

### 1. Working memory — Pi's own session storage, keyed by working path

Pi "stores sessions under `~/.pi/agent/sessions/`, grouped by working
directory" (`docs/sessions.md`), and `--continue` "opens the most recent session
for the current working directory". So the working path *is* the memory key.
`pi-subagents` does not invent a session scheme; it supplies a stable working
path and lets Pi do the rest.

Concretely this means:

- Drop `--no-session` from the default spawn. It is the single line that makes
  every current subagent amnesiac.
- Do **not** pass `--session-dir` or synthesize `--session-id`. A
  package-managed session directory is a second storage scheme competing with
  Pi's, and it forfeits everything below.
- Reuse what Pi already implements and what a bespoke scheme would have to
  rebuild: automatic **compaction** with a summary plus retained recent
  messages, session **branching** (`/tree`, `/fork`, `/clone`) with branch
  summaries, the `/resume` picker with search and rename, `/session` for
  cost/token inspection, and `/export`.
- `context` stays `fresh | fork | resume`, but `resume` now means "continue this
  workspace's most recent session", i.e. Pi's own `--continue`, not a
  package-resolved session id.

**The load-bearing consequence.** Because working memory is keyed by working
path, *the workspace must be durable and stable per Agent.* If the cwd changes
every task, every task starts a new empty session group and the Agent's working
memory fragments into one orphan per task. This is precisely what the current
`worktree.ts` does — it creates `teammate-<taskId>` and removes the directory on
completion. So the workspace redesign in section 3 is not a separate feature; it
is the precondition for Pi-session-as-working-memory to mean anything.

Authority still binds to `spawnId`, never to the session. A resumed session
carries prior-attempt history into context, so the
`[agent-teams-assignment:<id>]` marker and the leader-side `context` projection
that strips retired-attempt reports must both apply inside the child. That needs
its own feature file; it is the one genuinely new correctness risk here.

### 2. Agent Memory — general task capability only

`CONTEXT.md` already fixes the content contract: "Private durable knowledge of a
persisted Agent's reusable capabilities, methods, judgment criteria, and
operating patterns, including abstractions learned through project work, kept in
the Agent's own folder. Project-specific facts, decisions, and history remain in
Project Memory." Its `_Avoid_` list rules out "per-project subfolder" and
"shared memory folder".

So Agent Memory holds **how this Agent works**, never **what some project says**.

```text
~/.pi/agent/agents/<name>.md          user definition — the identity source
~/.pi/agent/agents/<name>/            Agent Memory, user scope only
    MEMORY.md                         bounded discovery index
    <entry>.md                        one capability / method / criterion each
    proposals/<ts>-<slug>.md          Memory Proposals awaiting review
```

**User scope only.** There is no `<cwd>/.pi/agents/<name>/MEMORY.md`. Three
independent reasons converge:

1. `CONTEXT.md` forbids a per-project subfolder for Agent Memory.
2. An existing project directive already requires local memory to live only
   under `~/.pi/` — recorded in `.memory/project_public-memory-project-root.md`
   as "本地的记忆只允许在 `~/.pi/` 中的位置".
3. A project-scoped capability folder cannot serve a cross-project Agent, which
   is the whole point of ADR-0001.

Agent *definitions* remain project-specializable — `CONTEXT.md`: "The user
definition is the persistent identity source; a project definition only
specializes that same Agent." The precise line is: **identity may be specialized
per project; capability memory may not.**

Content qualification follows `features/agent-memory-abstraction.feature`, which
already states the rules and moves to this package:

- Originating in a project does not disqualify a lesson.
- **Removing project identifiers does not prove a lesson is general.** An
  unsupported generalization is not merged as a global rule; a valid abstraction
  keeps its assumptions and limits.
- Reusing a method in project B does not import project A's facts, decisions, or
  history.

Injection follows ADR-0003 exactly: `before_agent_start` appends **only the
index** — filename, source, one-line description per entry — under a bounded
budget, roots declared once, all content marked untrusted reference data. The
child reads a full entry with `read` when the task needs it. Reuse
`continual-learning`'s budget, shortening, and omission-count rules plus its
memory-security tests (traversal and symlink-escape rejection); do not
reimplement its 2020-line `inject-memory.ts`.

Write gate comes free from the existing tool grant: an Agent whose grant includes
`edit`, `write`, or `bash` may append dated entries; a read-only Agent receives a
read-only block and no write path. The Agent writes a **Memory Proposal**, never
a direct merge — review and merge stay with `continual-learning`
(`/consolidate`, `/memory`), which already owns parent-validated plans, undo,
and guardrails. `pi-subagents` exposes `listAgentMemoryRoots()`; absent
`continual-learning`, proposals accumulate for human review. Safe degradation,
not failure.

**Temporary Agents get no memory folder.** **Agent Promotion** — the leader
judging a Temporary Agent's result worthy of a persisted identity from outcome
evidence, verification, and reuse value — is what creates the folder, and it is a
separate decision from memory approval.

### 3. Isolated workspace — the Computer Lease

`CONTEXT.md` already names this: "**Computer Lease**: Exclusive workspace
authority granted to one Work Session. Local worktrees, isolated browsers, and
cloud computers are alternative kinds of Computer Lease." The current
implementation is the weakest kind and has three defects:

| Defect | Current `worktree.ts` | Consequence |
| --- | --- | --- |
| Not durable | Directory removed by `cleanupWorktree`; only the branch survives | Orphans the Pi session group → amnesia (section 1) |
| Per task, not per Agent | `teammate-<taskId>`, branch `teammate/<taskId>` | No stable Agent home; deps re-provisioned every task |
| Inside the leader's tree | `<repoRoot>/.pi/worktrees/` | Not a cross-project Agent home; shares `.git` and pollutes the checkout with durable state |
| Opt-in | Only when `agent.worktree: true` | Default is *no* isolation: parallel workers share the leader's working tree |

Target: a **durable per-Agent workspace at user scope**, so one Agent has one
stable working path across attempts and across projects:

```text
~/.pi/agent/workspaces/<agent-name>/<project-slug>/    durable linked worktree
```

Durability also solves the provisioning cost that per-task worktrees hide:
`node_modules`, `.venv`, and build caches are paid once per workspace and reused,
instead of per task. This is the reasoning behind Grok Bot sharing one machine
across an account's bots — "multiple agent teammates access shared workspace
files, installed dependencies, and authenticated browser logins in parallel
without re-authenticating each time." Isolation of *identity and writes* does not
require duplicating *dependencies*.

Two cwd-keyed integrations must be handled explicitly, because both currently
break silently under a changed working path:

- **Pi sessions** group by cwd — the mechanism section 1 depends on. A stable
  workspace path is what makes it work.
- **`continual-learning` Project Memory** resolves its private root from the
  canonical cwd (`resolveMemoryPaths` → `projectScopeKey`). A subagent in a
  linked worktree has a *different* canonical cwd, so it resolves a different,
  empty private root and sees none of the leader's project memory. The public
  `.memory/` mirror survives because it is git-tracked and `--show-toplevel`
  resolves to the worktree itself, which satisfies the mirror's enablement rule —
  so the failure is *partial and silent*: public memory present, private memory
  absent. Adopt `pi-subagents`' rule: **project memory maps to the main checkout
  for linked worktrees.**

**Write confinement — the Grok borrow.** Grok Bot enforces workspace isolation
with kernel primitives (Landlock on Linux, Seatbelt on macOS, seccomp) behind
four profiles: `workspace` (writes confined to CWD, `~/.grok/`, tmp), `strict`
(reads confined to CWD plus system paths, child-process network blocked),
`read-only` (writes and child outbound network blocked), `devbox` (disposable,
broader writes).

This repo already has the axis those profiles belong on. `references/agent-roles.md`
defines a **Mutability** axis (`mutating` · `read-only`) and then admits the gap
in writing:

> "A `bash` grant is not read-only — a shell can still write, so 'read-only'
> here bounds the tools, not the file system, and the completion gate relies on
> the reviewer's instruction rather than enforcement."

That sentence is the justification for this layer. The profile is **derived from
the tool grant**, not a new orthogonal knob:

| Tool grant | Profile | Enforcement |
| --- | --- | --- |
| read-only (`read`,`grep`,`find`,`ls`) | `read-only` | writes and child outbound network blocked |
| `edit`/`write`, no `bash` | `workspace` | writes confined to the workspace |
| `edit`/`write` **and** `bash` | `strict` | writes confined, child-process network gated |
| explicit disposable experiment | `devbox` | broader writes, workspace discarded |

Platform reality must be stated honestly: Seatbelt via `sandbox-exec` on macOS,
Landlock/seccomp or bubblewrap on Linux, and no equivalent on Windows. So this is
a **declared, optional capability with truthful reporting** — where enforcement
is unavailable the spawn result says "filesystem isolation only (worktree); no
kernel write confinement", never silent passage. `pi-subagents` draws exactly
this line between "declared capabilities" and proven launch compatibility, and
it is the right discipline.

**Secret hygiene — an immediate finding, independent of the split.**
`spawner.ts:585` spawns the child with `env: { ...process.env, ...options.env }`.
Every subagent today inherits the leader's complete environment, including every
provider API key and token. Grok Bot's sandbox explicitly applies "top-level
environment variable policies, preventing spawned shell processes or
sub-commands from accessing secrets or API keys stored in your global
environment variables." An allowlist-plus-denylist env policy is cheap, needs no
kernel support, and should land before the sandbox work rather than after it.

**Propose-and-permit — the Muse borrow.** Meta Muse is containment-first: the
agent runs in a runtime cell and can only *propose* actions, while a host-side
Sentinel evaluates each against policy and escalates to human approval; an Auth
Daemon swaps surrogate tokens for real credentials so the model never sees them;
eBPF taint tracking strips automatic egress from any process that read sensitive
or untrusted data.

The local analogue already exists in this monorepo: `continual-learning`
guardrails' `bash` rule with `action: "confirm" | "block"` is a pre-execution
gate at the command boundary — the Sentinel's role — and `CONTEXT.md` already
defines **Attention Request** ("bounded request for human judgment or
authorization containing the decision, evidence, recommendation, and allowed
choices") and **Capability Grant** ("authorization that lets one Work Session use
a requested external tool or computer capability... become visible progressively
as the Work Session needs them"). So propose-and-permit is a wiring job onto two
existing mechanisms, not a new subsystem. Full credential surrogation and eBPF
taint tracking are out of scope for a local tool.

### Also new in Package 1

- **Budgets**: `toolBudget` / `usageBudget` equivalents. `WorkerUsage` is already
  accumulated; only the ceiling and the fail-closed stop are missing.
- **Depth guard**: default 2 levels. A child cannot spawn a child today only
  because `-ne` plus one `-e` leaves no `agent` tool; once worker extensions
  compose, nesting becomes reachable and must be bounded deliberately.

## Package 2 — `@fradser/pi-tasks`: Work Items own their context

Requirement: *task 能够让 pi 管理任务的上下文.*

`@fradser/pi-tasks` is the single-writer Work authority plus a per-Work context store. It
runs in the leader session and needs no child process.

**Work Item context bundle** — what `@fradser/pi-tasks` persists per Work Item:

| Field | Status | Purpose |
| --- | --- | --- |
| `subject`, `description`, acceptance criteria | exists | the brief |
| `dependsOn`, `resources` | exists | graph + conflict exclusion |
| `verify` | exists | independent acceptance gate |
| `result`, `errorMessage`, `deferredMessages` | exists | evidence retention |
| `contextSnapshot` | **new** | bounded session snapshot for `fork`/recheck |
| `handoff` | **new** | structured successor brief (replaces prose `buildSuccessorHandoff`) |
| `contextRefs` | **new** | prior Work IDs, report IDs, files this Work builds on |
| `workspacePath` | **new** | the Agent workspace this Work ran in. Not a session id — Pi owns session storage and resolves it from this path, so `@fradser/pi-tasks` records the path and never a session handle |
| `contextBudget` | **new** | byte/line ceiling so a long-lived Work cannot grow unbounded |

`@fradser/pi-tasks` deliberately stores **no session identifier**. Session storage belongs
to Pi and is keyed by working path; the Work Item records the path it ran in and
leaves resolution to `pi-subagents` at spawn time. Keeping that boundary is what
prevents `@fradser/pi-tasks` from growing a dependency on the process layer.

Promoting `work-context.ts` from a fork-only helper into the Work Item's own
context store is the core of this package. Two concrete payoffs: reassignment
hands the successor a **bounded structured handoff** instead of the full
history, and a Work Item survives leader restarts — `readBoardFile` already
reloads the board on `initTeamMachine`, but today the context behind it does
not.

The verify gate (`runVerifyGate`, `resolveGateOutcome`,
`VERIFY_FAILURE_ESCALATE_AFTER`) moves here whole: it judges a **Submission**
against a Work Item's completion requirements, which is `Work Acceptance` in
`CONTEXT.md` and has nothing to do with processes.

Standalone surface: `work(create|list|assign|release|reopen|supersede)` for the
leader, `work(list|claim|release|submit)` for a worker, and a `/task` console.
Installed without `pi-subagents`, `assign` targets the current session itself
rather than a child — which is exactly "pi 管理任务的上下文".

## Package 3 — `@fradser/pi-agent-teams`: peers choose and complete Work

Requirement: *支持 subagent 能够互相沟通，选择并且完成 task.*

This is largely already built and largely stays:

- **互相沟通** — `agent_event` plus `inbox-*.jsonl` peer mail, `spawnId`-bound
  delivery so a replacement resident cannot consume its predecessor's mail,
  `peerDeliveryStates` recording `queued|routed|dropped`. This is the capability
  `pi-subagents` does not have at all; it is the reason `agent-teams` survives as
  a package rather than being absorbed.
- **选择 task** — contested board claims through atomic intent files
  (`createTaskIntent` wins exactly one racer), notice throttling
  (`NOTICE_PACE_MS`, `noticedTaskIds`), harness wake-ups, and the deliberate
  `pending/recovery-required` hold that keeps a transient failure from being
  silently retried by whichever resident happens to be idle.
- **完成 task** — attempt-bound authority: one Assignment Attempt, one terminal
  report, automatic and explicit submission through one acceptance pipeline.

New work in Package 3 is composition and presence, not mechanism:

1. Wire `ChildHost` (Package 1) to `WorkStore` (Package 2) — the assignment,
   claim-acceptance, and submission loops that `team-machine.ts` currently
   inlines.
2. **Agent Presence** per `CONTEXT.md`: leader-visible state (queued, starting,
   active, waiting, blocked, complete) reported *without a model turn*. ADR-0002
   already forbids heartbeat/stall notices; presence is console telemetry.
3. **Team Console** upgrade: cross-project Agents, project Work Items, Work
   Sessions, coordination history. `ui.ts` (747 lines) is the base; a
   FleetView-style persistent view is the borrowable idea here.
4. **Handoff** as a real transfer: source keeps ownership and resource authority
   until the target accepts and ownership changes atomically. Today
   `buildSuccessorHandoff` requires the predecessor to be stopped first.
5. **Agent Inbox** durability: a message may wait with no active Work Session.
   Today mail dies with the leader session's runtime dir
   (`STATE_DIR_MAX_AGE_MS` cleanup).

## Execution sequence

Strangler order; every step ships green and stays publishable. Do not attempt
the split as one commit — `test_teammate_package.py` (1907 lines),
`test_assignment_guards.py` (1009 lines), and 23 feature files all pin current
behavior.

| Step | Work | Gate |
| --- | --- | --- |
| 0 | Freeze baseline: record candidate revision, run `pnpm check`, snapshot `pnpm --dir packages/agent-teams pack --dry-run` | All green before any move |
| 1 | **Env policy at spawn.** DONE. Replace `env: { ...process.env, ...options.env }` with an explicit allowlist plus a secret denylist. Independent of the split, needs no kernel support, and closes the finding that every subagent currently inherits every provider key | Live spawn: child can run, `env` inside the child shows no provider token |
| 2 | Extract `worker-runtime` into `@fradser/pi-kit`: env binding, attempt authority, intent files, outbox append, `readJsonlBatch`. **2a DONE** (primitives added to kit, additive, no consumer rewired); **2b pending** — rewiring `statefile.ts` / `worker.ts` touches files the step-1 security review is reading, so it waits for that review rather than invalidating its evidence | `packages/kit/tests/test_pi_kit.py` + agent-teams suite unchanged |
| 3 | Make `SpawnRequest.extensions: string[]` replace `WORKER_EXTENSION`; capability tool set becomes contributed per loaded worker extension. **DONE** | Live `pi --print` spawn + one resident round-trip; command line asserted from inside a spawned child |
| 4 | Create `packages/subagents`; move `agents.ts`, `spawner.ts`, `worktree.ts`, `agent-actions.ts`, `leader-reports.ts`, roster state, spawn/readiness/close machine; split worker extension out of `index.ts`. **PARTIAL** — see below | subagents standalone: delegate + report, no board, no peers |
| 5 | Create `packages/task`; move board state, intents, verify gate, `work-context.ts` → context store; split `work` tool. **PARTIAL** — see below | task standalone: one session manages a board with context |
| 6 | Reduce `agent-teams` to composition: peer mail, notices, wake-ups, presence, console | Full existing suite passes against the composed stack |
| 7 | **Durable per-Agent workspace.** Rewrite `worktree.ts` into `workspace.ts`: stable user-scope path per (Agent, project), no removal on completion, deps provisioning, and the `continual-learning` main-checkout mapping for linked worktrees | Same Agent across two attempts resolves one workspace path; subagent sees the leader's project memory |
| 8 | **Drop `--no-session`.** Working memory becomes Pi's own session storage keyed by the workspace path; add `context: resume` | Second attempt on one workspace continues the first attempt's session; authority still binds to `spawnId` |
| 9 | **Agent Memory.** User-scope folder, ADR-0003 index injection, tool-grant write gate, Memory Proposals; flip `agent-memory-abstraction.feature` from `@unimplemented` | Memory security tests; read-only Agent cannot write; no project fact admitted as a capability |
| 10 | **Sandbox profiles** derived from the tool grant, with honest capability reporting where enforcement is unavailable | Read-only grant provably cannot write outside the workspace on an enforcing platform; non-enforcing platform reports so |
| 11 | Budgets + depth guard; Handoff; durable Agent Inbox | Each behind its own feature file |

Steps 4-6 are the mechanical split and should land together as one version bump
of `agent-teams` (the public tool surface does not change). Steps 7-11 are the
new capability and each lands independently.

### Step 1 outcome

Landed as `src/child-env.ts` plus wiring in `spawner.ts`, `types.ts`,
`team-machine.ts`, and `ui.ts`; contract in `features/spawn-env-policy.feature`;
tests in `tests/test_child_env.py` and `tests/live-child-env.ts`.
The measured leader environment held **134 variables**, of which at least 40 were
credential-bearing (`CF_S3_KEY`, `NOTE_ENCRYPTION_KEY`, `EVENT_ENCRYPTION_KEY`,
`FIGMA_TOKEN`, `ODK_DESK_LINK_CONTROL_TOKEN`, an npm registry auth token whose
name embeds a private host, and others). All of them reached every spawned Agent
before this step.

The allowlist is exact-match with one admitted prefix (`LC_`). `PI_CODING_AGENT_DIR`
passes through, which is what lets the child resolve the same `auth.json` and
`models.json`; the local `cli-proxy` provider keeps a literal `apiKey` in
`models.json`, so no environment credential is needed for it. Setups using Pi's
`$NAME` interpolation need those exact names in `PI_TEAMMATE_ENV_ALLOW`.

Two findings worth carrying forward:

- **`tests/live-work-sessions.ts` is stale, independently of this change.** It
  delegates twice under the same name and expects two concurrent residents,
  which the current design forbids (`types.ts`: a teammate name is "unique among
  living teammates"). It fails identically at baseline `aa05ae0` — verified in a
  clean worktree — with `A living teammate named "live-worker" already exists.`
  It is opt-in and not run by `pnpm test`, which is why the breakage went
  unnoticed. Left unfixed here as out of scope; it should be repaired or removed
  when Package 1 work touches the live fixtures.
- **`tests/agent-actions-fixture.ts` mocks `spawnTeammate`**, so the Python suite
  never exercised a real child spawn. That is why step 1 added a real-spawn
  integration test rather than relying on the existing suite as coverage.

macOS blocks `ps eww` environment inspection for child processes (it returns the
header only), so the child environment cannot be verified from outside. The
integration test therefore has the child dump its own `process.env` to stderr,
which is both portable and a stronger proof than an external read.

### Step 3 and partial step 4 outcome

Step 3 landed as designed, with one correction. `capabilityTools` was made
optional with a runtime contradiction check rather than required: declaring
capability tools while supplying no extension is refused with an error naming
both, while an empty `extensions` list legitimately means "bare child with only
pi built-ins". Requiring the field would have forced ten unrelated tests to
declare `extensions: []` as noise; the contradiction check encodes the invariant
that actually matters.

Step 4 is **partial, deliberately**. `@fradser/pi-subagents` now exists and owns
the seven execution modules — `agents.ts`, `child-env.ts`, `leader-reports.ts`,
`spawner.ts`, `work-context.ts`, `worker-tools.ts`, `worktree.ts` — plus
`WorkerUsage`. It is a library package on the `pi-kit` pattern (no `pi` manifest
key, `exports: { ".": "./index.ts" }`), consumed by `agent-teams` through
`workspace:*`.

What did **not** move, and why: `agent-actions.ts`, the roster half of
`state.ts`, and the spawn/readiness/close half of `team-machine.ts` all import
the coordination core (`state.ts`, `statefile.ts`). Moving them requires
introducing the `ChildHost` / `WorkStore` / `Coordinator` interfaces first, which
is the real decomposition work rather than a file move. Until that lands,
`@fradser/pi-subagents` is a spawnable child with pi built-ins and no `agent`
tool, so it is not yet installable standalone — the README and manifest say so
explicitly rather than implying otherwise.

Tests moved with their subject: `test_child_env.py` and `test_spawn_extensions.py`
to `packages/subagents/tests/` (with their own `helpers.py` and `conftest.py`),
and both feature files to `packages/subagents/features/`.
`live-child-env.ts` stayed in `agent-teams` because it drives `initTeamMachine`
and `spawnTeammate` — it verifies the composed stack, not the execution layer.
`test_spawn_extensions.py` was rewritten to use neutral capability names
(`alpha_tool`, `beta_tool`) instead of the real coordination pair, which is a
stronger test of the property: the spawner must be agnostic. The agent-teams
side keeps `test_the_coordination_contribution_is_declared_and_passed_to_every_spawn`,
which asserts the declaration matches what `worker.ts` actually registers.
Remaining agent-teams tests now import the moved modules by package specifier,
so they exercise the real consumer resolution path rather than a relative file.

**A pre-existing repo hazard this exposed.** Adding the first cross-package type
boundary surfaced unresolved core-version drift: the lockfile holds
`@earendil-works/pi-coding-agent` at 0.84.1 for most packages, 0.85.1 for
`impeccable` and `utils`, and 0.87.1 for the root devDependencies. The drift was
tolerable only because nothing crossed a package boundary with core types. It is
not harmless: **`addedToolNames` exists in pi-agent-core 0.84.1 and 0.85.1 but
was removed in 0.87.1**, and `work-context.ts` still destructures it — so a
package resolving 0.87.1 fails to typecheck. The new package was aligned down to
0.84.1 to match its consumer rather than upgrading fifteen packages, which is
outside this task's scope. Aligning the whole repo to one core version, and
fixing the `addedToolNames` use, is a separate decision that should not wait for
the next package to trip over it.


### Step 5 outcome (partial)

`@fradser/pi-tasks` exists and owns the **dependency-free half** of the Work Item domain:
the data model (`BoardTask`, `TaskStatus`, `TaskIntent`, `WORK_RUNTIME_VERSION`),
the pure graph and resource rules, and durable board persistence including the
exclusive-create claim/submit intents.

What did **not** move, and why: the in-memory board container and its transitions
(`createTask`, `setTaskClaimed`, `releaseTask`, `completeTask`,
`reopenCompletedWork`, `releaseTasksOf`, `createDirectWork`, `reclaimDirectWork`),
the verification gate, and both `work` tool slices. The blocker is one function:
`activeAssignmentConflict` reads the roster to decide which held assignments
conflict. That is the `WorkStore` seam — task's store must take an injected
conflict oracle rather than reading a roster — and it deserves its own increment
with its own feature file rather than being improvised inside a file move.

The clean line that made this increment safe: **`resourcesConflict` is the
primitive and belongs to task; `activeAssignmentConflict` is roster policy and
stays.** That single distinction is what let the pure rules move with zero
behavioural risk.

Two duplications were removed on the way:

- `worker.ts` carried a private copy of `resourcesConflict` with a wider
  signature than the leader's. A worker and the leader could in principle have
  disagreed about whether two leases conflict. Both now call one implementation.
- `sessionKey` moved to `@fradser/pi-kit`, because the board directory and the
  teammate runtime directory are scoped by the same key and two packages must
  agree on which session a directory belongs to.

Three deliberate changes, each recorded in the changeset:

1. Board errors now say `Work snapshot`, not `Agent Teams Work snapshot` —
   `@fradser/pi-tasks` owns the file and may be installed without the team runtime.
   `test_snapshot_version.py` was updated to the corrected wording; the version
   numbers and the refusal to treat an unreadable board as empty are unchanged.
2. `TaskStatus` became a plain TypeScript union. The TypeBox construction existed
   only to be converted straight back with `Static<>` and no tool parameter ever
   used the runtime value, so `@fradser/pi-tasks` needs no typebox peer.
3. `WORK_RUNTIME_VERSION` keeps the value `2` inherited from
   `TEAM_RUNTIME_VERSION`, so pre-extraction boards still load. The two files now
   version independently, which is correct because their schemas are independent.

`canonicalDependencies` and `hasDependencyCycle` became public: they were private
to `state.ts`, and a board-only consumer needs the same cycle refusal the leader
applies at creation.

The new package carries its own contract and tests
(`packages/tasks/features/work-domain.feature`,
`packages/tasks/tests/test_work_domain.py`) importing through the barrel, so a
symbol missing from `index.ts` fails rather than passing through a deep relative
path. One test asserts the package boundary itself: every import in `packages/tasks/src/`
is a node builtin, the Pi core peer, pi-kit, or a sibling — and no module may
mention teammates, spawning, mailboxes, or `agent_event`.

The same core-version drift found in step 4 recurred here (`@fradser/pi-tasks` resolved
0.87.1 on first install) and was aligned to 0.84.1 for the same reason.


### Steps 7-9 outcome: workspace, working memory, and Agent Memory

Landed together, because Pi keys session storage by working directory: a durable
per-Agent workspace is the precondition for Pi's own sessions to serve as that
Agent's working memory, and Agent Memory is the semantic layer above it.

- **Durable per-Agent workspace** at `~/.pi/agent/workspaces/<agent>/<project-slug>/`,
  a linked worktree on a durable `agent/<name>` branch. Isolation is now the
  default; `worktree: false` opts out. Completion calls
  `preserveAgentWorkspace`, which commits the attempt's output and leaves the
  directory; only an explicit `releaseAgentWorkspace` removes one. A failed spawn
  removes a workspace only if that spawn created it and nothing ran in it.
- **Working memory is Pi's own session storage.** `spawnResident` gained
  `session: "none" | "persist" | "resume"` and no `--session-dir` is introduced,
  so Pi's compaction, branching, `/resume` picker, and `/export` are reused
  rather than rebuilt. A shared workspace stays `"none"`, because persisting
  there would put the child's turns into the user's own session group.
- **Agent Memory** at `~/.pi/agent/agents/<name>/`, user scope only, opt-in via
  `memory: true`, and never for a session-scoped Temporary Agent. Injection
  follows ADR-0003 (bounded index, no bodies). Writing is gated by the tool
  grant, with `bash` and `powershell` counting as write-capable because a shell
  can write. Generalizing lessons become Memory Proposals; review and merge stay
  with `pi-continual-learning`.
- **Two worker extensions in one child.** `agent-teams` now contributes
  `[SUBAGENT_WORKER_EXTENSION_PATH, WORKER_EXTENSION_PATH]` and the union of both
  capability sets. The first real use of the step-3 seam; the live run recorded
  the child's effective grant as `read, write, agent_memory, agent_event, work`,
  which is both packages' contributions in one process.

**The blocker this surfaced.** Pi's `defaultProjectTrust` is `"ask"`, and a newly
created directory is an untrusted project, so a child started in a fresh workspace
blocked forever on a trust prompt that `--mode rpc` has no UI to answer. The spawn
succeeded, the process lived, and nothing was ever reported. This is why the
isolated path had to be verified with a live run in a real repository: every unit
test called `ensureAgentWorkspace` directly, and the pre-existing live fixture ran
in a non-repository temporary directory that takes the shared fallback. Neither
could reach the defect.

Fix: `spawnResident` gained `approveProjectTrust`, which passes `-a`, set only
when the harness created the workspace — a linked checkout of a repository the
leader already trusts. A child sharing the caller's directory inherits that
directory's trust record and is deliberately not force-approved, which is also why
the shared path never showed the bug.

Two fixture defects were found and fixed while proving this. Redirecting
`PI_CODING_AGENT_DIR` to an empty temporary directory also hides the real
credentials, so the child cannot authenticate; the fixture now symlinks
`auth.json`, `models.json`, and `settings.json` through rather than copying them,
because a test must never duplicate a secret onto disk. And the timeout timer was
`unref`'d, so a child that never reported let the process exit silently instead of
failing; it is now kept alive so a hang is diagnosable. That single change turned
an empty exit into the error that led to the trust finding.

Verified by `packages/agent-teams/tests/live-workspace-memory.ts`
(`LIVE_AGENT_WORK_MODEL=... node tests/live-workspace-memory.ts`): durable
workspace, session persisted under the workspace path, reuse on a second attempt,
memory opted in, real model turn completed, durable branch present.

`worktree.ts` is superseded and no consumer imports it, but it remains exported so
its existing git-mechanics tests keep running. Removing it means migrating those
three tests to `workspace.ts` coverage, which is a separate change.

### Step 1 hardening

A self-review pass after the first green run found five defects in the change
itself. All are fixed; each is worth recording because three were caused by the
first version of the fix rather than by the original leak.

| Defect | Fix |
| --- | --- |
| `withheldSecretNames` unbounded in persisted state, with the diagnostic and the console each applying their own cap of 16 | Bounded once at the source; `withheldSecretCount` carries the true total |
| Static tripwire asserted `"...process.env" not in spawner` | Asserts `"process.env" not in spawner` — the weaker spelling passes on `Object.assign({}, process.env)` |
| Integration test spot-checked one sentinel, so an allowlist admitting a whole secret class would still pass | Asserts the full subset property via an exported `isAllowedEnvName` |
| Undocumented code-execution names in the allowlist (`NODE_OPTIONS`, `NODE_PATH`, `GIT_SSH_COMMAND`, `GIT_CONFIG_GLOBAL`, `EDITOR`, `VISUAL`, `PAGER`, `GIT_EDITOR`, `GIT_PAGER`, `SSL_CERT_FILE`, `SSL_CERT_DIR`) | Documented in the `ALLOWED_EXACT` header with the trust argument: they originate in the developer's shell, are not model-controllable, and carry no credential value |
| `envPolicy` reachability into the worker-readable roster unverified | Verified: `writeRoster` projects exactly seven fields, so it cannot reach workers |

The strengthened subset assertion then found a real platform interaction on its
first run: **libuv injects `__CF_USER_TEXT_ENCODING` into every macOS child
regardless of the supplied environment.** The name is simultaneously withheld by
the policy and present in the child. It is a UID-derived locale hint, not a
credential, and it is now declared as `RUNTIME_INJECTED_ENV_NAMES` so the test
asserts against an explicit narrow set instead of excusing any unexpected name —
a genuine leak must not be able to hide behind "the runtime probably added it".
The withheld count reflects the policy's decision and is not reduced by the
runtime putting a name back; that is pinned by a deterministic unit test because
the integration test's arithmetic depends on whether the host exports the name.

It also surfaced a second-order interaction: bounding the name list to 16 means
that on a shell exporting more than 16 credential-shaped variables, a specific
sentinel can be legitimately truncated out of the list. The assertion now treats
truncation as the only acceptable reason for absence, rather than being weakened
to not check at all.

Reference-machine measurement from the live run: **115 leader variables withheld,
45 credential-shaped**, name list at its cap of 16, child still authenticated and
completed its turn.

**Ordering constraint between 7 and 8.** The workspace must be durable *before*
`--no-session` is dropped. Pi keys session storage by working path, so enabling
session persistence while the cwd is still per-task and disposable would create
one orphaned session group per task — strictly worse than the current amnesia,
because it also accumulates unbounded storage. Step 1 is deliberately first
despite being unrelated to the split: it is a live secret-exposure finding and
should not wait behind a refactor.

Publishing: `scripts/publish-release.mjs` `PUBLISH_SCOPE` must list
`@fradser/pi-kit` → `@fradser/pi-subagents` → `@fradser/pi-tasks` →
`@fradser/pi-agent-teams` in that order, since consumers use their dependencies
at runtime. `~/.pi/agent/settings.json` currently points at
`packages/agent-teams`; the two new local paths must be added and the installed
paths verified with `pnpm check:install`. Changesets are required for all three,
and packed manifests must contain no `workspace:` protocols.

## The final tool design

This section supersedes both earlier framings in this document. The first proposed
that `agent-teams` be a load-time composition root calling its dependencies'
registrars; the second corrected that to a bundle that loads their extensions.
Both are kept in the reasoning below, because the defects they fixed are the reason
the third formulation looks the way it does.

Three packages, three tools, one registrant per tool. A package registers only
what it implements and never names a participant it does not own. A tool name is
never reused with a second meaning.

| Package | Tool | Owns | Never touches |
| --- | --- | --- | --- |
| `@fradser/pi-subagents` | `agent` | process lifecycle | task state, peer messaging |
| `@fradser/pi-tasks` | `task` | task state and context | processes, peer messaging |
| `@fradser/pi-agent-teams` | `message` | peer messaging, notices, presence, console | task state, process creation |

Nine actions in total, one schema for `task` shared by every process.

### The design criterion

The test applied to every merge and split in this design is not symmetry or
elegance. It is:

> **When the model judges wrong, is the mistake cheap, and is it reversible in
> both directions?**

The pre-existing double track fails it. `agent delegate` created a direct work item
*implicitly*, so a model could not afterwards tell which mode it was in, and a
wrong choice was invisible and unrecoverable. Every change below is justified by
this test and by nothing else.

### `agent` — 4 actions

| action | required | meaning |
| --- | --- | --- |
| `start` | `name`; `prompt?` | Spawn a persistent child. With `prompt`, it works immediately; without, it enters the worker pool and takes work from the board itself. Spawning never creates a task. |
| `inspect` | `session` | State, spawn id, holding, usage, environment diagnostics. |
| `list` | — | Enumerate children. |
| `stop` | `session` | Terminate the process, releasing its task lease. |

`delegate` and `start` are merged because they were the same operation dispatched
twice, and the only difference was whether a prompt was delivered. Optional
`definition`, `tools`, `model`, `fork`; `fork` without `prompt` now means a
context-primed idle resident and is no longer refused. No `verify`: there is no
task to attach it to.

### `task` — 4 actions, one schema for every process

| action | parameters | meaning |
| --- | --- | --- |
| `create` | `subject`; `description?` `dependsOn?` `supersedes?` `resources?` `verify?` `context?` | Record work. `supersedes[]` folds replacement in; there is no `supersede` verb. |
| `list` | `id?` `status?` `owner?` `claimable?` | Read only. Per-item `details` must carry `claimedBy`, `recoveryRequired`, and `dependsOn`, and the result is bounded. |
| `update` | `id`; `status?: in_progress\|pending` `context?` `description?` `verify?` `resources?` `reason?` | `→ in_progress` **is** taking the task. `completed → pending` **is** reopening. |
| `complete` | `id`, `outcome: success\|failed`, `result?` | The only terminal action. `failed` returns the task to pending, sets the recovery hold, and records the blocker as evidence. |

`claim` collapsed into `update(status=in_progress)`, `assign` into nothing at all,
`reopen` into `update(status=pending)`, `abandon` into `complete(outcome=failed)`.

### `message` — no `action` parameter

| parameter | value |
| --- | --- |
| `to` | `"leader"`, an exact `session:name:spawnId` route, a `session:name` route, or a bare name (ambiguity is rejected with the precise routes listed) |
| `body` | text |
| `kind` | `inform` (no response expected) or `request` (wakes the recipient) |

`details` returns `{ to, from, kind, outcome }`. There is deliberately no
`in_reply_to`: in a one-to-one conversation the sender *is* the thread. The only
failure mode is one question split across two messages, which is a prompt-level
requirement to write a message whole, not a protocol feature to add.

Three things are refused on purpose:

- **Broadcast, cc, groups.** "Tell everyone" is already automatic board notice. A
  manual broadcast invites the status-narration the guidance spends three lines
  opposing.
- **Attachments and file references.** Mail carries decisions and blockers.
  Evidence belongs to `complete(result)`. `BoardTask.deferredMessages` is the scar
  from getting this wrong before.
- **Request lifecycle state.** A stateful message queue requires polling, which is
  forbidden. The durable record of a blocker is `complete(outcome=failed)`; the
  message only wakes someone.

### Tasks and agents are decoupled

There is no `assignee` field, and a task has no owner. Ownership is *derived from
action*: the caller of `update(status=in_progress)` becomes the holder, and the
runtime records that identity from context. The model cannot name anyone else.

This removes three problems the earlier design could not:

1. A `claim`-style action with an optional `worker` parameter is a privilege
   escalation, or a silently ignored field. There is no field.
2. "One verb, two authorizations" cannot occur when there is one verb.
3. No `task` action needs to know whether the caller is the leader or a worker, so
   the two divergent schemas collapse into one.

The cost is real and accepted: the leader cannot push work to a named Agent. It
starts a resident, the resident is woken by board notice, and it takes what it
takes. The board states *what*, never *who*; `resources` expresses where writes
conflict, not who is conflicting.

### The state machine

`pending → in_progress → completed`, plus `superseded` produced only by
`create(supersedes)`. `recoveryRequired` is an orthogonal boolean, not a status.

1. **Taking** — `update(status=in_progress)` is atomic; exactly one winner, and a
   loser is told who holds it. The caller's `resources` are checked against every
   other live holder's.
2. **Delivering** — `complete` requires the caller to be the current holder. With
   no live holder, any process may close the task as fallback acceptance; a live
   holder that is not the caller is refused.
3. **Release** — automatic on `complete`, on process exit, and on `agent stop`.
   There is no explicit abandon verb.
4. **Recovery hold** — set by `complete(outcome=failed)`. Cleared by
   `update(status=in_progress)`, which **requires `reason`** while the hold is set.
   A reason is required rather than a role gate because a role gate would put
   Agent-identity authority back into the board, which is exactly what the
   decoupling removes.
5. **Reopen** — `update(status=pending)` on a completed task is refused while a
   dependent is in progress, and the error names the holder.

### Two entry points per package

`index.ts` is each library's barrel and cannot be a Pi extension: the loader
requires a `default` export function, and a barrel has none. Each package needs
three files, and the bundle points at the extension entries, never the barrels.

| Package | Library barrel | Leader extension | Worker extension (`-e` into a child) |
| --- | --- | --- | --- |
| `pi-tasks` | `index.ts` | `extension.ts` → `task` | `worker-extension.ts` → `task` |
| `pi-subagents` | `index.ts` | `extension.ts` → `agent` (**new**) | `src/worker-extension.ts` → `agent_memory` (exists) |
| `pi-agent-teams` | — | `index.ts` → `message`, plus the other two | `index.ts` worker branch → `message` |

`pi-subagents` currently has no leader-side extension at all; `agent` is still
registered by `packages/agent-teams/src/tools.ts`. That is the file that has to
exist before the split can be called done.

### Bundle composition

Pi sanctions loading a dependency's extension: `docs/packages.md` — "Other Pi
packages used as dependencies must be included in the published tarball and
referenced through their `node_modules` resource paths." So the bundle's manifest
is:

```json
"pi": {
  "extensions": [
    "./index.ts",
    "./node_modules/@fradser/pi-subagents/extension.ts",
    "./node_modules/@fradser/pi-tasks/extension.ts"
  ]
}
```

Each tool then has exactly one registrant in every install combination:

| Installed | Tools | Behaviour |
| --- | --- | --- |
| `pi-subagents` | `agent`, `agent_memory` | spawn and observe; prompted work is not recorded as a task; results report to the leader |
| `pi-tasks` | `task` | single-session board; the main session takes tasks with `update(status=in_progress)` |
| `pi-subagents` + `pi-tasks` | `agent`, `task` | residents read the same board; conflicts are checked against live holders |
| `@fradser/pi-agent-teams` (bundle) | `agent`, `task`, `message` | full runtime: peer mail, notices, presence, console |

### How the coordinator is reached

`pi-tasks` needs to wake residents and refresh the console without knowing what a
resident is. `pi.events` carries the outcome across Pi's separate module roots,
and `@fradser/pi-kit` carries the roster, so neither package imports the other:

```ts
// in pi-tasks, after a board transition succeeds
pi.events.emit("pi-tasks:task-taken", { id, holder, resources });
pi.events.emit("pi-tasks:task-completed", { id, outcome });
```

`pi-agent-teams` subscribes and does the noticing, the wake-up, and the console
refresh. When it is not loaded, nothing happens, which is the correct degradation.

**Dependency direction is acyclic:** `pi-tasks → pi-kit`; `pi-subagents → pi-kit`;
`pi-agent-teams → pi-kit` plus both. The domain does not know about processes, and
a process needs nothing from the domain either, because spawning no longer creates
a task.

### Breaking changes

One minor version is not available. This lands as `1.0.0` with no compatibility
layer, matching the existing preference for a hard cutover.

| Kind | Change |
| --- | --- |
| Tool names | `work → task`, `agent_event → message` |
| Removed actions | `delegate`, `claim`, `abandon`, `reclaim`, `assign`, `submit`, `release`, `supersede`, `get` |
| Removed parameter | `assignee`; `take` |
| Kept actions | `agent.start` (now with optional `prompt`), `task.create`, `task.list`, `task.update`, `task.complete` |
| Added parameters | `agent.start.prompt?`, `task.update.status?`, `task.update.reason?`, `task.complete.outcome` |
| Value rename | `TaskStatus` `claimed → in_progress` |
| Behaviour | `fork` with no `prompt` is now legal instead of refused |

Assertions are updated to the new names, never weakened, and boundary tests are
added pinning that every removed name and the removed status value are refused, so
the cutover cannot silently revert.

### Three findings from the design review

Recorded because each was a defect in a previous version of this plan.

1. **A read verb with a write side effect.** `list(take)` was the earlier answer to
   `claim`. Fusing the read a worker performs anyway with the atomic take is
   correct, but it must default off, state in its description that it can change
   state, and return an empty result rather than a duplicate when it loses the
   race.
2. **The recovery hold needs a stated reason, not a role gate.** See rule 4 above.
3. **A generic `status` field is not a state machine.** `reopen` was folded into
   `update(status=pending)` because its only real precondition — no live
   dependent — is a rule on that transition, not a separate verb. A separate verb
   would have made the model learn two paths for one change. What must never happen
   is letting `update` accept an arbitrary status; the accepted set is closed and
   any transition missing from it is a bug, not an extension point.

## Naming

Registry checked against the anonymous npm registry. Per the established naming
ladder (prefer an available unscoped name; otherwise `@fradser/<name>`; never
invent a `-fradser` suffix):

| Package | Unscoped | Verdict |
| --- | --- | --- |
| subagents | `pi-subagents` taken (`nicobailon`); `pi-subagent` **available** | Recommend `@fradser/pi-subagents`. `pi-subagent` is one character from a published package in the same ecosystem with the same purpose — an install typo in either direction is a real support and trust problem, and that outweighs the unscoped-name preference. |
| task | `@fradser/pi-tasks` **available**; `@fradser/pi-taskss`, `pi-work` taken | `@fradser/pi-tasks` is acceptable unscoped. `@fradser/@fradser/pi-tasks` if consistency across the three is preferred. |
| agent-teams | `pi-agent-teams` taken; `@fradser/pi-agent-teams` already published at 0.10.0 | Keep. A published name is permanent. |

### Tool names

The tool is `task`, not `work`. The package was already `pi-tasks` and the internal
type was already `BoardTask`, so `work` was the only name in the set that
contradicted the other two. `work` is also a mass noun, so a model reading
`work` plus an `action` parameter has to decide whether the tool performs work or
registers work items — which is the source of the double-track confusion at the
name level rather than the behavioural level. `agent` and `task` also form a
consistent noun pair.

Checked against every tool registered in this repository: no package registers
`task` or `message`, and plan-mode's collision set is built-ins only.

## Testing decisions

- Each new package gets its own `features/` and `tests/`, following the existing
  Given/When/Then → RED → GREEN convention. Existing feature files move with
  their concern; `agent-memory-abstraction.feature` moves to `subagents` and
  finally loses its `@unimplemented` tag at step 6.
- The existing Python suites stay authoritative for composed behavior. Do not
  weaken an assertion to make a move pass; a failing assertion after a move is
  evidence the seam is wrong.
- New feature files required, in step order: spawn env policy leaks no secret
  (1); standalone `@fradser/pi-tasks` with no child process (5); workspace durability and
  one stable path per Agent across attempts (7); project memory resolves to the
  main checkout from a linked worktree (7); resumed-session authority isolation
  — a prior attempt's history cannot act as current authority (8); Agent Memory
  write gate, traversal and symlink rejection, and rejection of a
  project-specific fact posed as a general capability (9); sandbox profile
  derivation from the tool grant plus truthful reporting on a non-enforcing
  platform (10); budget and depth fail-closed behavior (11).
- `tests/test_prompt_budget.py` imports `packages/agent-teams/src/guidance.ts`
  by path and must be updated at step 3-5 as guidance splits three ways.
- Runtime changes need `pnpm check:install` plus live `pi --print` verification;
  console and widget changes need interactive TUI checks.

## Out of scope

- Nested multi-level teams beyond the depth guard's default of 2.
- `Routine` (scheduled/external triggers). `CONTEXT.md` scopes cross-session
  background execution out of the current redesign.
- `Computer Lease` kinds beyond the local durable worktree — cloud computers,
  isolated browsers, Firecracker/microVM hosting. The profile abstraction leaves
  room for them; none is proposed here.
- Muse's credential surrogation, host-side Auth Daemon, and eBPF taint tracking.
  A local tool has no trust boundary that justifies them; the env policy at step
  1 is the proportionate substitute.
- `Capability Grant` progressive disclosure and `Takeover`. The vocabulary
  exists in `CONTEXT.md`; no implementation is proposed.
- **A work-history index.** Explicitly rejected: the Pi session already records
  what the Agent did in its workspace, and a second index would duplicate it and
  drift from it. Memory Proposals cite their own evidence instead.
- Cross-session P2P between independently launched terminal sessions — that is
  `docs/RFC-cross-session-communication.md`, a separate generalization.
- Adopting `pi-subagents`' mission/schedule/workflow/lane layer.
- Changing the public tool names. **Now RESOLVED and removed from this list**: the
  names are `agent`, `task`, `message`, and `/agent-teams`, changed deliberately
  and landed as `1.0.0`. The two team tools were renamed and the action set was
  reduced from fourteen actions across two divergent schemas to nine actions
  across one; see "The final tool design". `/agent-teams` is unchanged.

## Open decisions requiring authorization

1. **Naming** — RESOLVED. `@fradser/pi-subagents` and `@fradser/pi-tasks` are
   confirmed. The tool is `task` and the communication tool is `message`; see
   "Tool names" above and `CONTEXT.md`.
2. **Breaking-change policy** — RESOLVED. `1.0.0`, no compatibility layer. The
   original question was whether the tool surface changed; it now does, so `0.11.0`
   is not available. The memory notes and `unified-work-interface.feature` both
   favor an explicit hard cutover, and the cutover is pinned by boundary tests
   that refuse every removed name.
3. **Memory writes on by default** — should a write-capable Agent append to its
   own `MEMORY.md` without an explicit `memory: true` in its definition?
   `pi-subagents` requires opt-in frontmatter; that is the safer default.
4. **Workspace location — a convention owned by another package.** Durable
   per-Agent workspaces at `~/.pi/agent/workspaces/<agent>/<project>/` conflict
   with the established convention that Git worktrees live under
   `.pi/worktrees/<name>`, which `@fradser/pi-utils` owns
   (`packages/utils/extensions/worktree.ts`, with
   `worktree-completion.ts` hiding `.pi/worktrees/**` from file completion).
   Either extend the utils convention to cover durable agent workspaces, or keep
   the in-repo location and accept that a cross-project Agent has no single home.
   The first is recommended; it needs a coordinated change in `utils`.
5. **Workspace retention and reclamation.** A durable workspace is not deleted on
   completion, so it needs an explicit lifecycle: when an Agent is deleted, when
   a project is removed, and whether an idle workspace is ever reclaimed. Its Pi
   session group and its provisioned dependencies are reclaimed with it. The
   existing 7-day `STATE_DIR_MAX_AGE_MS` runtime-dir cleanup must *not* be
   extended to cover workspaces — that would silently destroy working memory.
6. **Sandbox enforcement policy on unsupported platforms.** When no kernel
   primitive is available (Windows today), does a `strict` or `read-only` grant
   fail closed — refuse to spawn — or spawn with a truthful "filesystem isolation
   only" warning? Fail-open with honest reporting is recommended for `workspace`,
   fail-closed for `read-only`, since a read-only reviewer that can write
   invalidates the reason it was chosen.
7. **`pi-kit` growth** — RESOLVED, and my first answer was wrong. I proposed
   adding `packages/kit/src/worker-runtime.ts` and re-exporting it from
   `src/index.ts`, on the grounds that `packages/kit/index.ts` is only
   `export * from "./src/index.ts"` so the public surface would not change.
   That would have broken a documented invariant: `src/index.ts` states that
   everything lives in one file **on purpose**, because a zero-internal-import
   module resolves identically under Node's native type stripping, tsx, pi's
   extension loader, and tsc with any `moduleResolution` — no extensionless
   specifier or `allowImportingTsExtensions` edge cases. A sibling module plus a
   relative re-export reintroduces exactly that edge case. The primitives are
   appended to `src/index.ts` instead (now 2602 lines), and two tests pin the
   layout so the invariant cannot be broken accidentally later. Splitting
   `kit/src/index.ts` into modules is therefore a larger decision than step 2
   warrants: it needs a loader-compatibility argument, not just a file-size one.
