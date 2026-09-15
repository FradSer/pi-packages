---
name: agent-teams-persistent-agents
description: Confirmed three-tool unified Work interface (agent/work/agent_event) with explicit actions, shared submission/verification pipeline, and atomic cutover from nine legacy tools
type: project
---

## Status

Planning spec at `packages/agent-teams/SPEC-unified-work.md` and `PLAN-unified-work.md`. Not yet implemented. The user explicitly selected: retain advanced Work management and resident autonomous claim, converge to three tool names, one-call agent delegation, and shared automatic+explicit submission.

## Confirmed interface

Three coordination tools; old names removed at cutover.

### `agent` — Agent definition and resident execution

| Action | Required | Optional | Effect |
|---|---|---|---|
| delegate | name, prompt | definition, resources, verify, fork, model | Create+assign one Work Item and start independent execution in one call |
| start | name | definition, model | Start an unassigned resident; no Work Item or promised result |
| inspect | name | session | Bounded Presence; starts no process |
| stop | session | — | Confirmed stop of exact execution |

- Inline definition retains description/tools/prompt/model/verify/worktree; generated roles are session-local unless user requests persistence.
- `fork` defaults false; true snapshots Leader's active Pi context (excludes unfinished tool exchanges and extension runtime identity). Valid only for delegate with no existing work.
- `delegate` has no steer or implicit reopen branch; it always creates independent Work Sessions even for the same Agent.

### `work` — Unified Work lifecycle (role-scoped)

| Action | Authority | Effect |
|---|---|---|
| create | Leader | Pending Work Item with deps, resources, verify; notifies eligible residents; never spawns |
| list | Leader or eligible Worker | State query; bounded filter/cursor; one ID returns result and current holding |
| assign | Leader | Authorize one Assignment Attempt on an exact idle session or defined Agent for fresh execution |
| claim | Eligible idle Worker | Queue intent; only the single writer's accepted binding authorizes execution |
| submit | Current bound owner | Candidate result; shares pipeline with automatic final answer; suppresses automatic duplicate |
| reopen | Leader | Settled terminal/parked work returns to pending; retains Work ID; retires old acceptance; creates no process |
| release | Leader or owner | Relinquish unfinished/failed work; live resource locks survive until acknowledgement or confirmed stop |
| supersede | Leader | Atomic replacement with pending-dependency rewire; live holder keeps resource until safe release |

### `agent_event` — Communication only

```ts
{ message: string; to?: string; intent?: "inform" | "request" }
```

- No lifecycle authority: cannot submit, complete, reopen, release, or transfer work.
- `to` omitted requires one unique bound reply route; ambiguous or absent → rejected.
- Events bind to the current attempt at send time; if the attempt closes before consumption, the event is historical or rejected, not delivered to a next attempt.

## One lifecycle

States: pending → active → verifying → completed | failed | superseded. Dependency/resource blockers and verification attention are reasons on those states, not parallel machines.

### Submission and verification

- Ordinary final answer and explicit `work submit` produce the same internal submission event. Explicit submission ends the Worker turn and suppresses automatic duplication.
- Effective gate: Work-specific verify, else Agent Definition default, pinned for the holding. Gate waits for authoring execution to settle.
- No gate → accept at settlement. Gate → verifying until PASS; resources retained.
- First FAIL → findings to same owner; may make a new submission without releasing.
- Second consecutive FAIL or twice-inconclusive → park; one Leader attention event; no autonomous retry.
- Completion is independent of acquisition path (delegate, assign, or claim).

### Resource and ownership safety

- One owner per Work Item at a time. Resource conflict check uses prefix hierarchy (firmware/sub conflicts with firmware/sub/deep).
- Resource locks survive supersession until cancellation acknowledgement or confirmed stop.
- Stale submissions, delayed gates, and old reports cannot accept, close, or unlock newer work.
- Failed work blocks dependents; explicit reopen/release required for retry.

## Cutover migration

| Removed | Replaced by |
|---|---|
| teammate_spawn (with prompt) | agent delegate |
| teammate_spawn (no prompt) | agent start |
| teammate_shutdown | agent stop |
| task_create | work create |
| task_list | work list |
| task_claim | work claim |
| task_submit | work submit or ordinary final answer (automatic) |
| send_message (leader→worker) | agent_event or agent delegate steering |
| agent steer/reopen | work assign + agent delegate (no dual-path) |
| agent inspect | agent inspect |

## How to apply

- Before implementation, each slice begins with its BDD scenario at `packages/agent-teams/features/unified-work-interface.feature` and one failing public-seam test.
- Keep the existing Python-to-Node test harness, real state reducers, and controlled process boundary.
- Do not introduce new adapter hierarchies, event-sourcing frameworks, or policy engines.
- The simplification is complete only when duplicate registrations, kind-dependent logic, and repeated coordination prose are deleted.
- The current single Leader runtime is the sole writer. Cross-runtime scheduling, global persistent inbox, daemon, cloud computers, automatic promotion, and Agent Memory changes are out of scope for this slice.

## Related

[[project_teammate_autonomous_and_tui]]
[[project_agent_leader_priority]]
[[project_follow-up-queue]]
[[feedback_no_sleep_waiting_for_teammates]]
