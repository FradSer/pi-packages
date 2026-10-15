# Repository context

Agent Teams models durable AI Agents that can work across projects, develop their own capabilities, and execute project work through isolated replaceable sessions. `packages/loop` adds scheduled self-prompting to one session.

Latest state only. Superseded evidence, old verification totals, resolved incidents and retired session handles live in git and in `docs/history/CONTEXT-archive-20261002.md`.

## Current state

- 2026-10-03 subagents audit complete: all 27 source modules and the feature/test surface are inspected. The final parent-isolation candidate passes its full package check set with unchanged source/manifest/feature/fixture/guidance hashes. Native concurrent parents and actual parent-session reopening pass; fresh independent review closes all scoped findings. The user's independent-history policy is implemented; identity Memory and scratch remain shared. Explicit standalone agent_message progress stays separate from final results. Cold startup uses a 30-second confirmation window; controls for running children retain five seconds. Typecheck, packed manifests and installation pass. Read @packages/subagents/tests/e2e-verification.md for current evidence and unrelated consumer failures.
- Dependency cohort is Pi 1.0.0: root and split manifests `^1.0.0`, installed and locked 1.0.0. The 0.99.2 and 0.8x cohorts and all their counts are superseded.
- The five-tool subagent interface, Markdown result rows, and native stream recovery are locally complete. Read @packages/subagents/tests/intent-interface-verification.md for scoped evidence and source hashes.
- Test simplification is complete. Production source hashes remain unchanged.
- Root/kit typechecks, packed manifests, installation, and diff checks pass. Unrelated task-contract checks still fail; no whole-workspace clean result is claimed.
- 2026-10-15 `packages/loop` (`@fradser/pi-loop`) is implemented on branch `pi/worktree/loop`: `/loop <request>` repeats one message into the session through `pi.sendUserMessage`, so every repetition is a real user turn. Explicit flags call no model; a free request is resolved by pi-kit `askSystemOne` choices over candidates that code builds. Read @packages/loop/README.md for the surface and @packages/loop/features/loop.feature for the contract.

## Active work

- E2E review finds two P2 gaps. RED regressions reproduce complete intent-only clearing and swallowed stop failures; fixes retain selections and make outer evidence assertions own acceptance.
- Resumed final verification passes, including the configured print/TUI cases; typecheck, packed manifests, installation and diff checks pass.
- Eight scoped source/fixture hashes stay unchanged during final checks. No retained test processes remain. Read @packages/subagents/tests/e2e-verification.md for current scope and limits.
- E2E completion is held on independent review turn 2. Task attempt records this missing result as a blocker; no failure verdict is inferred. Session:review-subagents-e2e:6c03bf14-655c-4663-88e0-86c3df7ab81c remains dispatched; await delivery, never poll or duplicate.
- Test simplification remains complete. Read @docs/research/test-suite-simplification-20261002.md for its historical unchanged-runtime evidence.
- Five-tool implementation remains complete. Model A/B performance and external gateway availability remain unverified.
- Tool-boundary review remediation (in progress): three review blockers are fixed (late hosted ACK rebinding, missing pending-startup close binding, dropped cancelled failures), plus one eager-binding overwrite. Reviewer turn3 closure is pending.
- Tool-definition optimization: agent-input and agent-output modules and child-tool activation landed, with bounded readback budgets and defined cancellation semantics. Original review3 blockers were independently closed in turn2, which found one new eager-binding P1. Four synchronous reentry cases reproduced RED, then binding checks ANY existing owner before set/pin, including the same host object; later confirmation requires retained original owner. The scoped read-only review is `session:review-agent-boundary:703e6288-34ea-40f6-96a0-68b1124a0306`.
- Latest full local subagents verification completed above. The prior362s grouped run was interrupted; its undelivered results are not counted. Independent review turn3 closure is still pending, with no polling or replacement. Broader hosted-controls/fork-review gaps remain separate and unclosed.
- 2026-10-15 loop verification against the real service and a real terminal: twelve labelled free requests were resolved by the live decision service (model `jev-1.13.0`) — interval 10/10, runs 4/4, and, after the count-segment fix, stop 10/10 and message 10/10, with the two genuinely ambiguous requests refused rather than guessed. Usage: a plan costs 1-2 requests and 1058-1611 input tokens in under 1.1 s (median 755 ms), and one `met` judgment costs 394 input tokens, so an eight-hour five-minute loop with a judged condition is about $0.0165 at the vendor's $0.42 per million input tokens, output not charged. The delivery refusal is defensive on all four replacement paths (`ctx.reload()`, `ctx.newSession()`, `ctx.fork()`, `ctx.switchSession()`), and the start and status rows were verified in a real Terminal.app window at 120x40, 48x24 and 48x12, where the terminal's accessibility text carries both rows. Read @packages/loop/AGENTS.md for the three explicit-run probes; VoiceOver speech, hardware terminals and other emulators stay unverified. Both review rounds' findings are fixed on the branch: a brace token outside the closed placeholder set is refused at start, a delivery call that throws is reported as undelivered and ends the loop, `README.zh-CN.md` carries the package section, the documented `/loop status` wording matches the code, `tests/test_loop_hygiene.py` runs the harness typecheck, and `CONTEXT.md` is repository level.

## Open blockers

- Real user-history migration stays dry-run until an independent current-candidate review arrives. The dry-run plan is READY: one flat `calc-check` definition and one old private session, no conflicts. The migration module is implemented and tested; no user data was changed.
- Reviews that returned an empty Session Result (resident-final-review, review-memory-fork-fix) are not verdicts. Never infer a PASS from an empty result, and do not poll or read child session files to wait.
- Latest `pnpm check:install` passes. Reload is needed to load new renderer and recovery extension code; existing children do not acquire new extensions.
- The repository-root suite reports one failure at this revision: `tests/test_runtime_workspace_contracts.py` wants `typebox` declared as a `*` peer of `packages/continual-learning`. The branch does not touch that package, and `pnpm check:install` of this worktree is not evidence about the main checkout's settings.
- Pull request 43's own Quality run had not concluded on the reviewed candidate. The five most recent Quality runs on `main` all failed for unrelated reasons.

## Decisions (current)

- 2026-10-03 user choice: each parent session uses independent durable child history. Native Pi session IDs select parent/project partitions; reopening the same parent resumes its own history. Identity Memory and scratch remain shared. Old project-only history stays untouched and is not automatically imported. Native concurrent-parent and actual-session-reopen verification passes. Different logical parents use separate history; concurrent copies of the same parent ID share one partition, without an ownership lock.
- Disk-defined identity: durable `<name>/agent.md` homes with Agent Memory, ordinary workspaces and project-scoped history. Project overrides are `.pi/agents/<name>/agent.md` and `<name>.local/agent.md`. No model-facing persistent, memory or worktree flags; inline roles stay in memory; no promotion and no git-worktree machinery. Authority: @packages/subagents/VISION.md and @packages/subagents/AUTHORITY.md.
- A temporary child stays IDLE after every result and accepts the next input until it is stopped or its parent exits. Stop and parent shutdown close it.
- 2026-10-04 user decision: the intent family is the only child tool surface. The `agent` tool, its six-action API, its selection flag and its uppercase receipts are retired under @docs/adr/0008-retire-the-legacy-agent-tool.md. The shared executor is `executeChildIntent` with operations `start | input | steer | inspect | list | stop`. A branch that recorded `agent` now receives the intent family. Model availability is not authorization.
- 2026-10-05 user decision: `agent_inspect` is retired too. The intent family is `agent_start`, `agent_input`, `agent_stop`, `agent_list` plus `subagents_enable`; the executor operations are `start | input | list | stop`, with `input` carrying `delivery: "next" | "steer"`. The roster is a status summary and the child's answer arrives with its Session Result. `RETIRED_TOOLS` in `src/tool-activation.ts` scrubs both retired names from a recorded selection. A settled child leaves the above-editor activity area but stays addressable, and a reported answer is expansion detail: the collapsed row is the headline plus the expand affordance.
- 2026-10-04 user decision: one result paints one collapsed row, `[tool] label · @name · status`, with the name once and the state word not repeated when the label carries it. A roster row reads `[agent] listed · @children · N of M`. Everything else is expansion detail, and one fact never appears twice in a row.

## Subagents legacy retirement

Complete, and the five-tool surface above supersedes this record: `src/agent-tool.ts` became `src/child-execution.ts` with `executeChildIntent`, the `agent` registration, `AGENT_TOOL_PARAMS`, `AGENT_CAPABILITY_TOOLS`, `agentRowSpec` and the legacy interface flag are deleted, receipts use the lowercase row vocabulary and the child's display label, and the harness recipes that cleared the last failures stay in git history. Authority: @docs/adr/0008-retire-the-legacy-agent-tool.md.

## Packages

The vocabulary below is split by owning package. Each term is implemented by exactly one package, and no package names a participant it does not own.

| Package | Owns | Model-facing surface |
| --- | --- | --- |
| `@fradser/pi-subagents` | Agent execution, Session Result, private history and Memory | `agent_start`, `agent_input`, `agent_stop`, `agent_inspect`, `agent_list`, `subagents_enable` |
| `@fradser/pi-tasks` | Task, Task Status, Recovery Hold, Submission, Task Acceptance | `create_task`, `get_task`, `list_tasks`, `update_task` |
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
A session-scope in-memory actor with no disk `agent.md`, Agent Memory, private
workspace or persisted history. It becomes IDLE after results and accepts send
until stopped or its parent exits. It cannot be promoted or retroactively persist
its earlier conversation.
_Avoid_: Persisted Agent, promotion, automatic one-shot close

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
One durable unit of work recorded by a person, Routine, external event, or Agent handoff. A Task states what must be done and under which completion requirements; it never states who must do it. Ownership is derived from action and never declared, so a Task carries no assignee and any Agent or the main session may take it.
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
Exclusive external resource authority granted to one Work Session. The subagent
package now provisions only ordinary scratch folders: no Git worktree, branch,
automatic commit or write isolation. Broader resource leases remain coordinator
concepts, not an execution-layer workspace promise.
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

**Session Result**:
The settled output one Work Session turn produced for the work it was given, handed to the Leader's session once per settled turn. It carries that turn's final answer verbatim and names its Agent and Process Incarnation; it is not a claim that the work was accepted, and an ended Process Incarnation whose turn produced none says so without requiring a turn.
_Avoid_: Submission, Message, Agent Presence, report receipt, progress update

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
