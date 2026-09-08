# Repository Guidelines

## Structure

`index.ts` re-exports `src/index.ts`. Under `src/`, `tools.ts` registers leader
tools and commands; `worker.ts` owns worker tools and shared `task_list`;
`team-machine.ts` coordinates mail, task intents, verification, and wake-ups;
`state.ts` owns roster/board/inbox state; `spawner.ts` manages resident RPC
children; `ui.ts` owns the console; `leader-reports.ts` defines envelopes and
grouping. Supporting modules cover discovery, state-file IO, worktrees, and
guidance.

There are no bundled roles. Consult @references/agent-roles.md when generating
one; keep it session-local unless the user explicitly requests persistence.

## Commands

From the repository root:

```bash
python3 -m pytest packages/agent-teams/tests/ -q
pnpm --dir packages/agent-teams pack --dry-run
```

## Style and architecture

Preserve explicit `.ts` relative imports for native Node execution and strict
TypeBox schemas. Agent definitions are Markdown frontmatter plus a prompt;
resolve names project-local `.pi/agents/<name>.local.md` > project
`.pi/agents/<name>.md` > user `~/.pi/agent/agents`. Deduplicate paired files;
generated session roles fill undefined names. `model`, `verify`, and `worktree`
belong to the role definition, not top-level spawn overrides.

`send_message` has six parameter fields separating destination, text,
assignment controls, and status. Its leader controls include `reopen` and
`resources`; `status` describes worker reports to `leader`. Leader steering carries authoritative task direction at the next safe boundary,
ahead of worker plans and peer follow-ups, while preserving system/user constraints.
Send newly discovered information or changed priorities rather than status requests. `task_create` has
six flat fields separating dependencies, verification, resources, and
supersession. Only the leader writes state/board snapshots; workers express
claims/submissions through exclusive-create marker files.

## Independent Work Sessions

`agent` with prompt and no work starts independent work even for the same Agent;
work selects a stable Work Item handle and validates Agent ownership. Each reopen
changes assignment identity, not the Work Item handle. Inspection lists actual
sessions and precise routes without starting execution. `fork` defaults false;
true snapshots the Leader's active Pi context, excluding unfinished tool exchanges
and extension runtime identity. It is invalid with work or without prompt.
Keep context seeding in `work-context.ts`; never switch or mutate the Leader's
session. Context files belong to the child lifetime. Reference:
@SPEC-work-sessions.md and @features/work-session-delegation.feature.

Direct-work ordinary final answers are reported by worker settlement hooks, with
failed outcomes for errors/aborts/incomplete responses. Explicit terminal reports
suppress duplicate automatic results. Board completion still requires submission
and verification. Finish announcements are per assignment attempt, not process.
Use `recipient.ts` for precise or unambiguous shared message routing.

## Lifecycle and Coordination Contracts

- Spawn uses native `Text`: `[agent] @<name> started · <assignment>`, with only
  the prefix colored, wrapping and no expansion/background band. Other tools
  use `src/tool-render.ts` and its static pi-kit adapter; `task_list` uses
  `listed`. Suppress shutdown's row after completion was already announced.
- Reports use `[message] from @<name>` and `<agent-message>` with expandable
  bodies and a separate finish entry. Keep `<harness-event>` diagnostics and
  health notices separate. Requested shutdown adds no leader follow-up.
- Leaders always expose spawn/create; living teammates reveal shutdown/send,
  and board tasks reveal list. Workers reveal list/claim on a board notice,
  then submit while holding a claim.
- `steered` means the control stream accepted a native prompt with steering behavior;
  that prompt also starts idle execution. Peer input uses lower-priority follow-up.
  Inbox/outbox writes are `queued`, not read or processed. Worker reports hand off to Pi immediately;
  Pi delivers them at the next safe tool boundary or wakes an idle leader.
  Agent Teams has no additional queue, debounce, or wait for `agent_settled`.
  A terminal report closes its assignment and ends the worker turn; only
  `agent_settled` confirms execution settlement. Further reports from the closed
  assignment are rejected. A new assignment cannot inherit an older PASS. Preserve intermediate reports,
  including identical bodies, and repeated content across assignments.
- Direct assignments and board claims are mutually exclusive. Direct terminal
  reports close assignments until explicit reopen; board completion requires
  `task_submit` and its effective verify gate. Resource locks survive
  supersession until cancellation acknowledgement or shutdown. Lost claim
  races return actionable errors, not blocking waits.
- For verify escalation, spawn identity, one-shot board notices, and
  console-only silence telemetry, consult @README.md sections “Reliability
  Protocol” and “State and Sessions” before changing `team-machine.ts` or
  `statefile.ts`. The harness never sends the leader heartbeat or stall notices.

## Testing Guidelines

`features/agent-teams.feature` and `tests/test_teammate_package.py` cover roster,
board, messaging, rendering, and process lifecycle. Exercise claim races,
stale-spawn rejection, verification, terminal-report suppression, and resource
supersession. Pack checks must retain the role reference and package `.memory`.
