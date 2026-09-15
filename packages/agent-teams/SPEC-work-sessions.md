# Compact Agent delegation with independent Work Sessions

Status: confirmed for implementation. Tracker: package-local specification, as selected by the user; no remote issue or repository-wide tracker setup. Label: ready-for-agent.

Next-slice pointer: @SPEC-unified-work.md retains this slice's independent/forked execution guarantees while replacing work-ID steering and direct-only submission with the unified Work interface. This document continues to describe the earlier implemented slice.

## Problem Statement

A concise Agent interface currently chooses between creating work and steering a resident based on process liveness. It cannot run two independent delegations to the same Agent or inherit the Leader's actual context. Workers must explicitly report terminal status even when their ordinary final answer already contains the result.

## Solution

Keep agent and agent_event. A prompt without work always creates an independent Work Session. A work ID selects an existing Work Session. Add only optional fork, default false; true seeds new work with an immutable snapshot of the Leader's active conversation context. The runtime automatically delivers an ordinary final answer when execution settles.

## User Stories

1. As a Leader, I want each new delegation to create independent work even when the same Agent is already busy.
2. As a Leader, I want a returned work ID to address one exact assignment without guessing a resident.
3. As a Leader, I want presence to list the Agent's actual Work Sessions without starting execution.
4. As a Leader, I want fresh context by default for independent judgment.
5. As a Leader, I want explicit fork to inherit the current active context without writing a lossy handoff summary.
6. As a Worker, I want inherited context to retain message roles without acquiring the Leader's runtime identity or tools.
7. As a Leader, I want invalid context controls to fail before starting or steering work.
8. As a Worker, I want an ordinary final answer to reach the Leader without a second bookkeeping call.
9. As a Leader, I want failures, retries, execution settlement, and successful results to remain distinguishable.
10. As a Leader, I want completion evidence and announcements to belong to one assignment attempt.
11. As a participant, I want ambiguous Agent names to return precise routes rather than broadcasting into concurrent work.
12. As a user, I want temporary session context cleaned up without changing my original conversation.

## Scenarios

The executable contract is @features/work-session-delegation.feature. Existing delegation, reporting, and lifecycle scenarios are updated alongside their regression tests; old board behavior remains outside the new direct-delegation semantics unless explicitly required to preserve shared invariants.

## Implementation Decisions

- Preserve the existing delegation and shared communication tools; add no Codex-named tool family.
- A prompt without work creates a fresh execution identity for every call, with the requested Agent definition retained separately from the precise Work Session route.
- Supplying work checks Agent ownership before any side effect. Reopening creates fresh attempt evidence; stale result events cannot end newer work.
- fork is optional and defaults false. It is valid only for a new prompt with no work ID. Model overrides likewise apply at creation, not as implicit live-process replacement.
- Fork snapshots use Pi's active context including compaction semantics, not the entire JSONL tree or a synthetic prose summary. They exclude unfinished parent tool exchanges and extension runtime state. Parent sessions are never switched, branched in place, or modified.
- Context files belong to the owning runtime lifecycle. Existing local process isolation and approved tools are retained; fork grants no new capabilities, workspace copy, or sandbox promise.
- Automatic completion is accepted only after Pi settlement for the current assignment. Explicit terminal reports remain explicit submissions but must not cause duplicate automatic results.
- Completion means a captured execution outcome, not independent verification or integration. Board verification and resource ownership checks keep their existing authority.
- The current root-session single-writer ownership stays in place. Persistent Agent memory, promotion, and cross-runtime recovery are not reimplemented in this slice.

## Testing Decisions

- Primary seam: registered agent and agent_event tools with real state reducers and the child-process adapter controlled at the process boundary. Assert spawning, routing, results, state, and parent immutability rather than source-text implementation shapes.
- Fork context checks use real Pi SessionManager, branched and compacted fixtures, and the worker's selected session content.
- Stream-driven integration checks include final answers, tool messages, transient failures, retries, terminal reports, repeated settlement, and reopening races.
- Follow the existing Python-to-Node test harness convention, with test helpers kept under tests.
- Each behavior begins with a failing regression before implementation. Run package and root tests, typecheck, install validation, real Pi print smoke, and fresh-agent audit after self-verification.

## Out of Scope

New permanent tools; copying Codex's tool inventory; removing persistent-Agent goals; automatic promotion or Agent Memory changes; shared board redesign; cross-session daemon or global inbox transactions; cloud computers or security sandboxing; recent-N-turn fork; arbitrary sibling session fork; replaying completed external operations.

## Further Notes

Codex primary sources were inspected at revision 2cbbf0c9b542a36a1c3284b5e804917635b6f666. V1 fork_context defaults false; opt-in V2 fork_turns defaults all and separates ordinary messaging from follow-up tasks. These are execution references, not a replacement interface contract. The user explicitly selected fork=false as the default for this package.
