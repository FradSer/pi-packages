# Specification: Agent Teams Persistent Agents (Slice 1 — Core Delegation & Shared Communication)

Status: prior design target, not a complete implemented contract. For the next coordination interface and its delivery plan, use @SPEC-unified-work.md and @PLAN-unified-work.md; they retain advanced Work control and supersede this document's two-tool and automatic Temporary Agent assumptions for that slice.

## Problem Statement

Users need to delegate engineering responsibilities to named, persistent AI Agents across projects. Today, `@fradser/pi-agent-teams` models teammates as session-bound child processes started with `--no-session` and terminated on leader session shutdown. When a session ends or switches projects, the agent's identity, context, and standing responsibility vanish. Furthermore, leader and worker coordination currently relies on seven low-level tools with disparate completion and assignment semantics across direct kickoff and task board workflows.

## Solution

Transform `packages/agent-teams` into an Agent-first coordination system. An Agent is a durable cross-project entity whose definition at user scope establishes persistent identity and whose project definitions specialize that identity. Work is represented uniformly as durable Work Items executed inside isolated Work Sessions with replaceable Process Incarnations. Coordination converges on two symmetric, minimal tools:
1. `agent({ name, prompt?, work? })` for delegation and work control.
2. `agent_event({ message, to?, status? })` for shared, role-independent bidirectional communication.

Project facts and decisions remain in Project Memory, while each persisted Agent owns a dedicated memory folder for generalizable capabilities, methods, and operating patterns.

## User Stories

1. As a project leader, I want to delegate a task to a named Agent using `agent({ name, prompt })`, so that the Agent executes the assignment in an isolated Work Session without requiring manual process spawning.
2. As a project leader, I want an existing user-scoped Agent definition to be available across different projects, so that I can reuse the same coworker identity and capabilities everywhere.
3. As a project leader, I want a project-scoped Agent definition to specialize a same-named user Agent, so that project-specific instructions apply without destroying the Agent's durable cross-project identity.
4. As a project leader, I want delegating to an unknown Agent name to create a Temporary Agent, so that exploratory work proceeds without upfront definition ceremony.
5. As a project leader, I want to automatically promote a Temporary Agent to a persistent user Agent after an evidence-verified high-quality outcome, so that valuable roles are retained effortlessly.
6. As a project leader, I want to inspect an Agent's presence via `agent({ name })` without providing a prompt, so that I receive an immediate status projection without spending model tokens or triggering an unnecessary agent turn.
7. As a project leader, I want to provide steering to an existing Work Item via `agent({ name, prompt, work })`, so that the active Work Session receives directed guidance without creating an orphaned duplicate task.
8. As a worker Agent, I want to send updates, questions, and completion reports using `agent_event({ message, to?, status? })`, so that I use the exact same communication protocol regardless of whether I am addressing a leader or peer.
9. As a leader session, I want to send messages using `agent_event({ message, to, status? })`, so that leader-to-worker communication uses the same message protocol as worker-to-leader and peer-to-peer mail.
10. As a worker Agent, I want my sender identity and Work Session binding to be injected by the runtime environment, so that I cannot forge or misattribute my events.
11. As a worker Agent handling concurrent tasks across projects, I want replies to preserve their originating work context and reply route, so that communication in Project A never bleeds into Project B.
12. As a worker Agent, I want to omit `to` only when a unique bound reply route exists, so that my message is never misdelivered to an arbitrary session.
13. As a worker Agent, I want my Assignment Attempt to remain active until explicit verification passes, so that premature completion claims do not release work before verification.
14. As a persisted Agent, I want my learned capabilities and methods to reside in my own dedicated Agent Memory folder, so that project facts do not pollute my reusable capabilities.
15. As a project maintainer, I want Project Memory to retain project facts, architecture decisions, and history, so that project knowledge is not trapped in individual Agent folders.
16. As an operator, I want to manage Agents and view active Work Sessions through the `/agent-teams` console, so that management controls do not clutter the LLM tool surface.

## Scenarios

See `packages/agent-teams/features/shared-communication.feature` and `packages/agent-teams/features/agent-memory-abstraction.feature` for executable specifications. Additional core delegation scenarios:

```gherkin
Feature: Core Agent Delegation and Work Item Lifecycle

  Scenario: Leader delegates new work to an existing Agent
    Given a persisted Agent named "reviewer" exists in user scope
    When the leader calls agent with name "reviewer" and prompt "Audit auth middleware"
    Then a new Work Item is created with a unique work ID
    And an isolated Work Session starts for "reviewer"
    And the initial result includes Agent Presence showing 1 active Work Session

  Scenario: Leader checks presence of an idle Agent without prompt
    Given an Agent named "reviewer" has no pending inbox messages or active work
    When the leader calls agent with name "reviewer" without prompt
    Then the result synchronously reports status "idle"
    And no new model turn or child process is spawned

  Scenario: Temporary Agent promotion after verified success
    Given work is delegated to an unknown Agent name "data-migrator"
    And "data-migrator" executes as a Temporary Agent without Agent Memory
    When the Work Item passes verification with high-quality evidence
    Then the leader marks the Agent for promotion
    And a user-scoped Agent Definition is created for "data-migrator"
    And a dedicated Agent Memory folder is initialized for "data-migrator"
```

## Implementation Decisions

1. **Dual Tool Seam**:
   - The public model interface consists of exactly two tools: `agent({ name, prompt?, work? })` and `agent_event({ message, to?, status? })`.
   - All other lifecycle transitions (process spawning, lease acquisition, verification gating, memory proposal merging) are private implementations within the core engine.

2. **Work Item and Attempt Identity**:
   - Every delegation creates a durable `WorkItem` record.
   - Execution runs under an `AssignmentAttempt` uniquely identified by `(workItemId, attemptId)`.
   - Process incarnations are ephemeral instances identified by `(attemptId, incarnationId, incarnationEpoch)`.

3. **Runtime-Enforced Correlation and Binding**:
   - `agent_event` calls from worker processes extract `senderAgent`, `workSessionId`, `assignmentAttemptId`, and `incarnationEpoch` from secure process environment variables (`PI_AGENT_*`).
   - Leader calls bind to the current Pi session context.

4. **Storage Architecture**:
   - User definitions: `~/.pi/agent/agents/<name>.md`.
   - Project definitions: `<project>/.pi/agents/<name>.md` (git-managed) and `<name>.local.md` (local override).
   - Agent Memory: `~/.pi/agent/agents/memory/<agentName>/` (capabilities only).
   - Project Memory: Existing Project Memory paths (project facts and history).
   - Work Ledger: `<project>/.pi/work/ledger.jsonl` (atomic append with lock).

5. **No Background Daemon**:
   - Routine and inbox processing executes opportunistically while a leader or worker runtime is active. No external daemon or launchd service is promised or deployed.

## Testing Decisions

- Tests strictly assert behavior at the highest public interface: tool execution through `agent` and `agent_event`, and CLI state in `/agent-teams`.
- Unit tests verify pure state reducers (`WorkLedger`, `AgentDirectory`, `MemoryProposalReducer`) using in-memory adapters.
- Integration tests execute real child processes with mock Pi RPC streams to prove end-to-end delegation without network calls.

## Out of Scope

- Remote cloud computers or third-party VM provisioning (local Git worktree leases serve as the initial workspace adapter).
- Independent background cron broker/daemon running when Pi is shut down.
- Automatic full-text vector embeddings across Agent memory folders.

## Further Notes

- Existing single-writer file locking patterns and stale-event epoch defenses from `src/state.ts` and `src/statefile.ts` will be preserved and migrated directly into the new `WorkLedger` and `AgentDirectory` modules.
