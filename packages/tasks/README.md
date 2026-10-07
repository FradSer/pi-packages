# @fradser/pi-tasks

Tasks record durable work, its dependencies, and its completion evidence. The harness checks unfinished work before normal settlement.

It is a complete Pi package on its own. The manifest declares `pi.extensions`, so
installing it registers its four tools by itself, and it depends on no other
runtime package. `@fradser/pi-agent-teams` consumes it and loads its extension
alongside its own.

```bash
pi install npm:@fradser/pi-tasks
```

## Task tools

| Tool | Purpose |
| --- | --- |
| `create_task` | Record a name, detailed body, dependencies, and completion requirements. |
| `get_task` | Read one task in full, including evidence and its successor brief. |
| `list_tasks` | Read task names, status, dependencies, and recovery holds. |
| `update_task` | Edit content or dependencies, start work, record evidence, or reopen work. |

Use `dependsOn` for prerequisites. Independent tasks can run in parallel. A dependent task starts only after every prerequisite completes.

### Reaching the model

Registering a tool is not presenting it. A session that has never seen a task has no reason to look for one.

The trigger conditions therefore live in two surfaces, and they do different jobs. `create_task` states when recording a task is warranted and how a task differs from a goal, in its snippet and its description, and those are sent to the provider on every turn already. On top of them the package injects one bounded note per request from its `context` hook, because a description cannot say when the situation calls for the tool: a session that never considers recording work never reads the description of the tool that would record it.

The note carries no task state, so it is identical on every turn and lands at a fixed index after the system prompt. Each request therefore begins with exactly the previous one, and the provider's implicit prefix cache keeps matching. It is bounded, and tests pin its size, its position, its role, and that one source file defines it.

The note is a **system** message, injected through the `context_with_system` hook. The plain `context` hook never sees the prompt and tool system messages, so a note sent that way can only be a user-role message placed ahead of the user's own request — and a recorded run showed the model reporting it as the user's own message while it was in context. `context_with_system` receives the whole transcript and runs after every `context` handler, so the note reads as harness context and a note another package injected is left untouched.

The tools do not reach a child process. A subagent cannot take or complete a task, so a leader records the outcome from the child's report.

### Task content

The task interface has four core fields:

| Field | Meaning |
| --- | --- |
| `subject` | The short task name. |
| `description` | The detailed work to perform. |
| `dependsOn` | Task ids that must complete first. |
| `status` | The task's current progress. |

The division follows Claude Code's task tools. `get_task` returns the full body; `list_tasks` returns summaries.
See the official [TypeScript SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript) for the reference tool interfaces.

`update_task` can replace `subject`, `description`, or `dependsOn` without a status change. A rename does not change the task id.

Dependency edits replace the full list. An empty list clears it. Unknown ids, self-dependencies, and cycles are refused.
An in-progress or completed task cannot gain unfinished prerequisites. Complete those prerequisites, or reopen a completed task before the edit.

One call may carry content edits and a status change. The content half is validated and recorded first. A refused status keeps the edit, reports what stands, and names the status change as the half to retry; a refused content edit records neither half. A refused status on its own still says it must be a separate call, because the status change is the half that did not happen.

All task tool rows use the `tasks` label, an action, the task name, and a readable status.
Runtime tool names and structured statuses stay unchanged.

```text
[tasks] create · Verify subagents end to end · pending
Description:
Run the end-to-end checks and fix confirmed failures.

Verify:
Confirm that the affected checks pass.

depends · implement-fix
blocked · implement-fix
```

`Description:` identifies the stored `description` field. `Verify:` identifies the stored `verify` prompt.
Each heading appears only when its field has content. Dependency relations follow these sections on expansion.
Collapsed rows preview dependencies and unfinished prerequisites. Expansion preserves full ids, text, and their order.
Lists show complete stored task titles by default, wrapping long titles to the terminal width without expansion.
Descriptions remain separate. Lists also show each task's dependencies and unfinished prerequisites. Holder and resource rows do not appear. Runtime ownership remains in structured results and persisted data for coordination checks.
The tools do not accept or return `resources`.

A list omits full descriptions, completion gates, results, and gate verdicts. Use `get_task` to read these details and the successor brief.
This package does not add Claude Code's optional `owner`, `activeForm`, or generic `metadata` fields.

### Compatibility boundary

Stored resource fields and library resource helpers remain for existing data and known consumers. They are not part of the task tool interface.

This change does not alter execution, isolation, or resource policies in another package.

## Boundary

Everything here describes **Tasks**, not the processes that perform them and not
the messages between them. This package knows nothing about spawning, rosters,
presence, or peer mail, and the boundary is enforced by tests rather than left to
review: a source file that reaches for one of those words fails the suite.

| Module | Owns |
| --- | --- |
| `src/types.ts` | `Task`, `TaskStatus`, `TaskIntent`, `TASK_STATUSES`, `resolveRecordKind`, `TASKS_FILE_VERSION` |
| `src/graph.ts` | Task id derivation, resource normalization, supersession chains, dependency-cycle detection, and the resource-conflict primitive |
| `src/persist.ts` | Task directory layout, atomic read/write with version rejection, and exclusive-create claim/submit markers |
| `src/store.ts` | The task container, the participant seam, the closed set of transitions, and the one refusal every operation returns |
| `src/context.ts` | Bounded per-Task context, structured successor handoff, and the byte budget |
| `src/tool.ts` | The four tools: parameters, the declared result, projections, and the events a change is announced on |
| `src/rows.ts` | The lifecycle row, bound from pi-kit's shared geometry |
| `src/display.ts` | Task labels, readable statuses, and dependency summaries |
| `src/extension.ts` | Registers the four tools, persistence handlers, and the task stop check. |
| `src/stop-check.ts` | Returns bounded unfinished-task state to model context before settlement. |

`resourcesConflict` is the primitive. Deciding *which* held assignments to compare
against it is a participant question and stays with whoever owns the participant
registry.

### The participant seam

A task set with more than one participant needs to know who is holding what, and
the layer that spawns participants is the only one that knows. Importing it would
put that knowledge in this package; duplicating the shape by hand on both sides
would let the two drift, and a drifted seam fails silently as a single-participant
store rather than as an error.

The contract is therefore declared once, in `@fradser/pi-kit`, and both sides
import it. `@fradser/pi-subagents` publishes a registry through
`publishParticipantRegistry`; this package reads it through
`resolveParticipantRegistry`, and shapes the registry implements a `current`
predicate so it never has to learn what an incarnation or a stopped participant
is. With no registry published, the task set is single-participant and every take is
by the main session.

The same reasoning applies to the environment variable a spawned participant binds
through: `TASK_HOLDER_ENV` is named and exported here, so a spawner that renames
its own private variables changes nothing about how a participant is identified.

## Persistence

```text
~/.pi/agent/tasks/<sessionKey>/tasks.json            atomic replace, one writer
~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      exclusive-create claim intents
~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json exclusive-create submit intents
```

The task file has exactly one writer. Installed on its own, this package is that
writer: the extension entry reads the tasks at session start and writes them after
every change, so a standalone set survives a restart. Loading and writes use only `tasks.json`.
A layer that claims the store takes the persistence duty. This package then stands down, so only one writer remains.

The task tools are project-extension tools. A child process runs without
extensions, so it cannot reach them: a subagent cannot take or complete a task,
and the layer that spawned it records the outcome. That limit is stated rather
than worked around, because the alternative is a second task surface inside every
child, which is a different package's problem.

The old `board.json` filename and its path/resolver exports are retired. The runtime does not load, copy, rename, or delete those files.
Existing files stay in place but do not supply tasks. Transfer required records explicitly before upgrading; this release performs no migration.
The task file format remains version 2. Reload all contributing packages together; existing children retain their launch bindings.

Knowing that other participants exist is not the same as a claim. A task set a
participant registry was published beside keeps its own file, because the seam
that publishes participants claims the store from nobody: without a layer that
claimed it, this package is the only thing that would write the file, and a task set
recorded in memory alone is not a durable set. Standing down from that duty does
not mean touching what the claimer loaded — the task set it restored is the task set it
owns.

`session_start` fires again on every session switch, and the writer it attached
belongs to the session it was attached for. The entry therefore releases the
writer before it decides whether to attach a new one, whatever the reason: a
writer surviving a switch is not a second writer on one file, it is the only
writer on the wrong one.

A participant never writes the task set file. It expresses intent through an
exclusive-create marker, so exactly one racer wins a contested claim. An absent
set is a fresh store; a present but unreadable one is an error and is never
treated as empty, because that would silently discard durable work. An incompatible
`runtimeVersion` is rejected rather than migrated, and a process that could not
read the file does not become the writer for it.

A Task that was in progress when the task set was written comes back in
`recovery_hold`. A restored set has no participants, so it cannot still be in
progress, and handing the work straight back out would retry an attempt whose
outcome is unknown.

A restore is the other route into the store, so it is read through the same checks
a write applies. A task file that lost a field to a hand edit, a truncation, or an
older build comes back with that field repaired rather than trusted: a missing
array is an empty array, a budget above the task set's own is the task set's own, and a
status the task set cannot define is kept, held in `recovery_hold`, and reported
rather than adopted.
Anything the restore had to repair is surfaced as a notice, because a task set that
disagrees with its own file is the failure nobody would otherwise see.

`sessionKey` comes from `@fradser/pi-kit` so this package and any other keeping
per-session state agree on which session a directory belongs to.

## Status

A Task states what must be done and under which completion requirements. It never
states who must do it: ownership is derived from action, so there is no
`assignee` parameter anywhere in the tool, and the holder is recorded from the
caller's own runtime identity.

```text
pending ──take──▶ in_progress ──complete success──▶ completed
   ▲                  │                                 │
   │                  └──complete failed──▶ recovery_hold │
   │                                       │            │
   │                     take(reason) ─────┘            │
   ├──────────────reopen───────────────────────────────┘
   │
   └── superseded   (create with `supersedes`, atomically)
```

`recovery_hold` sits beside `in_progress` rather than under `pending`, because it
is a state of its own: the work was attempted and the attempt did not stand.
`pending` now means never attempted, and only that.

The set of statuses is one runtime list rather than a union of literals, so the
set, the declared result schema, the list filter, and the restored-status check
cannot disagree about what states exist.

A failure is explicit. `status=completed` with `outcome=failed` returns the task to
`recovery_hold` and retains the blocker as evidence, because a blocker recorded as
an ordinary answer is not a failure. Taking a task from `recovery_hold` requires a
stated reason. The surface is four tools — `create_task`, `get_task`,
`list_tasks`, `update_task` — one per operation, so a position in the lifecycle is
reachable by exactly one call. The names follow this workspace rather than
Claude Code's: verb first, the noun as the object, snake_case, the same shape as
`create_goal` and `get_goal` next door. `update_task` is the fat one, carrying
status, content and brief, in the same division Claude Code uses; what it does
not inherit is stated where it occurs.

## Reading the task set

The tool declares its result, so the result is data rather than a rendering of
it. A caller that is not a model reading prose — a codemode script asking which
work is claimable, a coordinator waking a participant, a test asserting a
transition — receives the projections through `structuredContent` instead of a
text block it has to take apart, with the per-task shape declared property by
property rather than as an untyped bag. A refusal is data too: it is marked as an
error for the model and still carries what it knows.

## Refusals

Every refusal the store returns looks the same: a **machine code** for a caller to
branch on, an optional **detail** naming what the refusal is about, and a **reason**
written for whoever reads it.

```ts
{ refusal: "resource-conflict", detail: "reviewer", reason: "Task ... conflicts with active work held by @reviewer." }
```

This is the third field name the store has used for the same sentence, after
`error` and `reason`. The third is the one that stays, because a caller could only
branch on *why* a take was refused; the other operations answered with prose under
a field name that differed per function. One shape means one exhaustive switch in
a consumer, and a refusal added to the store joins a list every caller already
handles. The success flag stays what each operation's own domain calls it, `ok` for
a task write and `applied` for a claim marker, so only the flag differs.

The model-facing text of a refusal is its `reason`, unchanged in wording. No rule
about what may be done changed with it.

Two parameters bound what a listing can cost. The store's own ceiling applies
whatever a caller asks for, and a `limit` sent by the caller applies on top of
it, so a declared parameter is never one the tool quietly ignores. A cap of zero
is the empty list it asks for, a fractional one is floored before it is applied,
and a negative one from a model is refused by name.

`context` is a declared object rather than a bare one. A field the task set has no
definition for is refused by name, at every level and on the store's own account
as well as the tool's, because a misspelled brief stored verbatim is retained on
the Task forever: read by no successor, formatted into no brief, and — when the
budget measured only the fields it knew by name — not counted against the ceiling
either.

The budget covers everything a Task retains, the free text included: its subject,
description, completion gate, recorded result, resource tags and context. A
creation is held to it like every other write, and so is each list of tags. A
budget may be set below the task set's default and never above it, because the
budget is the thing bounding a brief — a caller able to raise it removes the
bound. References are de-duplicated and capped on the way in rather than only when
a caller asks, and a note on a reference stays correctable.

A brief is folded into the one a Task already carries rather than replacing it.
Findings and outstanding work are added to across updates, because a successor
recording its own delta must not be able to drop what the outgoing attempt found.
That addition is linear, and the list is bounded by the byte budget rather than by
a count: a cap here would drop the very findings the brief exists to carry.

## Checking a completion

A model splits a large task into n tasks that may depend on each other, takes them
in series or in parallel, and then marks them complete. The task store is the only thing
that sees the whole sequence, so a completion is checked there — against facts the
task store already holds, never by running anything:

| Refused when | The task store can tell because |
| --- | --- |
| a declared dependency is not completed | the dependency is not in `completed` |
| a success records no result | there is no evidence for the judgement |
| nobody ever took the task | `claimedBy` is empty and the status is not `recovery_hold`, so no attempt exists |
| a declared gate was never answered | `verify` is set and no verdict came with the completion |

### Asking instead of failing

The checks above are a write-side flow: the task store refuses, and the refusal says
what would satisfy it. A model that has just finished one of a split needs the
read side too — which of the remaining n can I mark done *now*, rather than
discovering it one refused completion at a time.

Two things keep that read side cheap. A refused completion names **every**
unsatisfied check at once, each with its own remedy, so satisfying all of them is
one call rather than one per rule. And taking a task reports what its completion
must carry — the evidence, and the gate verdict when the task declares a gate — so
the call that finishes the work is also the call that satisfies the checks.

- **Every task names what is unfinished.** `dependsOn` says what the edges are;
  `blockedBy` says which of them are not completed, which is otherwise a
  comparison a caller makes by hand against a list.
- **`list_tasks` takes `ready`.** Tasks that could be completed right now: an
  attempt on the record — in progress, or in `recovery_hold` after a dead holder
  left it — with every declared dependency completed.

It is the mirror of `claimable`, which answers "what can I start". A task nobody
has touched is not completable however finished its dependencies are, because
there is no attempt to accept.

Both answers have one implementation, in the task store. `list_tasks` and the
reminder before settlement read the store's own predicates instead of restating
them, so a filter cannot report less available work than the take and completion
paths would accept.

Completion through an **intent marker** — the file a spawned participant writes
instead of calling a tool — is the same completion and carries the same checks and
the same verdict. A participant that could skip them by writing a file would make
every rule above advisory.

The third rule is the one that needed care. A holder that died leaves a recovery
hold behind, and that is exactly what makes an unheld task acceptable again — the
fallback path so dead work is not stranded forever. A task that was *never taken*
is different: nobody attempted it, so accepting it is a bare assertion.

The holder check that refuses a completion someone else is delivering applies only
while the task is in progress. A pending task is unheld, whatever a restore kept in
`claimedBy`. A restored pending task that names a departed holder therefore takes
the fallback path, exactly as `takeTask` accepts it.

A declared gate is a prompt, and a task set that evaluates prompts runs agents. So the
task store does not run one: it demands the answer and records it. A completion of a
gated task carries `verdict: "pass" | "fail"`, and the task keeps
`completionVerdict` plus the gate it answered, so a later reader can tell a
completion that was gated from one nobody checked. The answer itself is taken on
trust — the task store cannot know otherwise — but the omission becomes impossible.
A failed attempt answered no gate, so a failure clears `completionVerdict` and
`completionGate`. A reader never sees an earlier attempt's verdict on a task whose
current attempt failed.

All four checks are **off unless a caller asks for them** (`ALL_COMPLETION_CHECKS`),
and can be asked for one at a time. A coordinator that already verifies a
submission by other means is not refused for work it has already checked. The
model-facing tool asks for all of them, because that path is the one a model
drives.

### The other door: a withdrawn premise

The same invariant was reachable from the reopen side: completion is checked, so
nothing completes on an unfinished premise — but reopening a *premise* left the
conclusions standing on it.

`status=pending` pulls back everything transitively standing on the task being
reopened — a completed dependent had a *conclusion* withdrawn, one being worked on
had an *attempt* invalidated — each returned to `recovery_hold`, naming the task
whose reopening withdrew its premise. The cascade reaches the far
end of a chain, and a withdrawn attempt has its lease released, so it does not
leave the resources locked by a participant who is no longer working on anything.

**Reopen is always available.** The only two refusals left are definitional: the
task does not exist, or it is not completed. It used to be refused while a
dependent was being worked on, and that was the wrong rule twice over. Reopening
is the only way back from a completed task, so refusing it strands the work for
everyone who ever depended on it; and refusing it only *sometimes* gave one
operation two answers depending on who happened to be holding what at the time.
An operation whose answer is a race is worse than an operation with a cost.

The evidence is kept throughout: it is what the next attempt has to answer, and
what a reviewer reads before deciding whether the work still holds.

A recorded gate verdict is **withdrawn** on a task that gets pulled back, because
a `pass` on a task that is no longer complete is the one reading this task set cannot
afford. The task's own verdict survives its own reopen — it is pending again, and
the verdict described an attempt that may yet stand.

## Execution history

Automatically generated direct-input records carry `recordKind: "execution"`. They retain results, failures, and recovery evidence for inspection.
They do not trigger task continuation or autonomous claims. An ordinary task remains actionable unless its lifecycle or recovery requirements prevent work.

Earlier generated `work:<UUID>` records receive this classification on restore when explicit metadata is absent.
An explicit `recordKind: "task"` takes precedence. Classification does not complete an attempt, clear its hold, or delete its evidence.
The public tools do not let the model change this internal classification.

## Before the model stops

Pi invokes `agent_before_settle` after a normal final response. The harness checks for pending and in-progress tasks at this boundary.

If work can proceed, it appends the current task status to model context and requests one continuation. The message contains:

- Task ids, status, and holders.
- Unfinished dependencies and claimable work.
- Instructions to perform the work before recording completion evidence.

The harness never completes a task itself. An `in_progress` status is not proof that the implementation exists.

The transcript shows one compact row:

```text
[tasks] continue · 2 unfinished tasks · continue work · ctrl+o to expand
```

The full instructions remain in model context. They contain at most 20 task rows and 8 KiB of text.
The status row expands to a separate bounded summary with task names, progress, dependencies, and unfinished prerequisites. A row names the work and its state. It does not print the task id beside the name, because the id is derived from the subject and would print the name twice; the id arrives in the tool result where a caller acts on it.

A status row exists only where a transcript can show it. In a session with no UI — `pi --print` — the check returns no result on a settlement that cannot continue, so the run prints its final assistant text instead of a row. A continuation result keeps its status message in every mode, because that message is the instruction the model reads on the next request.

### Continuation limits

Each real user input permits at most three automatic task continuations. Extension-generated input does not reset this allowance.

Each unchanged task snapshot receives only one continuation, even when pending work appears claimable.
If task state does not change, the harness reports `waiting · no task progress` instead of repeating the same request.
A claimable task does not prove that input or authorization is available. The harness does not infer approval from task status.

Changes to task content or lifecycle permit another continuation within the same allowance. A timestamp-only write is not progress.
When the allowance is exhausted by changed task snapshots, the harness reports unfinished work and stops requesting continuation.
New user input renews the allowance.

Cancellation, provider errors, queued input, and another handler's continuation take precedence. The task check does not restart those runs.

### Blocked work

A displayed status row does not create another model request. One task snapshot earns at most one continuation, whatever the state of its tasks: a snapshot with nothing immediately claimable is not a second kind of round, it is the same round with a different reason. The waiting reason names the blocker, and the status word stays `continue`.

The model reads `get_task`, checks saved evidence and dependencies, and decides whether recovery is safe within the authorized scope. It supplies a recovery reason only after that check.

The harness does not clear a recovery hold, transfer ownership, or mark work completed. If a blocker still requires access or user input, the model reports it.

The reminder carries the recovery instruction only when a recovery hold is present, and an unchanged snapshot receives no further continuation. Changed task state or new user input permits another check, within the same continuation limit.

The transcript names the reason:

```text
[tasks] continue · 1 unfinished task · continue work · ctrl+o to expand
[tasks] waiting · 1 unfinished task · recovery inspection required · ctrl+o to expand
```

When another boundary handler supplied messages or context edits, the task check preserves them before appending its status snapshot.

## Contracts

Behavior is pinned in `features/` with Given/When/Then scenarios, executed by
`tests/`:

```bash
python3 -m pytest packages/tasks/tests/ -q
```

- `features/work-domain.feature` — the domain rules, durable persistence, the completion facts that follow from task
  state, and the boundary this package keeps
- `features/work-context.feature` — bounded per-Task context
- `features/task-tool.feature` — the tool surface, dependency-based workflow, its row, and standalone durability.
- `features/completion-checks.feature` — completion evidence, dependency checks, and reopen invalidation.
- `features/task-stop-check.feature` — task reminders, cancellation, blocked work, continuation limits, and headless
  settlement output.

`tests/test_task_stop_live.py` runs real Pi with a deterministic local provider. It requires no credentials or network requests.

## License

MIT
