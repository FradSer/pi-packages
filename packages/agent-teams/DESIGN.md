# Agent Teams Redesign

## Status

Product direction agreed; the coordination protocol is not yet implementation-ready. [DESIGN-REVIEW.md](./DESIGN-REVIEW.md) records unresolved contracts and proposed simplifications without changing the agreed product requirements. No implementation has started.

## Product model

Agent Teams is organized around cross-project persistent Agents, not leader-session child processes.

- A user Agent Definition establishes a durable Agent identity.
- A project Agent Definition specializes the same named Agent for that project.
- A project specialization without a user Agent creates a Temporary Agent. The leader may promote it automatically after judging its first result high-quality from outcome evidence, verification, and future reuse value.
- A persisted Agent may own several concurrent Work Items. Every Assignment Attempt runs in an isolated Work Session with its own Pi session, Process Incarnation, context, tools, and temporary state.
- Project facts, concrete decisions, and history remain in Project Memory. Agent Memory records reusable capabilities, methods, judgment criteria, and operating patterns, including lessons abstracted from project work; ownership follows the lesson's content and applicability, not its learning location.

## External interface

### Delegation and work control

The coordinating role uses a compact delegation interface. This is not its only tool: Leaders and Workers both use the shared communication interface below.

```ts
agent({ name, prompt?, work? })
```

- `name` resolves a persisted or Temporary Agent.
- `prompt` without `work` creates a new Work Item and isolated Work Session.
- `prompt` with `work` directs guidance to the specified work's current Work Session. Delivery uses the shared communication protocol rather than a separate leader-only transport.
- no `prompt` checks the Agent's persistent inbox and queued Work Items. A Work Session starts only when actionable work exists; otherwise the result synchronously reports `idle`.
- every result includes Agent Presence: an Agent summary plus one compact row per active Work Session. The row identifies its state, Work Item, current action or waiting reason, and next actor.

The interface does not expose Agent creation, promotion, memory, capability grants, Work Session creation, task claiming, verification, routines, preview, takeover, or shutdown as permanent tool parameters. Those concerns stay behind the Agent module or in the Team Console.

### Shared communication

One communication interface for Leader ↔ Worker and Agent ↔ Agent, independent of coordination role or user/project Definition scope:

```ts
agent_event({ message, to?, status? })
```

- the same tool name, parameter meanings, delivery protocol, and routing receipts apply to every participant. There is no Worker-only report tool or Leader-only messaging tool.
- a Leader sender is bound to its Pi session and runtime; it need not own an Assignment Attempt or be a persisted Agent. A Worker sender additionally binds to its Agent, Work Session, Assignment Attempt, and Process Incarnation. Callers cannot supply or forge sender identity.
- `to` addresses a participant or a runtime-provided precise reply route. Agent names reach Agent inboxes; bound Leader routes reach the originating Leader conversation. A reply to one Work Session never fans out to every Session of that Agent.
- omitted `to` is valid only when the runtime supplies one unambiguous reply route. With no route or multiple possible routes, the send is rejected with an explicit-recipient instruction; the runtime does not guess a Leader or the latest Session.
- ordinary messaging is shared. `status` expresses an allowed message intent or state-transition request; state and authority determine which transitions are progressively available, not ownership of the communication tool. Message intents include `inform` and `request`; completion, handoff, and memory proposals require their own valid bindings and authorization.
- `inform` alone does not create a model turn in an inactive recipient. A `request` may queue actionable work under existing policy; delivery is not permission to change ownership. Handoff still requires target acceptance and validated transfer.
- an ordinary Leader or Worker message does not itself complete work, replace its owner, or grant capabilities. Shared communication is not shared unrestricted control.

The redesign acceptance contract is recorded in [features/shared-communication.feature](./features/shared-communication.feature), tagged as unimplemented. Other state-transition contracts remain subject to the design review.

## Deep modules

### Agent Directory

Owns Agent identity, Definition resolution, Temporary Agent lifecycle, promotion, Agent Memory location, persistent inbox, and Agent Presence projection.

Its interface hides user/project discovery, project specialization, Definition version pinning, storage, promotion evidence, and process incarnations.

### Work Ledger

Owns the single Work Item lifecycle for work created by a person, Routine, external event, or Agent handoff. It replaces direct assignments and Board Tasks.

It contains resource conflicts, dependencies, supersession, ownership, Assignment Attempts, verification, terminal state, and historical evidence. Existing single-writer reducers and stale-event protections migrate here.

### Work Session Runtime

Creates isolated Pi sessions and replaceable Process Incarnations for Assignment Attempts. One Agent may run several Work Sessions concurrently without sharing prompt context, process state, active tools, or uncommitted memory.

A Process Incarnation ending does not delete the Agent, Work Session, or Work Item. No permanent background daemon is part of this redesign; Process Incarnations run only while an Agent Teams runtime is available.

### Agent Memory

Every persisted Agent owns a dedicated folder. The folder contains capability-focused memory only:

- capabilities the Agent has demonstrated;
- reusable methods, procedures, and judgment criteria, including lessons abstracted from project experience;
- execution preferences and operating patterns;
- project-safe evidence references and merge metadata for those claims.

Memory ownership follows what was learned, not where it was learned. A project may retain the concrete decision and its history while the Agent separately retains the reusable lesson derived from it. This is abstraction, not copying or moving the project record.

It must not contain project-specific facts, decisions, history, or per-project subfolders. Those records and raw evidence remain in the existing Project Memory or originating Work Item. Evidence references do not authorize automatic loading of source project material into another project's Session.

Concurrent Work Sessions never write Agent Memory directly. They submit versioned, evidence-backed Memory Proposals. Project origin alone does not disqualify a proposal: review checks whether its content is genuinely reusable, retains relevant assumptions and limits, and excludes project-specific material. Removing names alone does not turn a local choice into a general rule. The Agent-level serial reducer resolves duplication/conflicts, automatically merges sufficiently supported low-risk preferences, and requires human approval for high-risk rules.

Temporary Agents do not receive an Agent Memory folder until promotion. Promotion and approval of any abstracted lesson remain separate decisions.

The intended distinction is captured in [features/agent-memory-abstraction.feature](./features/agent-memory-abstraction.feature), tagged as unimplemented.

### Capability Resolver

Agent Definitions describe capability intent. A Work Item determines the initial minimum tools. User/project policy authorizes Capability Grants, and a Work Session may progressively load more approved capabilities as needed.

The current Pi built-ins are the first adapter. Local worktrees, isolated browsers, cloud computers, external connectors, and other tool sources can become adapters only when they actually exist; the architecture must not claim unsupported capabilities.

### Computer Lease Manager

Every Work Session receives its own Computer Lease. The first adapter is the current local Git worktree. Future isolated-browser or cloud-computer adapters may satisfy the same seam.

Human access follows:

1. Status: safe presence only.
2. Preview: bounded read-only activity and artifacts.
3. Takeover: pause Agent writes, transfer control atomically, audit the transition, and resume only after control is returned.

### Runtime Coordinator

Consumes persistent Agent inbox entries, Work Items, Routine triggers available inside the current runtime, verification outcomes, and Process Incarnation events. It starts Work Sessions only for actionable work and returns state transitions rather than making callers orchestrate them.

It notifies the user only for an Attention Request or an important final result. Ordinary progress, routing, retry, and recoverable execution remain internal.

## State contracts

### Agent

- globally stable identity across projects;
- user Definition is the identity source;
- project Definition specializes the same identity;
- zero or more concurrent Work Sessions;
- one dedicated Agent Memory folder after persistence;
- one persistent addressed inbox.

### Work Session

- belongs to exactly one Agent and Assignment Attempt;
- pins the resolved Agent Definition version;
- has one isolated Pi session and at most one live Process Incarnation;
- obtains its own Capability Grants and Computer Lease;
- may be replaced/recovered without changing Agent identity.

### Work Item

- has exactly one current owner Assignment Attempt;
- handoff is an offer until the target accepts;
- resource authority stays with the source until atomic acceptance;
- completion remains gated by verification when configured;
- late events are Historical Evidence and cannot mutate current state.

### Agent Promotion

- a new name first creates a Temporary Agent;
- the Temporary Agent completes the current Work Item without Agent Memory;
- final synthesis by the leader judges quality using result evidence, verification, and reuse value;
- one high-quality result may promote it automatically;
- promotion defaults to a user Agent Definition so it can work across projects;
- a clearly project-specific specialization remains in the project Definition.

## Storage ownership

Exact paths remain an implementation decision, but ownership is fixed:

- user Agent Definitions: persistent identity declarations;
- project Agent Definitions: same-name specializations;
- each persisted Agent: its own private Agent Memory folder and inbox/history state;
- each project: existing Project Memory and project Work Ledger;
- each Work Session: isolated Pi session and replaceable runtime state.

Secrets and external connection references never enter Agent Definition, Agent Memory, Project Memory, or prompts.

## Team Console

`/agent-teams` becomes the human management interface and uses the existing `ctx.ui.custom` pattern.

Primary views:

- Agents: cross-project identity, capability summary, inbox, active Work Sessions;
- Work: current project's Work Items, ownership, verification, handoffs;
- Attention: only decisions or authorizations requiring the user;
- Memory: Agent capability memory and pending proposals, clearly separate from Project Memory;
- Diagnostics: Process Incarnations, usage, raw events, tool grants, and adapter details;
- Computer: Status, Preview, and Takeover when a real adapter supports them.

The passive widget remains display-only and shows active Work Sessions. It does not intercept input or expose idle Agents as permanent visual noise.

## Removed concepts

The redesign removes these as public orchestration concepts rather than preserving parallel compatibility paths:

- `teammate_spawn` and `teammate_shutdown`;
- separate direct assignment and Board Task protocols;
- `task_create`, `task_list`, `task_claim`, and `task_submit` as model-facing coordination tools;
- `handoffFrom` prompt synthesis;
- session-scoped generated roles as the default identity model;
- process name as durable identity;
- project facts inside Agent Memory;
- a promised persistent Routine broker or daemon.

## Delivery slices

Implementation should grow in working vertical slices. Every behavior begins with a `.feature` scenario, then a failing test, then implementation.

1. Agent Directory and domain state: cross-project persisted Agent, project specialization, Temporary Agent, Definition pinning, Agent Presence.
2. Unified Work Ledger: migrate direct/board invariants, Assignment Attempt identity, resources, verification, supersession, and accepted handoff.
3. Isolated Work Sessions: one Pi session per Assignment Attempt, concurrent Sessions per Agent, replaceable Process Incarnation.
4. Minimal tools: use `agent` for delegation/work control and the same `agent_event` communication interface for Leaders and Workers; keep execution capabilities and advanced transitions progressively disclosed.
5. Agent folders and memory reducer: capability-only Memory Proposals, serial merge, project-fact rejection, promotion-created folder.
6. Persistent Agent inbox and Agent-to-Agent communication: `inform`, `request`, and acknowledged `handoff`.
7. Capability resolution and current built-in adapter; then local worktree as the first Computer Lease adapter.
8. Team Console projections, Attention Requests, Preview, and Takeover only for supported adapters.
9. Routine intents limited to the lifetime of the available Agent Teams runtime.
10. Remove obsolete teammate/task interfaces and documentation, add a Changeset, run package and monorepo verification, install live, and smoke the new surface in Pi.

## First implementation acceptance scenarios

The first slice is not complete until these behaviors hold:

- a user Agent is visible from two projects as the same stable identity;
- a project Definition specializes it without creating another identity;
- a project-only Definition creates a Temporary Agent until promotion;
- one Agent can own two concurrent Work Items through isolated Work Sessions;
- each Work Session pins a Definition version and rejects stale Process Incarnation events;
- Agent Presence reports all active Work Sessions without model polling;
- Temporary Agents have no Agent Memory folder;
- project facts cannot enter an Agent Memory Proposal;
- no background broker or cross-session Routine execution is claimed.
