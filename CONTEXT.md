# Agent Teams

Agent Teams models durable AI Agents that can work across projects, develop their own capabilities, and execute project work through isolated replaceable sessions.

## Language

**Agent**:
A persisted AI coworker with a stable identity, capability-focused Agent Memory, and work history that may span projects. Project definitions specialize the Agent for a project without turning it into a project-owned identity.
_Avoid_: Teammate, Bot, worker, sub-agent, resident process

**Leader**:
The coordinating role responsible for delegation and synthesis in a work context. A Leader can send and receive the same communications as Workers; the role is not a separate Agent identity or Definition scope.

**Worker**:
The executing role of an Agent Work Session for an Assignment Attempt. Workers can communicate with their Leader and peers through the same shared communication language.

**Temporary Agent**:
A one-off actor created when work names no persisted Agent. It receives an isolated Work Session but owns no Agent Memory; repeated use or demonstrated work quality may promote it automatically into a persisted Agent.
_Avoid_: Persisted Agent, anonymous Work Session

**Agent Promotion**:
The transition from a Temporary Agent to a persisted Agent after the leader judges its result high-quality from outcome evidence, verification, and future reuse value. Promotion creates a stable identity and enables Agent Memory.
_Avoid_: Self-promotion, spawn, routine activation, memory proposal

**Agent Definition**:
The versioned declaration of an Agent's identity, responsibility, instructions, and requested capabilities. The user definition is the persistent identity source; a project definition only specializes that same Agent, and each Work Session pins the resolved version.
_Avoid_: Role Template, project-owned identity, spawn configuration

**Project Memory**:
Durable facts, concrete decisions, and history of one project, available independently of any particular Agent. Abstracting a reusable lesson does not move or replace the originating project record.
_Avoid_: Agent Memory, complete chat history

**Agent Memory**:
Private durable knowledge of a persisted Agent's reusable capabilities, methods, judgment criteria, and operating patterns, including abstractions learned through project work, kept in the Agent's own folder. Project-specific facts, decisions, and history remain in Project Memory; Temporary Agents have no Agent Memory.
_Avoid_: Project archive, per-project subfolder, shared memory folder, complete chat history, session scratch state

**Memory Proposal**:
A versioned, evidence-backed candidate for Agent Memory that describes a reusable capability or abstracted lesson with its applicability and limits. Its learning source may be a project, but its content does not carry that project's concrete facts, decisions, or history.
_Avoid_: Direct memory write, project fact, unqualified generalization, self-reflection log

**Work Item**:
One durable piece of work created by a person, Routine, external event, or Agent handoff. All work follows the same ownership, resource, verification, and completion language.
_Avoid_: Direct assignment, Board Task, prompt-only task

**Assignment Attempt**:
One authorization for an Agent Work Session to perform or hold a Work Item. It is distinct from Agent identity and the Work Item; replacing, reopening, releasing, or reclaiming work creates a new Assignment Attempt.

**Handoff**:
An offered transfer of a Work Item between Agent Work Sessions. The source remains owner and keeps its resource authority until the target accepts and ownership changes atomically.
_Avoid_: Peer message, copied task, immediate reassignment

**Routine**:
A standing trigger that creates a Work Item for an Agent from a schedule, external event, or Agent signal while the current Agent Teams runtime is available. Cross-session background execution is outside the current redesign.
_Avoid_: Repeated prompt, polling turn, promised background daemon

**Attention Request**:
A bounded request for human judgment or authorization containing the decision, evidence, recommendation, and allowed choices. Routine progress, ordinary routing, and recoverable execution remain internal rather than becoming Attention Requests.
_Avoid_: Status update, full transcript, generic stall notice

**Capability Grant**:
A user- or project-policy authorization that lets one Work Session use a requested external tool or computer capability. Grants may differ by Agent and Work Item, and become visible progressively as the Work Session needs them.
_Avoid_: Tool name in a prompt, shared credential, automatic role permission

**Computer Lease**:
Exclusive workspace authority granted to one Work Session. Local worktrees, isolated browsers, and cloud computers are alternative kinds of Computer Lease; one Agent may hold several through isolated Sessions.
_Avoid_: Agent identity, shared mutable desktop, working directory alone

**Takeover**:
An explicit transfer of a Computer Lease from an Agent Work Session to a person. Preview is read-only; Takeover pauses Agent writes until the person returns or ends control.
_Avoid_: Shared control, automatic access, transcript view

**Work Session**:
An isolated context in which one Agent performs one Assignment Attempt. An Agent may hold several concurrent Work Sessions, but their prompts, process state, tools, and uncommitted memory remain isolated.
_Avoid_: Agent identity, shared chat, task thread

**Process Incarnation**:
One temporary process executing a Work Session. A Process Incarnation may stop and later be replaced without ending the Agent, Work Session, or responsibility.
_Avoid_: Agent, Work Session, identity, permanent worker

**Agent Inbox**:
The Agent's persistent addressed-message queue. A message may wait with no active Work Session; an available Agent Teams runtime starts a Session only when the message requires a response or creates work.
_Avoid_: Ephemeral process inbox, broadcast transcript, background-daemon promise

**Agent Presence**:
The leader-visible state of an Agent and its Work Sessions, including whether work is queued, starting, active, waiting, blocked, or complete. Presence reports state without requiring a model turn.
_Avoid_: Status polling prompt, raw process telemetry

**Agent Event**:
A shared communication sent by a Leader or Worker to report information, contact another participant, or request an allowed state transition. Sender identity and work context come from the runtime; the ability to communicate does not grant authority to change work state.
_Avoid_: Worker-only report, role-specific messaging, caller-supplied sender identity, free-form inferred completion

**Coordination Event**:
An asynchronous Agent Event, work intent, verification result, or lifecycle marker that may propose a shared-state transition. Its authority depends on its source and the addressed state; an ordinary Leader message does not require a Worker Assignment Attempt.

**Historical Evidence**:
A Coordination Event from an Assignment Attempt that is no longer current. It remains in Work Item history and may support capability-focused Memory Proposals, but cannot propose a current shared-state transition.

**Team Console**:
The interactive surface through which a leader views cross-project Agents, project Work Items, Work Sessions, and coordination history. It presents richer detail without adding model-facing tool parameters.
