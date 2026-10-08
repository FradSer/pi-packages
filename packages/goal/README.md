# @fradser/pi-goal

One thread-scoped objective, authorized continuation, and evidence-based completion.

```bash
pi install npm:@fradser/pi-goal
```

## Commands

| Command | Behavior |
| --- | --- |
| `/goal <objective and completion conditions>` | Ask the model to create a complete objective, or merge this request into the current objective. |
| `/goal` | Show the complete current objective, conditions, reason, and usage. |
| `/goal pause` | Stop current Goal work and pending continuation. |
| `/goal resume` | Authorize continuation, preserving accumulated tokens, elapsed time and run count. |
| `/goal clear` | End the current Goal without claiming completion. |

A goal belongs to its thread. A fresh thread never adopts another thread's goal.
The command queues the user's request; it does not create a second goal or overwrite
an existing objective with a raw additive fragment. The accepted model revision
commits the complete objective and conditions together.

## Tools

- `create_goal({objective, verification_contract?, token_budget?})` starts one goal.
  Another unfinished goal must be revised or explicitly cleared first. A budget
  is set only when requested by the user.
- `get_goal({section?, cursor?})` reads the goal. `summary` and the compatibility
  alias `objective` return the same view. Long model responses include a
  content-bound continuation cursor; the initial TUI result displays the full body.
- `update_goal(...)` performs exactly one operation: request `status: "complete"`
  with an optional `completion_summary`, report `status: "blocked"` with a reason,
  carry out an explicit user pause with `status: "paused"` and a reason, or commit
  a complete `objective`/`verification_contract` revision.

Use ordinary work tools for research. There is no `research_goal`, saved
`next_action`, or separate Goal history tool. Old history reads direct the caller
to the thread transcript. Empty updates and mixed operations are rejected.

## Continuation and completion

A normal settled turn does not invoke a checker. The runtime authorizes another
run only after successful effective work, within the configured limits, with no
queued user input. New successful tool receipts count as work; repeating the same
call and output cannot keep the loop alive. Pending monitor acknowledgements are
not completed work. Unrelated background agents do not count as Goal progress.

Generation and dispatch checks authorize each continuation exactly once. User
input invalidates a queued continuation. Failed, interrupted, empty or repeated
runs wait for explicit recovery rather than fabricating a user pause. Restoring a
session restores its objective but grants no continuation by itself.

Only an explicit completion request invokes one fresh tool-less check. The check
receives the **complete** objective and conditions plus bounded, attributed
observations from this thread. Executor claims are escaped untrusted data. The
checker cannot inspect files or run tests: the executor must collect concrete
verification first. A final `MET` accepts completion; `NOT MET` leaves the goal
unmet. Errors, cancellation and superseded results are distinct and cannot complete
the goal. Three refused completion requests do not pause it.

The same reported blocker must recur on three consecutive model turns with no new
work before the goal becomes blocked. Repeated reports in one turn count once;
new work, requirement revisions and a session boundary reset the streak.

Main-model usage and completion-check usage count against the goal budget. Reaching
the budget stops work and reports the limit; it never means completion.

## Display

Transcript results use the shared pi-kit `[goal] <action or state>` band. Command
and automatic results are durable custom session messages, not replaceable info
notifications. Each event has one result. Settled objectives, conditions, reasons
and reports wrap in full without `ctrl+o` expansion.

The passive footer keeps the Codex-style `Pursuing goal · 2h 25m` while work is
running or continuation is authorized. Otherwise it reads `Goal waiting`,
`Goal paused`, `Goal blocked`, or `Goal budget limited`, followed by elapsed time.
A running check temporarily shows neutral `[goal] checking` status.

[All TUI cases and trigger conditions](TUI.zh-CN.md).

## Storage and settings

Active state is an atomic `.pi/goals/<id>/record.json`. A write lock protects
revision checks, requirement changes and continuation claims. Completion and clear
release that record and detach the thread. **No Goal archive is created.** Existing
legacy archive, prose, research and history files are left untouched; they do not
reactivate finished goals. The normal Pi transcript retains the result.

Global settings are `~/.pi/agent/goal.json`; project overrides are
`.pi/goals/settings.json`. Supported settings are `maxAutonomousRuns`, `provider`
and `model`. The check defaults to the current session model. `PI_GOAL_MODEL`,
`PI_GOAL_PROVIDER` and `PI_GOAL_MAX_RUNS` provide temporary overrides.
`maxAutonomousRuns` is a lifetime continuation allowance; unset is unlimited and
`0` disables continuation. Resume does not replenish the allowance. Legacy research
and check-bypass settings are ignored; completion conditions cannot be bypassed.

## Verification

```bash
python3 -m pytest packages/goal/tests/ -q
pnpm exec tsc --noEmit -p packages/goal/tsconfig.tests.json
pnpm typecheck
pnpm --dir packages/goal pack --dry-run
uv run --no-project --with pyte python packages/goal/tests/goal_native_completion.py
```

Native acceptance uses a scripted provider inside a real Pi CLI/TUI and decodes
complete terminal frames, including resizing and interactive management. It makes
no remote model calls. Docker acceptance installs the packed Goal and its required
kit dependency into an isolated Pi environment; test fixtures inject the scripted
provider/checker, without other production extensions or host credentials.
