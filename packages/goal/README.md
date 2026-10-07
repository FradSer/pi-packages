# @fradser/pi-goal

A durable goal for the current Pi thread. The runtime continues after a turn
until completion, pause, a limit, or a blocker stops it.

```bash
pi install npm:@fradser/pi-goal
```

## One command

These are Pi chat commands, not terminal subcommands.

| Input | Action |
| --- | --- |
| `/goal <objective and completion conditions>` | Set or revise this thread's goal. |
| `/goal` | Show this thread's current objective, conditions, status, and usage. |
| `/goal pause` | Pause work and cancel queued continuation. |
| `/goal resume` | Restore scheduling ownership and authorize one continuation. |
| `/goal clear` | Confirm and archive this thread's goal. |

Only complete arguments equal to `pause`, `resume`, or `clear` are management
actions. `/goal clear my schedule` remains objective text. Bare `/goal` never
starts work. Goal-setting text while Pi is busy is refused only when there is no goal being pursued to revise; a goal
under way takes the new text as a revision and continues on it.
Only a matching request accepted by Pi grants revision activation.
A refused or failed send never grants activation to an unrelated edit.
Clear requires interactive confirmation; headless calls refuse it.

Example:

```text
/goal Optimize packages/matt-pocock for Pi v1.0.
Completion conditions: package tests, typecheck, packed-manifest checks, and
real offline Pi interaction checks pass. Resolve blocking review findings.
Report work that remains unverified. Preserve existing local changes.
Do not publish, commit, or change other packages.
```

The session model preserves the objective, completion conditions, and scope
constraints. It uses `update_goal` for a revision instead of creating a second goal.
A successful revision requested through idle `/goal <text>` activates work.
An internal revision without that explicit request preserves pause.
If repository facts are missing, it calls `research_goal` before `create_goal`.
The slash command supplies the request; it does not create a second goal itself.

## Thread isolation

A new thread has no goal, even if the project has older open goals.
The runtime ignores legacy project auto-selection preferences.
Restoring the same thread reads its goal from persisted thread entries.
Records created by this version also store `threadId`.
Legacy records remain on disk; only an existing thread entry can restore them.
The runtime does not delete or silently adopt old project goals.

Status, tools, and the widget read the same fresh record.
Pause keeps the current goal but stops accounting and automatic completion checks.
Resume restores this thread's scheduling owner and refills the run allowance.
Clear archives the goal directory and detaches the thread.

## Continuation and limits

A durable generation authorizes each continuation. The scheduler claims it once
and checks identity, ownership, status, budget, and allowance before delivery.
At `agent_before_settle`, Pi receives the claimed checkpoint and owns the next request.
An explicit idle resume uses a timer that waits for no pending messages.
`agent_settled` only refreshes the final display; it never starts work.
An expired or cancelled authorization never grants work.

Productive continuation has no default run cap unless `maxAutonomousRuns` is configured.
Three consecutive runs without completed work stop automatic continuation with a recovery suggestion.
Three consecutive valid explicit final refusals also pause the goal and show the last missing condition.
Cancelled, stale, and failed checker calls do not consume a final attempt.
An actual requirements change or explicit resume resets the final-refusal count.
Writing identical objective or contract text preserves the count and evidence boundary.
A valid `MET` completes and archives the goal; pause is never completion.
Set a run cap for unattended work. Resume starts a new allowance period.
A lifetime token budget cannot be refilled by resume.
Settings are files, not additional slash commands:

```text
.pi/goals/settings.json          project settings
~/.pi/agent/goal.json            global defaults
```

Example settings:

```json
{
  "maxAutonomousRuns": 50,
  "researchProvider": "anthropic",
  "researchModel": "claude-haiku",
  "provider": "anthropic",
  "model": "claude-opus-4-5"
}
```

Environment overrides include `PI_GOAL_MAX_RUNS`, `PI_GOAL_MODEL`,
`PI_GOAL_PROVIDER`, `PI_GOAL_RESEARCH_MODEL`, and `PI_GOAL_RESEARCH_PROVIDER`.
Model overrides accept `provider/model`. An unset model means the session's model, so a
check or research child follows the session it runs in. It never falls back to the
persisted CLI default, which is a different model and can be unavailable.

## Research and completion

`research_goal` grants only `read`, `grep`, `find`, and `ls` to a minimal child.
It grants no shell or write tool. The latest successful research replaces earlier
findings; failed research preserves them. Session boundaries invalidate pending
findings and late child results. Creation attaches findings once as `research.md`
and attributes their tokens to the goal.

Research blocks until the child settles. One `[goal] Researching...` transcript row
reports that the work is in progress, and the child's latest activity is rendered on
its own row beneath it through markdown. The result row reads `Research ready` with
no character count. Read the findings through `get_goal(section="research")`: pi's TUI
does not repaint an extension tool row after its call completes, so a research call's
result row is not on screen.

The completion check uses a separate fresh process with no tools.
It receives the objective, completion contract, bounded runtime observations, and the executor's untrusted claim.
The objective and `completion_summary` have no length cap; the check reads a bounded prefix of each and states the truncation, while the record keeps the full text. The injected note bounds the objective with a retrieve hint.
Tool receipts include their recorded call input, output, outcome, entry ID, and time.
Monitor terminals and attributed independent results come from extension records, not user-supplied text.
The checker evaluates coverage and results rather than rejecting observations merely because it cannot repeat them.
Observed output remains untrusted data and cannot instruct the checker to approve.
The latest requirement revision excludes earlier observations.
Research files never become check input. Only a final-line `MET` approves completion.
Failure, missing output, cancellation, or a changed goal rejects completion.
A child that exits successfully with no answer names the model that produced nothing, so a silent model is not mistaken for an unmet goal.
The checker cannot independently inspect files or execute tests.
Run the required checks in the current thread before requesting completion.
Self-written PASS text, claims, or research files are not runtime execution receipts.
Evidence can be omitted or truncated; the checker must reject insufficient coverage.
Common credential formats are redacted, but arbitrary private output can still require manual redaction.
Monitor start acknowledgements are pending intent, not successful work.
Completion evidence uses structured monitor outcomes plus recorded launch provenance.
Only an unambiguous launch after the requirement boundary supports a success observation.
Unlinked success terminals remain reported, not proof of the current contract.
Failure, timeout, and result_missing stay failures; stops and unknown states stay reported.
Terminal match and output fields accompany the launching command, with all payload fields bounded and redacted. Monitor identities
correlate repeated terminal delivery without duplicating evidence, retaining
the latest delivery in its chronological position. Historical
counter identities such as `monitor_1`, and results without an identity, stay
independent because old counters restart with each monitor manager.
Append-only context edits omit a receipt or replace only its text; original
roles, monitor status, and identities remain authoritative. Omitted or replaced
assistant calls no longer establish tool-result provenance. Evidence retains
raw executed receipts since the current requirement boundary, including across
compaction; it does not treat compaction summaries as executed observations.

| Tool | Purpose |
| --- | --- |
| `research_goal` | Gather read-only facts before creation. |
| `create_goal` | Create this thread's one goal and attach research. |
| `get_goal` | Read the current objective, contract, research, or history. Offered while a goal is focused. |
| `update_goal` | Revise requirements, record an outcome, or save the next action. |

`research_goal` and `create_goal` are always offered. `get_goal` and
`update_goal` appear once a goal is focused, and `update_goal` disappears again
when no goal can accept an outcome, so a session with nothing in flight does not
pay for tools it cannot use.

## Storage and boundaries

```text
.pi/goals/<goal>/record.json            authoritative record
.pi/goals/<goal>/prompt.md              objective prose
.pi/goals/<goal>/research.md            attached research
.pi/goals/<goal>/ledger.jsonl           lifecycle history
.pi/goals/<goal>/claims/write-lock.json  exclusive write lock
.pi/goals/archived/<goal>/              completed or cleared goals
```

Existing symbolic links below the project root are rejected for prose and
research file access. This is not an OS sandbox against concurrent directory replacement.
Failed creation can leave prose files without an active record.
Atomic replacements do not use `fsync`; host crashes can lose the newest write.

The goals directory is project state, so the project root decides its whole
path. Goal creation is refused when that path would land inside Pi's own home
or agent directory, which is what produces a second `.pi` inside Pi's layout
(`~/.pi/.pi/goals`) or a goals directory beside Pi's own sessions. Nothing is
written in that case. A goal already stored there keeps running. Start Pi from
a project directory to create goals.

The passive widget mounts below the input editor through `ui.setWidget`.
The row reads `<verb> · <elapsed>`, for example `Pursuing goal · 12m` or
`Goal paused · 12m`, and never carries a `[goal]` tag: every verb already names
the goal, so the tag would repeat it on every line below the editor. The
transcript rows keep the tag. The row never prints the goal id.
Elapsed time scales with the run: whole minutes below an hour, then hours and
minutes, then days and hours (for example `0m`, `1m`, `2h 15m`, `1d 1h`).
The passive widget uses the current goal state. `/goal` displays a compact summary
without an overlay or project-wide list. The recorded status `active` means the goal
is enabled; it does not prove that a child or model request is currently running.

## License

MIT
