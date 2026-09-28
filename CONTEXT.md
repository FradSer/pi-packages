# Agent Teams

Agent Teams models durable AI Agents that can work across projects, develop their own capabilities, and execute project work through isolated replaceable sessions.

## Packages

The vocabulary below is split by owning package. Each term is implemented by exactly one package, and no package names a participant it does not own.

| Package | Owns | Model-facing surface |
| --- | --- | --- |
| `@fradser/pi-subagents` | Agent, Work Session, Assignment Attempt, Agent Memory, Computer Lease | `agent` |
| `@fradser/pi-tasks` | Task, Task Board, Task Status, Recovery Hold, Submission, Task Acceptance | `task` |
| `@fradser/pi-agent-teams` | Message, Coordination Event, Agent Presence, Team Console | `message` |

`@fradser/pi-agent-teams` is a bundle: installing it loads all three. Each package is also complete on its own.

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

**Task**:
One durable unit of work recorded on the Task Board by a person, Routine, external event, or Agent handoff. A Task states what must be done and under which completion requirements; it never states who must do it. Ownership is derived from action and never declared, so a Task carries no assignee and any Agent or the main session may take it.
_Avoid_: Work Item, Direct assignment, Board Task, prompt-only task, assignee field

**Task Status**:
The lifecycle position of a Task: pending, in progress, completed, or superseded. Moving a Task into progress is the act of taking it, and completion is the only terminal transition for work someone actually did.
_Avoid_: Claimed, state, phase

**Recovery Hold**:
A flag on a Task whose last attempt ended in failure, withholding it from automatic taking until a participant proceeds with a stated reason. It keeps one transient failure from being silently retried by whichever participant happens to be idle, and it is not a Task Status.
_Avoid_: Blocked status, failed status, automatic retry

**Assignment Attempt**:
One authorization for an Agent Work Session to perform or hold a Task, acquired by taking the Task rather than by being named as its owner. It is distinct from Agent identity and from the Task. Each new assignment has a new attempt; completing, reopening, process exit, or stopping retires the old authority before another attempt can acquire it.
_Avoid_: Assignee, pre-declared owner, role grant

**Task Board**:
The shared register of Tasks and their availability, readable and writable by every Agent and by the main session through one interface. It is not a separate kind of work with different completion rules, and it does not dispatch work to a named Agent.
_Avoid_: Work Board, Second work lifecycle, independent task store, dispatch queue

**Submission**:
One candidate result supplied by the current Assignment Attempt, recorded as a success or a failure together with its evidence. An ordinary final answer and an explicit submission represent the same kind of evidence; a blocker reported as prose rather than recorded as a failure is not a failure. A revised result is a new submission, not acceptance of the previous one.
_Avoid_: Completed Task, message status, process exit, prose blocker report

**Task Acceptance**:
The decision that a current submission satisfies its Task's completion requirements, including any verification gate. Acceptance is distinct from execution ending, submitting a result, or integrating changes into another workspace.
_Avoid_: Work Acceptance, Final answer, report receipt, successful shutdown

**Handoff**:
An offered transfer of a Task between Agent Work Sessions, expressed as a Message to the target and finished by the current holder releasing it. The source keeps its resource authority until it releases, so the target cannot begin before then.
_Avoid_: Copy, immediate reassignment, pre-declared owner

**Routine**:
A standing trigger that creates a Task for an Agent from a schedule, external event, or Agent signal while the current Agent Teams runtime is available. Cross-session background execution is outside the current redesign.
_Avoid_: Repeated prompt, polling turn, promised background daemon

**Attention Request**:
A bounded request for human judgment or authorization containing the decision, evidence, recommendation, and allowed choices. Routine progress, ordinary routing, and recoverable execution remain internal rather than becoming Attention Requests.
_Avoid_: Status update, full transcript, generic stall notice

**Capability Grant**:
A user- or project-policy authorization that lets one Work Session use a requested external tool or computer capability. Grants may differ by Agent and Task, and become visible progressively as the Work Session needs them.
_Avoid_: Tool name in a prompt, shared credential, automatic role permission

**Computer Lease**:
Exclusive workspace authority granted to one Work Session. Local worktrees, isolated browsers, and cloud computers are alternative kinds of Computer Lease; one Agent may hold several through isolated Sessions.
_Avoid_: Agent identity, shared mutable desktop, working directory alone

**Takeover**:
An explicit transfer of a Computer Lease from an Agent Work Session to a person. Preview is read-only; Takeover pauses Agent writes until the person returns or ends control.
_Avoid_: Shared control, automatic access, transcript view

**Work Session**:
An isolated execution context of one Agent with at most one current Assignment Attempt. A resident Work Session can be unassigned or serve successive attempts. An Agent's concurrent work uses separate Work Sessions whose prompts, execution state, tools, and uncommitted memory remain isolated.
_Avoid_: Agent identity, shared chat, task thread

**Fresh Work Session**:
A new Work Session that receives its own assignment without inheriting the Leader's conversation history. Agent instructions and authorized capabilities are separate from that history.
_Avoid_: New Agent identity, new process only

**Forked Work Session**:
A new Work Session that inherits a snapshot of the Leader's active conversation context before pursuing its own assignment. It neither continues the Leader's session nor transfers the Leader's execution authority.
_Avoid_: Handoff summary, shared mutable conversation, workspace copy

**Process Incarnation**:
One temporary process executing a Work Session. A Process Incarnation may stop and later be replaced without ending the Agent, Work Session, or responsibility.
_Avoid_: Agent, Work Session, identity, permanent worker

**Agent Inbox**:
The Agent's persistent addressed-message queue. A message may wait with no active Work Session; an available Agent Teams runtime starts a Session only when the message requires a response or creates work.
_Avoid_: Ephemeral process inbox, broadcast transcript, background-daemon promise

**Agent Presence**:
The leader-visible state of an Agent and its Work Sessions, including whether work is queued, starting, active, waiting, blocked, or complete. Presence reports state without requiring a model turn.
_Avoid_: Status polling prompt, raw process telemetry

**Message**:
One point-to-point communication from a participant to a named participant, carrying either an information notice or a request that needs a decision. Sender identity comes from the runtime, and a recipient is addressed by name or by an exact session rather than by a thread or reply reference. A Message is not evidence, is not a broadcast, and does not submit results or change work ownership, acceptance, or lifecycle state.
_Avoid_: Agent Event, thread, reply chain, broadcast, attachment, worker-only report, caller-supplied sender identity

**Coordination Event**:
An asynchronous Message, work intent, verification result, or lifecycle marker that may propose a shared-state transition. Its authority depends on its source and the addressed state; an ordinary Message does not require an Assignment Attempt.

**Historical Evidence**:
A Coordination Event from an Assignment Attempt that is no longer current. It remains in Task history and may support capability-focused Memory Proposals, but cannot propose a current shared-state transition.

**Team Console**:
The interactive surface through which a leader views cross-project Agents, project Tasks, Work Sessions, and coordination history. It presents richer detail without adding model-facing tool parameters.
