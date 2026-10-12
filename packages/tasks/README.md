# @fradser/pi-tasks

Tasks is a durable work list with dependencies and completion evidence. A goal is one objective pursued until achieved; a task is one unit of work to order, take, and finish.

```bash
pi install npm:@fradser/pi-tasks
```

The extension registers four tools and uses `@fradser/pi-kit` for shared rendering, persistence primitives and participant contracts. Agent Teams consumes the same store; Tasks does not spawn workers or add a research, archive or separate history workflow. The tools do not reach a child process. A subagent cannot take or complete a task, so the leader records the outcome from its report.

## Tools and states

| Tool | Purpose |
| --- | --- |
| `create_task` | Record subject, description, dependsOn, verify and optional replacement relations. |
| `get_task` | Read one task in full, including evidence and successor context. |
| `list_tasks` | Read compact summaries with statusFilter, claimable, ready, limit and cursor. |
| `update_task` | Edit content and/or apply one guarded transition. |

| State | Meaning | Next action |
| --- | --- | --- |
| pending | Work available after its dependencies complete, including reopened work. | in_progress |
| in_progress | The caller holds the attempt. | completed or blocked |
| blocked | Work needs a blocker resolved or a previous attempt inspected. | in_progress with reason |
| completed | Success delivered with evidence and required verdict. | pending to reopen |

A dependency-unfinished task remains pending and shows `Blocked by #N`. It cannot start or successfully complete until its prerequisites complete. `supersededBy` is a replacement relation, not a fifth status. Replaced records remain readable but are excluded from pending, claimable, ready and continuation work. A holder of replaced work must acknowledge cancellation before releasing its lease.

`update_task` routes status transitions:

- `in_progress`: take the task for the derived caller; blocked work requires `reason` explaining safe recovery. Recover blocked work before submitting a successful completion.
- `blocked`: record `reason`, release the caller's attempt and retain previous evidence.
- `completed`, `outcome=success`: record `result`; dependencies, prior attempt and a declared verify gate must satisfy the completion checks. A gate requires `verdict=pass`.
- `completed`, `outcome=failed`: retain the failure result and move to blocked. A later success keeps `failureEvidence` alongside the new result.
- `pending`: reopen a completed task while retaining its evidence. Completed or held transitive dependents become blocked; their conclusions are withdrawn and leases released. Recovery must address the reopened premise.

The store records a verdict; it does not run the verification prompt itself. Library consumers can request completion checks individually; model-facing tools request all checks. Ownership is derived from the caller, never an assignee parameter. Foreign holders, replacements, invalid graphs and invalid transitions are refused.

Content edits replace subject, description, dependsOn or verify; context merges successor information. Unknown dependencies and cycles are refused, and held/completed work cannot acquire unfinished prerequisites. One call may edit content and status: an accepted edit survives a refused status, and the result says so; a refused edit records neither half.

## Rendering and pagination

All tool results and automatic messages use the shared pi-kit `[tasks]` lifecycle style. Explicit tool results wrap titles, descriptions, Verify, evidence, blockers, errors and persistence notices in full. Automatic waiting messages are collapsed by default. Use Ctrl+O or the native row action to expand their complete details. Display numbers follow creation order across the full task set; filtered pages can contain gaps. Storage ids, holders and resource locks remain in coordination data rather than ordinary rows. The public tools do not accept or return resources.

```text
[tasks] create · #2 Verify dependency handling (pending)
Description:
Exercise the dependency transitions and record the evidence.
Verify:
The affected tests pass.
Depends on #1
Blocked by #1
```

A list contains summary fields, not descriptions, gates or full results; use get_task for those. Pages return at most 40 tasks. `count` is the number of matching records, `shown` the current page size, `offset` its position and `cursor` the next page token. Pass cursor back to read the next page; filters travel with it. Invalid tokens, mismatched filters and changed list snapshots are explicitly refused, so restart the listing after a mutation. `limit=0` returns no rows, positive fractions are floored and negative limits are refused.

See [all TUI triggers and examples](TUI.zh-CN.md).

## Automatic continuation

Pi's `agent_before_settle` checks normal completion. It continues only when all of these hold:

- New successful tool work occurred in this run. Repeated identical tool arguments/results, Task bookkeeping and monitor polling do not count.
- A normal task can run: an unheld pending task with completed dependencies, or an in-progress task held by the caller.
- Fewer than three automatic continuations occurred since real user input.
- No abort, pending user input or continuation requested by another handler exists.

A distinct successful tool result establishes tool activity, not verified task progress. Task metadata changes alone never buy another turn. Extension-generated input does not reset the allowance. Replaced tasks and internal `recordKind=execution` records never trigger continuation. Blocked work waits for deliberate recovery; the harness does not clear blockers or infer authorization.

Automatic messages display `continue` or `waiting`. Continue messages show full task information. Waiting messages show the headline by default; expansion shows the reason, current blocker, handoff, original plan and evidence. Allowance exhaustion is waiting, not a user pause. Identical waiting snapshots are deduplicated. No UI means no passive row, preserving the final `pi --print` answer. Earlier boundary messages and context edits are retained. Model instructions are bounded to 20 task rows and 8 KiB; omissions direct the model to list_tasks. Display rows use full stored text.

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
