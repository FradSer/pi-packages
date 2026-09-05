# Repository Guidelines

## Structure

`index.ts` re-exports `src/index.ts`. Under `src/`, `tools.ts` registers leader
tools and commands; `worker.ts` owns worker tools and shared `task_list`;
`team-machine.ts` coordinates mail, task intents, verification, and wake-ups;
`state.ts` owns roster/board/inbox state; `spawner.ts` manages resident RPC
children; `ui.ts` owns the console. Supporting modules cover discovery,
state-file IO, worktrees, rendering, and follow-up delivery.

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

Keep seven tool names and one `send_message` primitive. Its leader controls
include `reopen` and `resources`; `status` describes worker reports to `leader`.
`task_create` has six flat fields separating dependencies, verification,
resources, and supersession. Only the leader writes state/board snapshots;
workers express claims/submissions through exclusive-create marker files.

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
- `steered` means the control stream accepted a write; inbox/outbox writes are
  `queued`, not read or processed. The first terminal report ends the worker
  turn and suppresses later reports until a new prompt. Preserve intermediate
  reports, including identical bodies, and repeated content across assignments.
- Direct assignments and board claims are mutually exclusive. Direct terminal
  reports close assignments until explicit reopen; board completion requires
  `task_submit` and its effective verify gate. Resource locks survive
  supersession until cancellation acknowledgement or shutdown. Lost claim
  races return actionable errors, not blocking waits.
- For verify escalation, spawn identity, one-shot board notices, and heartbeat
  behavior, consult @README.md sections “Reliability Protocol” and “State and
  Sessions” before changing `team-machine.ts` or `statefile.ts`.

## Testing Guidelines

`features/agent-teams.feature` and `tests/test_teammate_package.py` cover roster,
board, messaging, rendering, and process lifecycle. Exercise claim races,
stale-spawn rejection, verification, terminal-report suppression, and resource
supersession. Pack checks must retain the role reference and package `.memory`.
