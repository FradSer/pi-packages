# @fradser/pi-goal

One thread-scoped objective, authorized continuation, and evidence-based completion.

```bash
pi install npm:@fradser/pi-goal
```

## Commands

| Command | Behavior |
| --- | --- |
| `/goal <objective>` | Show one `[goal] requesting` row with the typed words, and ask the model to create or revise one concise, outcome-focused objective. |
| `/goal` | Show the complete current objective and reason. |
| `/goal pause` | Stop current Goal work and pending continuation. |
| `/goal resume` | Authorize continuation, preserving accumulated tokens, elapsed time and run count. |
| `/goal clear` | End the current Goal without claiming completion. |

An action verb is one only by itself: `/goal clear my schedule` is a request for the
model, not a command that clears the goal.

A goal belongs to its thread. A fresh thread never adopts another thread's goal.
The command queues the user's request; it does not create a second goal or overwrite
an existing objective with a raw additive fragment. The accepted model revision
commits one concise objective that preserves explicit requirements, without adding
unrequested implementation details or inferred scope.

## Tools

- `create_goal({objective})` starts one goal. The objective is the goal's only
  requirement text: there is no second verification field and no completion
  condition beside it. Another
  unfinished goal must be revised or explicitly cleared first. A goal has no
  spending cap and none can be set: it is bounded by its work, not by a ceiling.
- `get_goal({section?, cursor?})` reads the goal. `summary` and the compatibility
  alias `objective` return the same view. Long model responses include a
  content-bound continuation cursor; the initial TUI result displays the full body.
- `update_goal(...)` performs exactly one operation: request `status: "complete"`
  with an optional `completion_summary`, report `status: "blocked"` with a reason,
  carry out an explicit user pause with `status: "paused"` and a reason, or commit
  a complete `objective` revision.

Use ordinary work tools for research. There is no `research_goal`, saved
`next_action`, or separate Goal history tool. Old history reads direct the caller
to the thread transcript. Empty updates and mixed operations are rejected, and so
is a call that carries a field this version does not declare: a removed field
cannot be silently dropped from a revision that is applied.

## Run-start context

Pi 1.2 `before_agent_start` contributes Goal capability and current state through structured system prompt sections once per run. Tool rounds do not inject or replay runtime messages. The runtime enforces current state independently; use `get_goal` for updated details during a run.

## Continuation and completion

A normal settled turn does not invoke a checker. The runtime authorizes another
run only after successful effective work, within the configured limits, with no
queued user input. **Progress means a workspace change**: only a successful
`edit` or `write` this goal has not already seen earns the next run. Reading,
searching, fetching, running commands and delegating work to another process
explore, and exploration does not hold the loop open. Three consecutive runs that change nothing stop automatic
continuation and say so; `/goal resume` starts the window again. A requirement
revision does not clear that memory, so re-wording the objective cannot make the
same change count twice. A user's own turn is a fresh opportunity rather than a
run that changed nothing, and `/goal <text>` is that user's turn even though the
command delivers it as a custom message: a run that only records the objective
still earns exactly one real run, and the run after it is judged normally.
Pending monitor acknowledgements are not completed
work. Unrelated background agents do not count as Goal progress.

Generation and dispatch checks authorize each continuation exactly once. User
input invalidates a queued continuation. Failed, interrupted, empty or repeated
runs wait for explicit recovery rather than fabricating a user pause. Restoring a
session restores its objective but grants no continuation by itself.

Only an explicit completion request invokes one fresh tool-less check. The check
receives the **complete** objective plus bounded, attributed
observations from this thread. Executor claims are escaped untrusted data. The
checker cannot inspect files or run tests: the executor must collect concrete
verification first. A final `MET` accepts completion; `NOT MET` leaves the goal
unmet. Errors, cancellation and superseded results are distinct and cannot complete
the goal. Three refused completion requests do not pause it.

The same reported blocker must recur on three consecutive model turns with no new
work before the goal becomes blocked. Repeated reports in one turn count once;
new work, requirement revisions and a session boundary reset the streak.

Usage is a report, not a ceiling. Main-model usage and completion-check usage are
recorded against the goal, and nothing stops because a number got large: with no
spending cap anywhere, the three-run no-change window above is the bound, and
`maxAutonomousRuns` is the only optional ceiling. A record an earlier version wrote
with a `tokenBudget` is read without it, so a goal that stopped under one continues
as any stopped goal does. A record that carries a `verificationContract` from an
earlier version is read without it too: the objective is the only requirement the
check judges.

## Display

Transcript results use the shared pi-kit `[goal] <action or state>` band. Command
and automatic results are durable custom session messages, not replaceable info
notifications. Each event has one result. Settled objectives, reasons and reports
wrap in full without `ctrl+o` expansion. A row's body is the objective and any stop
reason; usage stays on the record and in the run-start counters, so no row repeats
a token count.

`/goal <request>` keeps its own row: one `[goal] requesting` line with the typed
words under it. The shared band strips control bytes from those words. The complete
request body stays out of the terminal transcript, so the row that reports what the
goal became never sits under a wall of prompt text. That body still reaches the
model, and it remains in the session record. A session replayed without this
renderer is the one exception: Pi then prints the stored body through its default
custom-message rendering.

The passive footer keeps the Codex-style `Pursuing goal · 2h 25m` while work is
running or continuation is authorized. Otherwise it reads `Goal waiting`,
`Goal paused` or `Goal blocked`, followed by elapsed time.
A running check temporarily replaces that row with one neutral activity line, without a `[goal]` prefix.

[All TUI cases and trigger conditions](TUI.zh-CN.md).

## Storage and settings

Active state is an atomic record under Pi's own agent directory:
`~/.pi/agent/goals/<project key>/<id>/record.json`. Goal state belongs to the
sessions that share a working directory, and the project key keeps two projects
apart, so a new goal writes nothing into the working tree. A write lock protects
revision checks, requirement changes and continuation claims. Completion and clear
write the terminal `complete` status and detach the thread: the record is kept, so
what was asked for and how it ended stay readable. **No Goal archive is created.**
A goal stored by an earlier version in `<project>/.pi/goals` is still read, locked
and written where it lives, and its legacy prose, research and history files are
left untouched; they do not reactivate finished goals. The normal Pi transcript
retains the result.

Global settings are `~/.pi/agent/goal.json`; a project's overrides are
`settings.json` inside that project's goal directory. An override stored by an
earlier version in `<project>/.pi/goals/settings.json` is still read. Supported
settings are `maxAutonomousRuns`, `provider`
and `model`. The check defaults to the current session model. `PI_GOAL_MODEL`,
`PI_GOAL_PROVIDER` and `PI_GOAL_MAX_RUNS` provide temporary overrides.
`maxAutonomousRuns` is a lifetime continuation allowance; unset is unlimited and
`0` disables continuation. Resume does not replenish the allowance. Legacy research
and check-bypass settings are ignored; the completion check cannot be bypassed.

## Verification

```bash
python3 -m pytest packages/goal/tests/ -q
pnpm exec tsc --noEmit -p packages/goal/tsconfig.tests.json
pnpm typecheck
pnpm --dir packages/goal pack --dry-run
uv run --no-project --with pyte python packages/goal/tests/goal_native_completion.py
uv run --no-project --with pyte python packages/goal/tests/goal_native_request_row.py
uv run --no-project --with pyte python packages/goal/tests/goal_native_request_continuation.py
uv run --no-project --with pyte python packages/goal/tests/goal_native_revision.py
```

Native acceptance uses a scripted provider inside a real Pi CLI/TUI and decodes
complete terminal frames, including resizing and interactive management. It makes
no remote model calls. Docker acceptance installs the packed Goal and its required
kit dependency into an isolated Pi environment; test fixtures inject the scripted
provider/checker, without other production extensions or host credentials.
