# @fradser/pi-tasks

Tasks is a durable work list with dependencies and completion evidence. A goal is one objective pursued until achieved; a task is one unit of work to order, take, and finish.

```bash
pi install npm:@fradser/pi-tasks
```

The extension registers four tools and uses `@fradser/pi-kit` for shared rendering, persistence primitives and participant contracts. Agent Teams consumes the same store; Tasks does not spawn workers or add a research, archive or separate history workflow. The tools do not reach a child process. A subagent cannot take or complete a task, so the leader records the outcome from its report.

## Tools and states

| Tool | Purpose |
| --- | --- |
| `create_task` | Record a subject, optional detail, dependsOn and replacement relations. |
| `get_task` | Read one task in full, including evidence and successor context. |
| `list_tasks` | Read compact summaries with statusFilter, claimable, ready, limit and cursor. |
| `update_task` | Edit content and/or apply one guarded transition. |

A `subject` is a short name of at most 60 characters for the row a reader sees; `description` is optional detail that does not fit it, and a subject alone is a complete task. Name a task in `dependsOn` when this task cannot start before that one finishes. Use `supersedes` when earlier work is obsolete or wrong: the replacement takes over its dependents and the old record stays readable. A task id is minted once from the subject and stays the handle across a rename.

| State | Meaning | Next action |
| --- | --- | --- |
| pending | Work available after its dependencies complete, including reopened work. | in_progress |
| in_progress | The caller holds the attempt. | completed or blocked |
| blocked | Work needs a blocker resolved or a previous attempt inspected. | in_progress with reason |
| completed | Success delivered with evidence and required verdict. | pending to reopen |
| cancelled | Unfinished work the caller abandoned. It leaves the board and keeps its record. | pending to reopen |

A dependency-unfinished task remains pending and shows `Blocked by #N`. It cannot start or successfully complete until its prerequisites complete. `supersededBy` is a replacement relation, not a status. Replaced records remain readable but are excluded from pending, claimable, ready and continuation work. A holder of replaced work must acknowledge cancellation before releasing its lease.

`update_task` routes status transitions:

- `in_progress`: take the task for the derived caller; blocked work requires `reason` explaining safe recovery. Recover blocked work before submitting a successful completion.
- `blocked`: record `reason`, release the caller's attempt and retain previous evidence.
- `cancelled`: record `reason` for abandoned unfinished work. The task leaves the board, stops counting as unfinished and keeps its record; a cancelled prerequisite still blocks its dependents. Use it instead of `blocked` when nothing is waiting on an external condition.
- `completed`, `outcome=success`: record `result`; dependencies, prior attempt and a declared verify gate must satisfy the completion checks. A gate requires `verdict=pass`.
- `completed`, `outcome=failed`: retain the failure result and move to blocked. A later success keeps `failureEvidence` alongside the new result.
- `pending`: reopen a completed or cancelled task while retaining its evidence. Completed or held transitive dependents become blocked; their conclusions are withdrawn and leases released. Recovery must address the reopened premise.

The store records a verdict; it does not run the verification prompt itself. Library consumers can request completion checks individually; model-facing tools request all checks. Ownership is derived from the caller, never an assignee parameter. Foreign holders, replacements, invalid graphs and invalid transitions are refused.

Content edits replace subject, description, dependsOn or verify; context merges successor information. Unknown dependencies and cycles are refused, and held/completed work cannot acquire unfinished prerequisites. One call may edit content and status: an accepted edit survives a refused status, and the result says so; a refused edit records neither half.

## Rendering and pagination

All tool results use the shared pi-kit `[tasks]` lifecycle style. Every row is collapsed by default: it shows only its `[tasks] <action> · <title>` headline with the native expansion hint on the last line. A headline wider than the row wraps in full over more lines instead of being elided: every line but the last wraps at the full width, and only the last line makes room for the hint. The task name and its trailing status group (`(in progress)`, `(blocked)`, `(cancelled)`) stay readable. Use Ctrl+O or the native row action to expand the wrapped body, which carries titles, descriptions, Verify, evidence, blockers, errors and persistence notices. A list shows only its task count until expanded. Display numbers follow creation order across the full task set; filtered pages can contain gaps. Storage ids, holders and resource locks remain in coordination data rather than ordinary rows. The public tools do not accept or return resources.

```text
[tasks] create · #2 Verify dependency handling (pending) · to expand
```

A list contains summary fields, not descriptions, gates or full results; use get_task for those. Pages return at most 40 tasks. `count` is the number of matching records, `shown` the current page size, `offset` its position and `cursor` the next page token. Pass cursor back to read the next page; filters travel with it. Invalid tokens, mismatched filters and changed list snapshots are explicitly refused, so restart the listing after a mutation. `limit=0` returns no rows, positive fractions are floored and negative limits are refused.

See [all TUI triggers and examples](TUI.zh-CN.md).

## Passive monitoring

Tasks records work; it does not control model execution. The extension registers no settlement, request-context or tool-activity hooks. It adds no capability note, automatic reminder, waiting row or continuation row. Open tasks never request another model turn.

Before the final answer, the model can check unfinished work explicitly:

1. Call `list_tasks` with `statusFilter: ["pending", "in_progress", "blocked"]`.
2. Follow each returned cursor to read all matching rows.
3. Call `get_task` for each task that needs a full check.
4. Report unfinished work or record completion with its evidence.

This check is a caller action, not a runtime requirement. Tasks never treats a final answer as task completion. Existing state and evidence checks still apply to `update_task`.

The retired settlement helpers, capability-note helpers and status-message renderer are removed, including their public exports. No compatibility implementation remains. This removes the old automatic-execution API; the four task tools and saved task format remain unchanged.

## Persistence and compatibility

```text
~/.pi/agent/tasks/<sessionKey>/tasks.json            atomic replacement, one writer
~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      exclusive-create claim intents
~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json exclusive-create submit intents
```

Standalone Tasks restores tasks.json at session start and persists after changes. A coordinator claiming the store takes sole writer responsibility. Publishing a participant registry alone does not claim the store. Session switches detach the old writer before loading new state. A present unreadable or incompatible file raises a notice and is not overwritten as an empty store. Task files remain version 2.

Legacy recovery_hold maps to blocked. Legacy superseded maps to a normal state plus its preserved replacement relation; a missing replacement retains replacementUnresolved metadata and stays inactive with a repair notice. It cannot be retaken, deleted or used as a dependency until its replacement relation is repaired. In-progress work restored without participants becomes blocked. Completed records, results, recovery notes and replacement relations remain. Legacy execution records are classified without deleting their history. The previously retired board.json is not loaded, copied or removed.

The store normalizes restored fields and reports repairs. Context updates merge historical findings. An explicit outstanding list replaces the current list; an empty list clears it. The default retained-text budget is 64 KiB, including subject, description, verify, evidence, blocker, failure evidence, recovery notes, retained evidence history, resources and context; callers may lower it, not raise it. Model writes exceeding the budget are refused rather than silently truncated. Runtime stop cleanup always retains its diagnostic and releases the stopped holder, including for legacy records already beyond their budget.

Task intents use exclusive creation; only the store owner writes task state. Resource compatibility helpers remain for known consumers. `TASK_HOLDER_ENV` and the participant seam use pi-kit contracts rather than duplicated registry types.

## Verification

Behavior contracts live in features/ and regression checks in tests/.

```bash
python3 -m pytest packages/tasks/tests/ -q
pnpm typecheck
pnpm --dir packages/tasks pack --dry-run
uv run --with pyte python packages/tasks/tests/task_native_frames.py --output /tmp/tasks-native-frames
sh packages/tasks/tests/tasks_docker.sh
```

Native CLI/TUI checks use real Pi with a deterministic local provider, without credentials or model network requests. Such checks prove runtime behavior, not real-model judgment. Validation evidence and limitations are recorded separately when the full gate completes.

## License

MIT
