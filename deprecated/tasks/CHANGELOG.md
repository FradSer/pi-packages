# @fradser/pi-tasks

## 0.2.0

### Minor Changes

- e86a44f: Four tools, one noun. The task board is now `create_task` / `get_task` / `list_tasks` / `update_task` — the same shape as `create_goal` and `get_goal` beside it — and the three names for one thing are gone.
  
  **The surface**
  
  `@fradser/pi-tasks` used to register a single `task` tool with an `action` parameter. It now registers four tools, one per operation. The decomposition follows Claude Code's task tools for one reason that matters more than the resemblance: a position in the lifecycle is reachable by exactly one call, and a refusal can name the call that earned it.
  
  The names are not Claude Code's. They follow this workspace: verb first, the noun as the object, snake_case — `create_task` beside `create_goal`, `get_task` beside `get_goal`. A PascalCase name imported from another product reads as someone else's vocabulary in a session where every other tool here is snake_case.
  
  - `create_task` records what must be done, and takes `supersedes`, which replaces an obsolete task atomically and re-points every dependent at the replacement.
  - `get_task` reads one task in full, including the structured brief a successor needs. `list_tasks` is bounded and leaves the brief out, so this is how a brief is read; without it a handoff is written for nobody. It accepts an `id` and nothing else.
  - `list_tasks` reports the state a model would otherwise have to infer: who holds each task, whether a recovery hold is set, what it depends on. A pending task that must not be taken is otherwise indistinguishable from one that may.
  - `update_task` is the fat one — status, content, brief — the same division Claude Code uses, where one declaration covers four operations rather than four declarations competing for the prompt.
  
  **Breaking**
  
  - The `task` tool and its `action` parameter are gone. A caller that used `action: "create"` uses `create_task`; `action: "list"` uses `list_tasks`; `action: "take"`, `action: "complete"` and `action: "reopen"` all become `update_task` with `status: "in_progress" | "completed" | "pending"`.
  - `BoardTask` is now `Task`. It is re-exported from `@fradser/pi-agent-teams`, so a consumer of that package's types sees the new name.
  - The store and file symbols lost the board prefix: `loadBoard` → `loadTasks`, `clearBoard` → `clearTasks`, `boardDiagnostic` → `storeNotice`, `configureBoardStore` → `configureTaskStore`, `isBoardStoreClaimed` → `isTaskStoreClaimed`, `onBoardChanged` → `onTasksChanged`, `BoardStoreHooks` → `TaskStoreHooks`, `boardFilePath` → `tasksFilePath`, `readBoardFile` → `readTasksFile`, `writeBoardFile` → `writeTasksFile`, and `WORK_RUNTIME_VERSION` → `TASKS_FILE_VERSION`.
  - The task file is `tasks.json`. It is still **read** as `board.json`, so a task recorded by an earlier install is picked up rather than orphaned, and a session that loaded the pre-rename file says so. Writes only ever go to `tasks.json`.
  - `TASK_CAPABILITY_TOOLS` lists the four names, so a spawner granting a capability has to be updated. A grant of `"task"` now matches nothing.
  
  **What did not change, deliberately**
  
  - No delete. Claude Code removes a todo with `status: "deleted"`; this package's contract is that a task carrying a result, a dependency or a completed attempt is real work, and real work is returned to pending rather than erased.
  - A completion still needs an explicit `outcome`. Collapsing it into `status: "completed"` alone would let a completion be a field assignment rather than a judgement with evidence, which is what the old `complete` action existed to prevent.
  - `dependsOn` is not mutable through `update_task`. Supersession re-points dependencies, atomically and cycle-checked, which is the mechanism this package already pins.
  - `status` is refused by name when it is outside the three routes, instead of falling through to the content branch where a caller would be told it had supplied nothing to change.
  
  **Verification**
  
  `python3 -m pytest packages/tasks/tests/ -q` (71 passed), `packages/agent-teams/tests/` (280 passed), `pnpm typecheck`, and the tool-parameter schema fixture. Driven live on Pi 1.0.0 as well: a throwaway extension called all four registered tools through `ctx.executeTool` for twenty-seven steps of a full lifecycle — create, get, list with each filter and cap, take, twice-take, a brief written twice, read back, every refusal a caller can earn, failure and recovery, completion, double completion, reopen, an unmet dependency, a supersession, and an unknown field. Seventeen accepted, ten refused, and the supersession reached the file with the brief intact.
- e86a44f: Retire the task board vocabulary and the `board.json` persistence fallback. Load and write only `tasks.json`. Remove the retired path and resolver exports. Preserve old files without automatic migration or deletion.
  
  Rename shared assignment kind `board` to `task`, use task-prefixed attempt ids, and rename worker binding to `PI_TEAMMATE_TASKS_FILE`. Use task names in coordination callbacks, notices, and console navigation. Update all contributing packages together and restart existing children before using the new bindings.
  
  This is a breaking library and worker-protocol change for these pre-1.0 packages. Task file format version 2, completion evidence, dependency rules, ownership, and recovery remain unchanged.
- e86a44f: The task board reports itself as data, stops losing the file it owns, and a session switch no longer writes to the session that was left.
  
  **Durability**
  
  - A board a participant registry was published beside now keeps its board file. The extension stood down whenever `isCoordinated()` was true, and that also answers true for a board that merely knows about other holders — where the default store's own change hook is a no-op and nobody is writing the file. Every install of this package beside `@fradser/pi-subagents` that did not also install a layer claiming the store recorded tasks in memory and left no board on disk, with nothing reporting it. The narrower `isBoardStoreClaimed()` answers the question the file actually turns on, and `isCoordinated()` keeps its meaning of "this board has participants".
  - Standing down no longer empties the board. Clearing the in-memory board happened before the claim was checked, so on the claimed path the handler cleared the board the claimer had just restored and returned without reloading it — and because a clear records no change, nothing noticed before the claimer's next snapshot persisted that emptiness over durable work.
  - `onBoardChanged()` releases the board writer, and the extension entry does so at the top of every `session_start`. `session_start` re-fires on `/new`, resume, and fork; if the new session's board file was present but unreadable, the handler returned before attaching a writer and the previous session's writer stayed attached. Work recorded under the open session then landed in the file of the session that had been left: two boards, one writer, and neither holding what it claimed.
  
  **The result is data**
  
  - A result states what changed and leaves how to call the tool to its declared description, which is in the prompt either way. The `create` result used to end with a `NEXT ·` line naming the next call; it duplicated the description verbatim in spirit, and it was the only result line reaching the human row, so the one action whose row carried a body had model-facing call syntax in it. Every row now reads the same way, and a plain creation leaves its headline alone. A creation that made tasks obsolete still says so on the row, because that is state a person wants.
  - The `task` tool declares an output schema and returns `structuredContent`, so a codemode script asking which work is claimable receives the task projections instead of a `TASK · id · status · subject` text block it has to take apart. The per-task shape is declared property by property rather than as a bare `object`, which would have handed the script an untyped bag and put it back to reading prose. A refusal is data too: it is still marked as an error for the model and still carries what the board knows.
  - The tool declares `openWorldHint: false`, `readOnlyHint: false`, and `idempotentHint: false`. It makes no claim about destructiveness, because it cannot keep one: `reopen` erases the result a completion recorded, and `create supersedes` has no inverse verb in the closed action set.
  - A `limit` sent by the caller now applies, where it was previously declared and then read only from a programmatic option. Every stated cap applies and the board's own ceiling applies regardless. `0` is honoured as the request it is, a fractional cap is floored before it is applied, and a negative one from a model is refused by name rather than dropped as though it had never been sent.
  
  **Bounded context**
  
  - `context` is a declared object rather than a bare one, and a field the board has no definition for is refused by name instead of cast into storage. A misspelled brief was retained on the Task verbatim: read by no successor, formatted into no brief, and not counted against the byte budget. The store now reads a context through the same check on its own account, at every level — a top-level-only check still dropped a misspelled field inside a handoff and reported success to a coordinator calling `setTaskContext` directly.
  - The budget measures everything a Task retains: subject, description, completion gate, recorded result, resource tags and context. It previously counted three of those, which left `verify` — free text a model writes in its own words, re-serialized on every board write — unbounded, and a creation was not budgeted at all. Resource tags had no ceiling at all, unlike every other model-supplied list on a Task, so the board file could be grown without limit for the price of one argument. A refusal now names the task by its derived id rather than quoting the offending input back, which turned a 70 KB subject into a 70 KB error.
  - A budget may be set below the board's default and never above it. The budget is the only thing bounding a brief, so a caller able to raise it removes the bound: one update naming a gigabyte was enough to put megabytes of findings on a single task, re-serialized on every change after it.
  - A brief is folded into the one a Task already carries. Findings and outstanding work are added to across updates, so a successor recording its own delta can no longer drop what the outgoing attempt found. The union is linear: it ran on every update against a list that can hold thousands of entries, and measuring that showed 200 merges over 8200 findings taking 15.8 seconds on the interactive tool path. It is 124 ms now. There is deliberately no count cap on findings, because a cap would drop the one thing the brief exists to carry; the byte budget is what bounds the list, and it is enforced on the write that grows it.
  - A supersession now reaches the durable board file. The change mark sat between recording the replacement task and rewriting the obsolete one, so a session whose last change was a supersession persisted a board still saying the obsolete task was pending and its dependents still pointed at it — and nothing marked it again, so a restart loaded that disagreement. Every in-memory assertion of this transition passed, because memory was always right.
  - A restored board is read back through the same checks a write applies, because `loadBoard` is the other route into the store. Validating only on the write path left a restored `budgetBytes` unclamped — one hand-edited line was enough to put a Task back over the ceiling the rest of this work exists to hold — a context spread straight off disk, and a `dependsOn` holding something other than task ids. A status the board cannot define is kept, held, and reported rather than adopted, so a restored board can never hold a state the store never enters and no projection can fail its own declared schema. What a restore had to repair is reported, not swallowed.
  - A context that would record nothing is refused. A context whose every value was blank normalized to nothing and reported success, which is the same "your brief was recorded" lie as a misspelled field, relocated from a misspelling to a blank. A blank field beside a real one is still fine.
  - `TaskStatus` is now a union derived from a runtime list, so the board's statuses, the declared result schema, the list filter, and the restored-status check all read from one place. They were four hand-written copies, and a status added to one left the declared schema quietly describing four while every projection of the fifth failed it.
  - A note on a reference can be corrected, and a budget of less than one byte is refused rather than floored to a ceiling no later write could satisfy.
  
  **Verification**
  
  `python3 -m pytest packages/tasks/tests/ -q` (68 passed), `packages/agent-teams/tests/` (281), `packages/subagents/tests/` (466), `pnpm typecheck`, and the `agent-teams` tool-parameter schema fixture, whose `context` sample now uses the declared handoff shape and asserts that a string or misspelled handoff is rejected.
  
  Driven live on Pi 1.0.0 as well: a throwaway extension called the registered `task` tool through `ctx.executeTool` for all twenty-three steps of a full lifecycle — create, list with each filter and cap, take, twice-take, a brief written twice, both refusals a context can earn, failure and recovery, completion, double completion, reopen, an unmet dependency, a supersession, and an unknown action — which is how the missing supersession mark was found, since every one of those steps is right in memory and only the file was wrong. Sixteen accepted, seven refused by the board and three by Pi's own parameter validation before the handler ran.
- e86a44f: `@fradser/pi-tasks` now honours the boundary it claims, and a standalone install
  is durable.
  
  ## The boundary is enforced, not asserted
  
  The package documented that it knows nothing about processes, rosters, or peer
  mail, and the test that claimed to enforce it only checked import specifiers and
  four words. The source had meanwhile grown a `spawnId` comparison, `Leader`
  comments, and a symbol key naming `@fradser/pi-subagents` — a coupling that
  compiles, passes every behavioural test, and produces a wrong board.
  
  **What moved out of `store.ts`.** The leader-half is gone: `createDirectWork`,
  `discardDirectWork`, `reclaimDirectWork`, `reopenCompletedWork`, and
  `releaseTasksOf` were process operations wearing domain names. What remains is the
  board and its transitions, in Task and holder vocabulary.
  
  **The seam is declared once.** The participant registry — shape and key — moved
  into `@fradser/pi-kit`, which owns no consumer and is already a dependency of both
  sides. It was previously a hand-written mirror in each package, and a mirror is
  exactly how that stops matching: a renamed field showed up as a silently wrong
  assignment. The registry interface also gained `current(holder, incarnation?)`,
  so this package asks whether a participant can act instead of reading its liveness
  and incarnation itself. `@fradser/pi-subagents` answers it from the roster, which
  is the only layer that knows.
  
  **The environment binding belongs to the board.** The tool read
  `PI_TEAMMATE_WORKER_NAME` — another package's private variable. It now reads
  `TASK_HOLDER_ENV`, which this package exports, and `@fradser/pi-agent-teams`
  spells it by import. The old coupling was a rename away from silently turning every
  participant's take into a take by the main session.
  
  **The test now enforces the claim.** `test_the_package_imports_no_coordination_concept`
  bans the runtime vocabulary across every source file, `test_the_package_names_no_sibling_package`
  fails if a sibling package is named at all, and
  `test_the_package_owns_its_own_environment_binding` pins the binding name.
  
  ## An installed-alone board survives a restart
  
  The package claimed durable board persistence, and only a coordinator ever wrote
  the file. Installed on its own, the board lived in memory and vanished with the
  process; no test covered it, because the e2e only checked one create/take/complete
  loop in a single process.
  
  `src/extension.ts` now reads the board at session start and writes it after every
  change when nothing else owns the store. A coordinator that claims the store keeps
  sole ownership and this package stands down, so two writers on one file is not
  reachable. A present-but-unreadable board is reported through
  `boardDiagnostic()` and appears in `list`, and the process does not become the
  writer for a file it failed to read.
  
  ## The row is a row
  
  `taskRowSpec` was written, exported, and never supplied: the extension passed no
  `renderResult`, so every real session got Pi's default rendering and the spec was
  only reachable from a test. `src/rows.ts` now binds the geometry once through
  pi-kit's `bindLifecycleRenderers` and the extension attaches it, matching how
  `@fradser/pi-subagents` and every other tool in this workspace paint a row. This
  is why `@earendil-works/pi-tui` is now a declared `*` peer.
  
  ## One function per behaviour, in Task vocabulary
  
  `reopenCompletedWork` and `reopenTask` were the same transition under two names
  and two vocabularies; the second is gone. The runtime-only transitions were renamed
  for what happened rather than for the act: `revertInFlightAttempt` became
  `revertUndeliveredTake` and now names its holder, `releaseTasksOf` became
  `failTasksHeldBy`. `bindTask` and `discardTask` replace the direct-work trio, and
  `BoardTask.deferredMessages` is gone: a peer message is a coordination record, and
  the board states what must be done rather than what was said about it.
  
  `BoardTask.errorMessage` is removed. Nothing ever wrote it, and the changeset
  moving retained evidence to `result` had already made it vestigial.
  
  ## The per-Task context budget is enforced
  
  `withinContextBudget` was exported and never called, so the budget that stopped a
  long-lived Task from growing without limit was declared and never applied.
  `setTaskContext` and `updateTask` now refuse a patch that would exceed it.
  
  `createBoundWork` in `@fradser/pi-agent-teams` composes `createTask` with
  `bindTask` and rolls the creation back on refusal, which is what the removed
  `createDirectWork` did. `TaskIntent.worker` is now `TaskIntent.participant`, and
  operator-visible board errors say "Task board" rather than "Work snapshot", which
  already said "Work" for a package whose tool is `task`.
  
  ## Publishing
  
  `@fradser/pi-tasks` and `@fradser/pi-kit` are unchanged in their published
  contract; this release only adds to them. `@fradser/pi-tasks` still needs its
  first interactive publish and npm trust setup before `@fradser/pi-agent-teams`
  can release, per the ordering pinned in `PUBLISH_SCOPE`.
- e86a44f: A completion is checked against the board's own facts before it is recorded.
  
  **The scenario this exists for.** A model splits a large task into n tasks that may depend on each other, takes them in series or in parallel, then marks them complete. The board is the only thing that sees the whole sequence, and until now it checked almost nothing on the completion path: the dependency graph was enforced when *taking* a task and not at all when *completing* one, and any caller could close a task that had never been taken.
  
  That let a model produce a board like this by bulk-marking four tasks complete:
  
  ```
  t1 pending    depends=[]
  t2 completed  depends=["t1"]      <- its dependency is not done
  t3 pending    depends=["t1"]      <- never taken
  t4 completed  depends=["t2"]
  ```
  
  A completed task depending on an unfinished one is precisely the state the graph
  exists to make impossible, and the board could not tell it apart from real work.
  
  **The checks**, all of them facts the board already holds:
  
  - **A dependency must be completed.** The refusal names the unfinished one, so the
    model can complete it and retry — which is also what makes a parallel batch
    recoverable: the dependents are refused, the finished ones stand.
  - **A success must record a result.** A success is a judgement against the task's
    requirements; it carries the evidence for that judgement.
  - **A task nobody worked on cannot be accepted.** A holder that *died* leaves a
    recovery hold behind, and that is what makes an unheld task acceptable again —
    the fallback path so dead work is not stranded. A task that was never taken has
    no attempt on the record, so accepting it is a bare assertion. Those two states
    were conflated; `test_an_unheld_task_accepts_fallback_acceptance` pinned the
    broad fallback while its own docstring described the narrow one, and its setup
    never built the dead-holder state it claimed to test.
  - **A declared gate must be answered.** `verify` is a prompt, and a board that
    evaluates prompts runs agents, so the board does not run one. It demands the
    answer and records it: a completion of a gated task carries
    `verdict: "pass" | "fail"`, and the task keeps `completionVerdict` and the gate
    it answered, so a later reader can tell a gated completion from an unchecked
    one. The answer is still taken on trust — the board cannot know otherwise — but
    the omission becomes impossible.
  
  **All four are opt-in** (`ALL_COMPLETION_CHECKS`, and one at a time), because a
  coordinator that already verifies a submission by other means would otherwise be
  refused for work it has already checked. `update_task` asks for all of them,
  because that is the path a model drives.
  
  **The other door, closed in the same change.** The invariant was reachable from
  the reopen side too: nothing completes on an unfinished premise, but reopening a
  *premise* left the conclusions standing on it. `status=pending` now pulls back
  everything transitively standing on the reopened task — a completed dependent had
  a conclusion withdrawn, one being worked on had an attempt invalidated — each
  returned to pending under a recovery hold, naming what withdrew its premise, with
  its evidence kept, its recorded gate verdict withdrawn, and its lease released.
  
  **Reopen is unconditionally available.** Only two refusals remain and both are
  definitional: no such task, or it is not completed. It was previously also refused
  while a dependent was being worked on, and that rule was wrong twice over.
  Reopening is the only way back from a completed task, so refusing it strands the
  work for everyone who ever depended on it; and refusing it only sometimes gave one
  operation two answers depending on who happened to be holding what at the time.
  `test_reopening_is_refused_while_a_dependent_is_in_progress` pinned that rule and
  now pins its replacement — the same reopen succeeding whether the dependent is
  completed or in progress.
  
  **And the marker path.** A completion submitted through an intent marker — the
  file a spawned participant writes instead of calling a tool — is the same
  completion, so it now carries the same checks and the same verdict. Without that,
  every rule above was advisory to any participant willing to write a file.
  
  One bug found on the way: `applySubmissionIntent` returns an `error` while
  `completeTaskWithOutcome` returns a `reason`, so threading the options through
  handed the object straight back and dropped the only sentence saying *why* a
  submission was refused. A participant refused with nothing to act on.
  
  **Verification.** `python3 -m pytest packages/tasks/tests/ -q` (76 passed) and
  `pnpm typecheck`. Driven live on Pi 1.0.0 as well: a throwaway extension split a
  task into four, took them out of order and in parallel, and tried every completion
  shortcut — the board refused an early take on an unmet dependency, a success with
  no result, a completion of a task nobody took, a gated completion with no verdict,
  and one with `verdict: "fail"`, then accepted the same completion with
  `verdict: "pass"` and recorded the gate. The persisted board held
  `t2 pending` while nothing claimed it completed. A three-deep chain was then
  completed and its premise reopened: both conclusions came back to pending naming
  what withdrew them, their evidence intact, and the board held no completed task
  depending on an unfinished one.
- e86a44f: The completion checks gained a read side: a caller can ask what blocks a completion instead of only finding out by failing one.
  
  `update_task status=completed` refuses and names the blocker, which is the write side. A model that split a task into n and just finished one has the other question — which of the rest can be marked done *now* — and answering it by attempting each completion is n refusals to learn n facts the board already holds.
  
  - **Every task carries `blockedBy`**: the ids among its `dependsOn` that are not completed. `dependsOn` says what the edges are; this says which of them are unfinished, which is otherwise a comparison against a list made by hand. Absent when nothing is blocking it.
  - **`list_tasks` takes `ready`**: the tasks that could be completed right now — an attempt on the record (in progress, or pending under a recovery hold a dead holder left) with every declared dependency completed. It is the mirror of `claimable`, which answers what can be started; the two together are what makes a batch of n recoverable without a refused completion per task.
  
  Both are pure functions of state the store already holds, and the declared output schema says so, so a codemode script reads the same thing a model does. A task nobody has touched is not completable however finished its dependencies are: there is no attempt to accept.
  
  Verified in `packages/tasks/tests/` (85 passed) and through the tool surface in a live Pi 1.0.0 session: a four-task split with one finished returned exactly the newly-unblocked dependent from `list_tasks {ready: true}`, while every task in the full list named what was still unfinished.
- e86a44f: Simplify task rows around the task name, detailed body, dependencies, and status. Remove holder rows from the transcript. Keep runtime ownership in structured results and persisted data.
  
  Allow `update_task` to replace the subject and dependency list without changing the task id. Validate unknown ids, self-dependencies, dependency cycles, and the dependency count before recording changes. Refuse unfinished prerequisites on in-progress or completed tasks. Require separate calls for content edits and status changes.
  
  Return summaries from `list_tasks`. Keep full descriptions, completion gates, evidence, and gate verdicts available through `get_task`. Preserve completion checks and bounded continuation of unfinished work.
- e86a44f: Make task dependencies the primary tool interface. Return unfinished task state to the model before normal settlement.
  
  ## Task tools
  
  Remove `resources` from the four tool parameter schemas, task projections, tool descriptions, and transcript rows. Use `dependsOn` for prerequisites and `blockedBy` for unfinished prerequisites.
  
  Independent tasks can run in parallel. Dependent tasks wait until all prerequisites complete. Stored resource fields and library helpers remain compatible with existing data and known consumers.
  
  ## Settlement check
  
  Register an `agent_before_settle` handler. If unfinished work can proceed, append a bounded task snapshot to model context and request one continuation.
  
  The snapshot includes task ids, status, holders, and unfinished dependencies. It directs the model to perform work before recording completion evidence. The harness never marks work completed.
  
  Permit at most three automatic task continuations per real user input. Extension-generated input does not reset the allowance. Report unfinished work when the limit is reached.
  
  Do not continue after cancellation or provider errors. Respect queued input and continuation already requested by another handler.
  
  Return blocked or recovery-held work for one inspection continuation per task snapshot. A passive status row alone does not reach another model request. The model reads the task and checks whether recovery is safe and authorized before supplying a recovery reason. The harness never clears holds or transfers ownership itself.
  
  After inspection, unchanged blockers receive a specific passive waiting message, not repeated automatic attempts. Inspection shares the same three-continuation allowance.
  
  Preserve entries from earlier boundary handlers when appending the task message. Repair missing or non-string task ids using the persisted key under a recovery hold, so one malformed record cannot disable reminders for valid work.
  
  Render one compact transcript row. Keep the full snapshot in model context, bounded to 20 tasks and 8 KiB.
  
  ## Verification
  
  Test the real Pi lifecycle with a deterministic provider. Reproduce premature settlement after setting `in_progress`, then verify that the next model request receives task state and completes dependent work.
  
  Also test a model that ignores reminders. Verify that only three additional requests run and unfinished task status remains unchanged.
  
  Resume a real saved session containing an interrupted task. Verify that blocker inspection reaches the next provider request, checks the saved artifact, recovers with a reason, performs and reads back work, and completes the task.
  
  Test an unresolved recovery blocker separately. Verify that inspection does not change its hold or retry it without resolving the blocker.
- 53cb34f: A Work Item now owns bounded context, and a successor handoff is a structured brief instead of concatenated prose.
  
  **@fradser/pi-tasks**
  
  `src/context.ts` adds the per-Work-Item context that was previously rebuilt ad hoc at each reassignment:
  
  - `WorkContext` on `BoardTask`: `workspacePath`, `handoff`, `refs`, `budgetBytes`.
  - `WorkHandoff`: `candidate`, `delta`, `verification`, `priorFindings`, `outstanding` — the fields a recheck actually needs. `priorFindings` exists specifically so prior review findings survive outside the result that a reopen clears.
  - `buildWorkHandoff` bounds each field to its share of the budget and reports whether anything was clipped. `clipToBytes` never splits a UTF-8 sequence and appends `[context clipped to budget]`, because a silently truncated brief is worse than a shorter one that announces itself.
  - `workContextBytes` / `withinContextBudget` measure description, result, error, handoff, and refs against the budget, so a long-lived Work Item cannot grow without limit.
  - `normalizeContextRefs` de-duplicates by kind and id, drops empties, and caps the list at `MAX_CONTEXT_REFS`.
  - `formatWorkHandoff` gives the brief one shape instead of one per caller.
  
  No session identifier is stored anywhere in this package. A Work Item records the workspace path it ran in and leaves session resolution to Pi, which groups sessions by working directory. That boundary is what keeps `@fradser/pi-tasks` free of the process layer, and `test_a_work_item_records_a_workspace_path_and_never_a_session_id` asserts it against the source rather than only the data.
  
  **@fradser/pi-agent-teams**
  
  `buildSuccessorHandoff` now builds its brief through `buildWorkHandoff` and `formatWorkHandoff` rather than joining prose lines. Prior leader reports go into `priorFindings` rather than a "Recent leader reports" string. The `SUCCESSOR HANDOFF FROM @name` heading and the `kind id` form of the prior assignment are preserved, so the existing handoff assertions still hold unchanged.
  
  `setTaskContext` records the Agent workspace path on the Work Item after a successful isolated spawn. It is additive: an existing field is only replaced when the caller supplies a new value, so recording a workspace path cannot erase a handoff written earlier.
  
  Contract: `packages/tasks/features/work-context.feature`.
- 7ac2735: Make creating a task lighter and the tool surface smaller.
  
  **What changed**
  
  - A `subject` is a short name of at most 60 characters. `create_task` and `update_task` refuse a longer subject and point at `description`. The store and its internal callers stay permissive, so Agent Teams keeps creating its generated work records.
  - `description` and `verify` are documented as optional; a subject alone is a complete task. The previous wording told the model to put the full brief in `description`, which made every creation carry a paragraph.
  - The four tool descriptions and every parameter description were trimmed. The registered surface is about 6044 characters instead of 7482, roughly 1510 tokens instead of 1870, sent on every request. The `update_task` context schema is about a third shorter.
  
  Contract: `features/discoverability.feature`, `features/work-domain.feature`.
  
  **Verification**
  
  - `tests/test_task_contents.py` refuses a 61-character subject with a message naming the limit, accepts 60, and refuses a long rename.
  - `tests/test_discoverability.py` asserts the tool surface states the short-name rule, the limit, that a subject alone is complete, and that detail goes in `description` only when it does not fit.
  - `tests/test_list_titles.py` creates its long-title fixture through the store, because the model-facing tool no longer accepts that subject.
  - The tasks suite and the Agent Teams consumer suite pass.
- df91761: Make the task tools discoverable, and stop charging for the checks that guard them.
  
  The four tools were registered and reachable, and a session that had never seen a task had no reason to look: measured over 1152 recorded sessions, `create_task` ran 17 times in 7 sessions while `bash` ran 78178 times. The package's only presence was a reminder that fires when unfinished tasks already exist, so it could sustain the habit and never start it.
  
  - The trigger conditions live in two surfaces. `create_task` states when recording a task is warranted and how a task differs from a pi-goal goal, in its snippet and its description, and those are sent to the provider on every turn already. On top of them the package injects one bounded note per request, because a description cannot say when the situation calls for the tool: a session that never considers recording work never reads the description of the tool that would record it. The note carries no task state, so it is identical on every turn and lands at a fixed index after the system prompt, which keeps each request a prefix of the last one. It is injected as a **system** message through `context_with_system`: the plain `context` hook cannot carry system messages, so a note sent that way lands ahead of the user's request as a user-role message, and a recorded run showed the model reporting it as the user's own message while it was in context.
  - A context-only edit is no longer progress. The settlement snapshot hashed `context` along with the work, so a bookkeeping write bought another automatic continuation. A brief is what a successor reads, not a change to the task, and it no longer counts toward the continuation allowance.
  - The settlement reminder is shorter, and the blocked-work instruction is emitted only when a recovery hold is present. The body carried fourteen instruction lines repeated at every settlement; one recorded session spent three of these messages on a single task.
  - The `inspect` status word is gone, so the reminder has three states instead of four: `continue`, `waiting`, `paused`. This is a wording and branch simplification, not a reduction in rounds — `inspect` and `continue` already shared one continuation and one model turn. A blocked snapshot now says `continue` and names the blocker in its waiting reason.
  - The `update_task` description no longer tells a caller to use separate calls for a content edit and a status change. The behaviour had already changed to accept both in one call, and the description was still instructing the extra round trip.
  - A handoff field written at the context level is moved into `context.handoff` instead of being refused. The field names are unique to the handoff, so the caller meant the handoff and said it one level too high.
  - A field no layer of the context owns is refused with a message that names the field and says where the handoff fields belong. The nested schemas are open for this reason: a closed one made the validator the author of the refusal, and its wording was `schema is false`.
  - One `update_task` call may carry content edits and a status change. The content half is validated and recorded first; a refused status keeps the edit, reports what stands, and names the status change as the half to retry. A refused content edit records neither half.
  - A task records who created it, and that record is what lets a caller deliver work it recorded and finished itself. `create_task` fills `createdBy` from the caller's own context, never from a parameter, and a completion from the recorded creator is accepted without a separate take. A caller that neither took the task nor recorded it is still refused: the rule asks for an accountable party, not for a call that records nothing new.
  - A refused completion names every unsatisfied check at once, with the remedy for each, instead of one per round trip. Taking a task reports what its completion must carry, so the call that finishes the work is also the call that satisfies the checks.
  - `checkCompletion` now returns every unsatisfied check rather than the first. It is exported, so a caller that reads its return value must read an array.
  
  The repository's `AGENTS.md` now states when to use the task tools, and records that they do not reach a child process: a subagent cannot take or complete a task, so the leader records the outcome from the child's report.
- 1c81c7a: Simplify Tasks to a guarded lifecycle with blocker recovery, cancellation and legacy-state migration. Keep replacements as relations, retain prior evidence, collapse every tool result and status row by default with native expansion, provide list cursors, and require effective work before bounded continuation. Update Agent Teams consumers for the Tasks state contract.
- 7ac2735: Give unfinished work an exit, and derive word-complete task ids.
  
  **What changed**
  
  - `update_task` accepts `status=cancelled` with a required `reason`. `blocked` means a blocker is in the way; abandoned work was recorded as blocked and counted as unfinished forever, so the settle reminder reported it at every settlement. A cancelled task keeps its record, reason and evidence, leaves the board, stops counting as unfinished or claimable, and is reopenable to `pending`. A cancelled prerequisite still blocks its dependents, because cancellation does not satisfy an edge.
  - `reopenTask` brings a cancelled task back to `pending` and clears its reason. Completed or held dependents are withdrawn exactly as they are for a reopened completion.
  - `taskIdFromSubject` truncates at a word boundary within the id limit and disambiguates duplicates with `-1`, `-2`, ... instead of cutting inside a word and starting at `-2`. The id is still minted once from the subject and stays the handle across a rename.
  - Agent Teams reports the cancelled count in its task summary and labels cancelled rows.
  
  Contract: `features/simplified-tasks.feature`, `features/work-domain.feature`.
  
  **Verification**
  
  - `tests/test_simplified_tasks.py` proves cancellation requires a reason, keeps the reason, stops claimable work, still blocks dependents, refuses a completed target, and reopens to pending.
  - `tests/test_work_domain.py` proves word-boundary truncation and `-1`/`-2` suffixes.
  - The tools suite and the Agent Teams consumer suite pass.
- e86a44f: Return one refusal shape from every task-store operation. A refusal is now `{ refusal, detail?, reason }`: a machine code from one closed set for a caller to branch on, the task, holder, or prerequisite it is about, and the sentence a caller or a model reads.
  
  Before this change the store returned the same sentence under five different shapes: `error` from a creation, `reason` from an edit, a completion, a reopen, and a bind, `refusal` with a `detail` from a take, and `error` again from a marker path. Only a take could be branched on without reading prose. The success flag is unchanged: `ok` for a task write and `applied` for a claim marker.
  
  This is a breaking library change for these pre-1.0 packages. Read `result.reason` where a result used `result.error`, and read `result.refusal` to branch on why. Every refusal word in the sentences themselves is unchanged, no rule about what may be done changed, and the four model-facing tools still report the same text. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together.
- e86a44f: Make a recovery hold a first-class status, at the same level as in progress. `TASK_STATUSES` gains `recovery_hold`, and the `recoveryRequired` flag is gone from the record, from every projection, and from the model-facing text. `pending` now means never attempted, and only that.
  
  A task that fails, that has its premise withdrawn by a reopen, or that is restored mid-attempt now sits in `recovery_hold` instead of `pending` under a flag. Taking from `recovery_hold` still needs a stated reason, and the refusal still names the state. A task row reads `recovery hold` in the status slot where it used to read `pending · recovery hold`, so a held task is no longer displayed as work that was never started.
  
  `claimable` and `ready` answer from the status alone: a claimable task is `pending` with every dependency met, and a completable one is `in_progress` or `recovery_hold`. The paired flag checks those predicates used to carry are gone.
  
  A task file written before this change restores correctly. A record with `pending` and `recoveryRequired: true` restores as `recovery_hold`, a record still in progress restores as `recovery_hold`, and the flag is never written back. The file format version is unchanged, because the reader normalizes both spellings rather than migrating the file.
  
  This is a breaking library change for these pre-1.0 packages. Read `task.status === "recovery_hold"` where a record used `task.recoveryRequired`, and drop `recoveryRequired` from anything that stored it. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together. Task file format version 2, completion evidence, dependency rules, ownership, and recovery rules are unchanged.
- 8662e95: Make Tasks a passive work record. Remove automatic settlement messages, continuation requests and capability injection. Remove the retired execution helpers and status renderer exports without compatibility implementations. Keep the four tools, persistence and state checks.
- 53cb34f: `@fradser/pi-agent-teams` is now a bundle of three independently installable packages, and the tool surface has changed. This is a breaking release: 1.0.0.
  
  ## The three packages
  
  | Package | Owns | Registers |
  | --- | --- | --- |
  | `@fradser/pi-subagents` | child process spawn and lifecycle, the child roster, workspace isolation, environment policy, Agent Memory | `agent` |
  | `@fradser/pi-tasks` | the task board: data model, status machine, dependency graph and resource rules, per-task context | `task` |
  | `@fradser/pi-agent-teams` | peer messaging, notices, Agent Presence, the Team Console | `message` |
  
  Installing `@fradser/pi-agent-teams` still gives all three tools: its manifest loads the other two extension entries. Each also works alone, and any pair works. A tool has exactly one registrant in every combination, which is what the split's own tests enumerate rather than assume.
  
  ## What a caller must change
  
  - **`work` is now `task`.** The package was already `@fradser/pi-tasks` and the type was already `BoardTask`, so `work` was the only name contradicting the other two — and it is a mass noun, which forced a model reading `work` plus an `action` parameter to decide whether the tool performs work or registers work items.
  - **`agent_event` is now `message`,** and its parameters are `to`, `body`, and `kind`. `body` avoids a caller writing `message: { message: … }`; `kind` is what the recipient owes the sender, nothing or a decision, rather than an intent the tool acts on.
  - **`agent` has four actions** instead of four differently named ones: `start` (with an optional `prompt`), `inspect`, `list`, `stop`. `delegate` and `start` were the same operation dispatched twice, differing only in whether a prompt was delivered.
  - **The board action set shrank from fourteen actions across two divergent schemas to five across one.** `assign`, `claim`, `release`, `abandon`, `reclaim`, `submit`, `supersede` and `get` are gone; `reopen` survives as `update status=pending` and `supersede` as `create supersedes`. A task names no owner, and there is no `assignee` parameter anywhere: a participant takes a task with `update status=in_progress`, and the caller is recorded as the holder.
  - **The board status `claimed` is now `in_progress`.**
  - A task failed, or an unfixable verification gate, returns to pending under a **recovery hold**, and the retry needs a stated reason. That replaces a leader-side release action: the runtime records an attempt as not delivered and nobody has to clear a state nothing can clear.
  - Retained evidence moved from `errorMessage` to `result`, the field the board reads and shows.
  
  ## Why the tools are three
  
  The test applied to every merge and split in this release was not symmetry but: *when the model judges wrong, is the mistake cheap, and is it reversible in both directions?* `agent delegate` created a direct task implicitly, so a model could not afterwards tell which mode it was in and a wrong choice was invisible. Every change above either removes a choice or makes the outcome observable.
  
  ## Not in this release
  
  Workspace durability, Agent Memory and the child environment policy shipped earlier in the series and are described in their own changesets. The Computer Lease's sandbox profiles, budget and depth guards, task handoff transfer, and a durable Agent Inbox are deliberately absent: they are independent of the split and remain open.

### Patch Changes

- 97e9add: Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
- e86a44f: Classify automatically generated direct-input records as execution history. Keep failures and results readable without treating them as actionable task reminders or autonomous claim candidates. Explicit tasks retain their dependency and recovery checks.
  
  Restore earlier generated UUID work records as execution history when no explicit record classification exists. This read-side classification preserves status, evidence, and recovery holds. It does not mark failed attempts completed or alter user files directly.
- e86a44f: Collapse the task list row to its task count by default, like every other Tasks row. Expanding the row wraps the complete stored task titles to the terminal width, so no title end is unreachable. Descriptions stay separate, and existing task data and tool results are preserved.
- e86a44f: Use one `tasks` transcript label for the four tools and settlement status messages. Display actions and readable statuses without changing tool names or structured data. Name expanded fields with `Description:` and `Verify:`, then show dependencies. Keep dependency previews in collapsed rows and bounded summaries in expanded status messages. Full continuation instructions stay in model context.
  
  Return each unchanged task snapshot for continuation only once. Report waiting without another model request when no task progress occurs. Ignore timestamp-only writes when checking progress. Keep the three-continuation allowance for changed task state and preserve explicit recovery and authorization checks.
  
  Keep a clean idle agent closure in the console mailbox when it owes no result or unread input and releases no unfinished work. Preserve stopped-state evidence without an unexpected-stop notification or another leader turn. Continue to report crashes, signals, unconfirmed input, unresolved results, unread current-incarnation mail, and interrupted work. Inspect unread mail without consuming it or changing delivery records. Treat malformed or incomplete unread records as unresolved input.
- 1c81c7a: Name the task operation in the create_task routing hint while preserving the multi-step, multi-file, and multi-turn triggers.
- e86a44f: Fix defects exposed by task test auditing.
  
  - Preserve complete UTF-8 prefixes when clipping context. A split leading byte previously produced a replacement character and exceeded the byte limit.
  - Keep clipping output within budgets smaller than the truncation notice. The structured `clipped` flag reports truncation when the notice cannot fit.
  - Declare `invalidated` in the tool output schema. Reopen results previously carried this field without declaring it.
  - Name unfinished prerequisite ids when refusing to start a dependent task.
  
  Strengthen tests so setup must establish the state being checked. Validate actual structured outputs across all four tools, restore tasks through the shipping session handler, and reject identity fields against otherwise valid parameter objects.
  
  Use isolated agent directories and remove inherited holder bindings from test subprocesses. Mutation probes run in temporary source copies, not in the working directory.
- e86a44f: Report claimable work from one definition. The `list_tasks` filter and the reminder before settlement now read the task store's own `claimableTasks` predicate instead of keeping their own copies. A restored pending task that still names a departed holder is claimable, and the reminder used to omit it from the work it offered while `take_task` accepted it.
  
  Name the restored-record classification as `resolveRecordKind` beside the persisted-file version, and repair the persistence row of the README module table.
- 135dd1e: Collapse every tool result and status row by default and retain full details through native expansion.
  Correct current blocker reads, recovery evidence retention, outstanding work updates, and retained-text budget checks.
  Reject malformed task storage and preserve accepted edits when completion input is refused.
  Require deliberate recovery before successful blocked delivery.
  Prevent Agent Teams from announcing task outcomes after refused store transitions.
- e86a44f: Return no result on a settlement that cannot continue in a session with no UI. The waiting and paused notices are transcript rows, so a headless `pi --print` run that ended with unfinished work printed nothing. A continuation result keeps its status message in every mode, because the model reads it on the next request.
  
  Apply the completion holder check only while a task is in progress. A pending task is unheld, whatever a restore kept in `claimedBy`, so a restored pending task that names a departed holder completes through the fallback path instead of a refusal naming a holder who is gone. A task nobody ever took is still refused when the checks are on.
  
  Clear `completionVerdict` and `completionGate` when an attempt fails. A failed attempt answered no gate, so a reader never sees an earlier attempt's verdict on a task whose current attempt failed.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [a3ee3e3]
- Updated dependencies [2bba220]
- Updated dependencies [a0923d8]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [2116b41]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0
