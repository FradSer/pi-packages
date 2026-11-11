# @fradser/pi-goal

## 0.2.0

### Minor Changes

- 654cbe3: Store goal state under Pi's own agent directory instead of the working tree: `~/.pi/agent/goals/<project key>/<id>/record.json`, where the project key is a readable Memory-style name for that project plus a short digest of its canonical path, so two lookalike paths never share one directory. Starting a goal no longer creates a `.pi/goals` tree in the repository, and a project's settings override moves next to that project's goals; an override an earlier version left in `<project>/.pi/goals/settings.json` is still read. A goal stored by an earlier version inside a project is still read, locked and written where it lives, because moving it would leave two processes locking different directories for one goal. The placement refusal for projects inside Pi's own directories is gone with the project-relative layout it protected.
  
  Completion and clear write the terminal `complete` status and keep the record instead of deleting it, so what was asked for and how it ended stay readable under the agent directory and no claims directory is left behind in a project. No archive is created. A finished record is terminal: a late charge from the run that was in flight, a completion check that returns after another session completed the goal, a second session's pause or stop, and every other stale-snapshot write are all refused rather than moving it out of `complete`.
  
  While an older installed version is still in use it cannot see a goal stored under the agent directory, and it still deletes the record it completes or clears, so the record-keeping guarantee covers this version's own writes.
- 654cbe3: A goal no longer has a budget, and no way to get one. The concept is deleted rather than repositioned:
  `GoalRecord` has no `tokenBudget`, `budgetReached`, `remainingBudget` and the cap-stop helpers are
  gone, nothing in the runtime stops, refuses a resume, refuses a revision or narrows the tool surface
  because a number got large, the run-start prompt no longer prints a token limit or a remaining budget,
  and the `/goal budget` verb added in this cycle is removed again before release. Usage is still
  recorded and reported — main-model and completion-check tokens are attributed to the goal, including a
  cancelled or superseded check for the same open goal — but usage is a report, not a gate.
  
  A goal is bounded by its work. Automatic continuation still stops after three consecutive runs that
  change nothing observable (unseen successful `edit` or `write` counts as progress; reading, searching,
  fetching, commands and delegated child work explore), and `maxAutonomousRuns` remains the only
  optional ceiling, unset by default. A record an earlier version wrote is tolerated rather than
  migrated: a `budget_limited` status reads as `paused`, its `tokenBudget` field is dropped by
  normalization, and the goal resumes and completes normally, so a goal that an old cap had stopped is
  no longer stuck. `create_goal` exposes no budget parameter, so a model cannot reintroduce a limit
  nobody asked for.
- e9039a3: A goal now has one requirement text: its objective. The verification contract is deleted rather than
  repositioned, because two requirement texts meant the completion check judged one of them and the
  model could read the other. `GoalRecord` has no `verificationContract`, `create_goal` and
  `update_goal` expose no `verification_contract` parameter, `get_goal`/`/goal` and the `[goal] started` body print the objective alone, the run-start policy block
  carries no second block, and the completion check receives the complete objective with the recorded
  observations and nothing else. Both Goal tools refuse any parameter they do not declare, so a stale
  schema from an older session is refused as an unapplied update instead of having the removed field
  silently dropped from the revision it sent. A revision still moves the objective and the start of the evidence
  window together, so observations collected under the old requirement stay inadmissible.
  
  A record an earlier version wrote is tolerated rather than migrated: normalization drops its
  `verificationContract` field and keeps the objective unchanged, so a goal stored under the old shape
  reads, revises and completes as any other. `/goal <request>` now asks the model to preserve the
  existing requirements inside the objective instead of naming a separate completion condition.
- 9a5a257: Add thread-scoped durable goals with one `/goal` command.
  
  Set an objective with `/goal <text>`. View the current
  goal with `/goal`, and manage it with pause, resume, and clear arguments.
  Keep the passive pi-kit status row below the editor, flush-left, with whole-minute time.
  
  Collect bounded runtime verification observations separately from executor claims.
  Keep the completion checker tool-less. Keep a completed goal's terminal record
  without writing an archive. Preserve thread ownership and reject stale continuation or completion results.
  
  Stop after three valid explicit final refusals, with the unmet requirement and recovery advice.
  Stop empty continuation after three runs without completed work. Pending monitor acknowledgements
  are not completed verification. Preserve actual monitor terminal outcomes and attributed review results.
  
  Include offline native CLI and TUI E2E checks for completion, refusal, empty-loop bounds,
  activation, pause/resume/clear, state display, and bounded process cleanup.
  
  Keep `research_goal` blocking. It mounts no widget above the editor, reads `[goal] Researching...`
  while the child works, and renders the child's latest activity on its own row beneath it through
  markdown. The result row reads `Research ready` with no character count.
  
  Read the below-editor status row as `<verb> · <elapsed>`, for example `Pursuing goal · 12m`
  or `Goal paused · 12m`, with no `[goal]` tag in any state. Every verb already names the
  goal, so the tag would repeat it on every line below the editor. The transcript rows
  keep the tag.
  
  Accept `update_goal`'s `completion_summary` without a length cap. The completion check
  reads a bounded prefix and states the truncation, while the goal record keeps the full claim.
  
  Accept an objective without a length cap too, in the tool schema and in record normalization,
  so a long objective is neither rejected nor quietly shortened. The injected note and the
  completion check each read a bounded prefix and state the truncation.
  
  Use the session's model for the completion check and for research when no goal model is
  configured, instead of leaving the child to pick up the persisted CLI default. Read global
  defaults from `~/.pi/agent/goal.json`; a project `.pi/goals/settings.json` overrides it.
- 2bba220: Simplify Goals to create/get/update with explicit completion checking, full wrapped TUI text, and truthful continuation status. Remove research_goal, next_action, separate ledger history, automatic refusal pauses and archive writes. Preserve existing historical files and lifetime usage, and account cancelled checks and authorized revisions across lifecycle boundaries.

### Patch Changes

- 97e9add: Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
- ceb8e23: Keep `/goal <request>` objectives concise and outcome-focused. Preserve relevant explicit requirements without expanding background into speculative scope.
- 366d812: Remove dead code and comments that describe retired behaviour: the duplicate goal reader, the legacy `readPrompt` name, the fabricated `activePath` write, the unread `currentTurnSeq` and `focusedId` accessors, and three verdict fields that are never set or read. De-export helpers with no external reader; they stay in the module. Correct the comments that still described an append-only ledger, a prose file as the objective, and a refusal count.
  
  Add tests for the delivery-failure stop and for the timer delivery route. Replace the stale `goal_native_supersede.py`, which failed while asserting removed archive, ledger and research behaviour, with `goal_native_revision.py`: it drives a real Pi TUI, and asserts that one `/goal <request>` revises the open goal in place, keeps the earlier requirement inside the objective, pursues again, and writes no archive.
  
  Every harness that records observations now verifies each scenario it observed against every `features/*.feature` file: the scenario must exist in some file, with the same predicates in the same order, and a recording harness that wrote nothing fails. A recorded scenario can no longer drift, and a recording harness cannot lose its contract entry, without failing the suite; clause-only scenarios stay outside that check.
- 4d20b94: Automatic continuation now bounds itself by whether a run added anything, instead of by whether it
  changed the workspace. The two stops that punished real work are gone, replaced by one rule:
  
  - A settled run no longer ends the goal for lacking a tool receipt. A continuation run that reports
    where it got to, and a provider that returns an empty completion, used to stop the goal with
    `No effective work was recorded. Use /goal resume to continue.` in the very turn that explained the
    work — which for a long-running goal (large accumulated context) is a common shape, not a rare one.
  - The window no longer counts only an unseen successful `edit` or `write`. It counted a run that ran
    the whole gate suite and read its output as "nothing observable", so three verification runs in a row
    stopped a goal that was working; the window is now filled by runs that produced **nothing new**, and
    reset by a receipt this session had not already produced, whatever the tool.
  
  The message follows the rule: `3 consecutive runs produced nothing new. Use /goal resume to continue.`
  A failed or interrupted run is still the only immediate stop, so a provider outage cannot become a retry
  storm. Repeated receipts, an answer with no tool call, and a run that produced nothing at all are what
  fill the window, so a stagnant loop still stops by itself. Goal introspection (`create_goal`, `get_goal`,
  `update_goal`, `monitor_stop`) and a monitor that has not reached a terminal status are not work, and a
  requirement revision no longer clears the receipt memory (re-wording the objective must not reset the
  loop's only bound). `GoalScheduler.settled` takes `(goal, settings, successful, didWork)`,
  `GoalCore.performedWork` is again the one progress fact, and `GoalCore.changedWork`/`runChangedState`
  are deleted with the tool allowlist they read. `NO_CHANGE_RUN_LIMIT` is renamed
  `NO_NEW_WORK_RUN_LIMIT`, and the run-start policy block now tells the model the rule the runtime
  actually uses. A user's own turn is still always new work, so a `/goal <text>` request keeps the full
  window for the work that follows. `maxAutonomousRuns` remains the only optional ceiling; raising it is
  now the way to bound a goal that keeps doing new things.
- a3ee3e3: An automatic continuation no longer starts from an empty custom message.
  
  The 2026-11-04 `jev-duplex-analysis-and-data` archive records a durable goal
  created mid-session whose next three checkpoint runs each produced an empty
  assistant message, ending in `3 consecutive runs produced nothing new. Use /goal
  resume to continue.` The checkpoint body was empty and the run's assembled
  system prompt predated the goal's creation, so the model received neither the
  objective nor the work policy for those runs.
  
  `checkpointBody` now renders the cached policy, the escaped untrusted objective
  block, the live no-new-work streak and the in-flight-work note, and both
  continuation paths (the idle timer and the settlement boundary) deliver that
  body with the checkpoint. The checkpoint stays hidden from the transcript;
  claim, dispatch, acceptance and the three-run limit are unchanged. `settings()`
  falls back to the core's project root when no run context is bound yet, so a
  timer delivery needs no non-null assertion.
  
  Two Given/When/Then regressions pin the delivered and boundary-started body, the
  live streak and hidden display, and the escaping of a hostile objective; the
  feature contract was regenerated from observed assertions. Goal pytest, both
  typechecks, pack, all five native Pi CLI/PTY probes, the isolated Docker
  acceptance (Pi 1.4.0, 33 pytest cases and the full probe set) and the workspace
  quality gate pass. An independent read-only review found no new blocking defect.
  The first Docker attempt failed on a network-interrupted bun download and the
  retry succeeded; no real-model or archived-session replay was run.
- 42db715: Fix completion checks failing with `Model "…" not found` when the session model comes from a provider an extension registers, such as magpie.
  
  The check runs in a fresh child with `-ne`, so extension-registered providers and virtual routers do not exist there. Naming one made Pi exit before the check could start, and every completion request then paused the goal instead of being judged. Those models are now skipped: the configured or session model is used when the child can resolve it, otherwise the child receives no model and Pi selects one from its own catalog.
- a3ee3e3: A stalled Goal no longer stops making progress, and a transient interruption no
  longer cuts a working run short at an arbitrary point.
  
  Three defects produced the reported "three chances" behaviour:
  
  - Pi skips `agent_before_settle` on an aborted run, so the scheduler stayed
    `inRun`, leaked the previous run's `userRun` credit, and never re-armed. The
    runtime now closes the run at `agent_settled` (which Pi fires in a `finally`
    for every run, with an `aborted` flag) and drops that credit. An explicit abort
    keeps the goal open without silently starting another model turn; a host
    anomaly that skips the boundary without an abort re-arms through the ordinary
    store write. Only a real failed run stops at once. Restore and shutdown now
    reset the armed decision, denial, window streak, wait and pending timer, and a
    stale timer can no longer dedupe out a later delivery.
  - A quiet turn honestly waiting on an in-flight bounded child, steer or monitor
    had no tool receipt, so it spent one of the three no-new-work chances. The
    goal then stopped at `Goal waiting` exactly when the result was about to arrive.
    A living child of this project (checked by live pid and matching cwd) now
    holds the window for a bounded wait — a stale, foreign or hung child cannot
    spin the loop forever. Only a result whose wait this thread actually observed
    counts as new work, so another session's child cannot revive this Goal.
    A completed result re-arms only a stop the runtime itself wrote. A user's own
    turn with new work does the same. Neither lifts a user pause, a blocker, a
    provider-failure stop, a spent allowance or a finished goal.
  - A queued message made `boundaryContinuation()` discard the armed decision via
    `takeover()` with no re-arm. The armed decision now survives for the idle timer
    to deliver after the message settles. A refused checkpoint's `denied` flag no
    longer poisons the next run.
  
  The model-facing policy now says to finish the started work unit before ending a
  turn, to treat waiting on a bounded child as a legitimate turn, and to call the
  completion check in the run where the objective's conditions were verified. The
  run-start counters show the live no-new-work streak (`2/3`) instead of only the
  constant limit, so the last chance is no longer a surprise.
  
  Eighteen BDD regressions cover the aborted run, the leaked user credit, report-only
  turns waiting on delegated work, a queued steer preserving its decision, a
  refused checkpoint not poisoning the next run, a stalled goal resuming on the
  user's new work, and the safety boundaries: stale/foreign/hung children cannot
  hold the window (with the idle timer actually delivering), an unobserved foreign
  result cannot count as this Goal's work, restore starts a fresh window, a stale
  timer cannot dedupe out a fresh delivery, a user pause and a provider-failure
  stop cannot be lifted by new work, and `maxAutonomousRuns=0` cannot be re-armed.
  The dormant
  `goal_completion.mts` subagent scenario had pinned the stall as correct; its
  expected result is updated to the new requirement. `test_goal_hygiene.py` now
  runs `bun x tsc`, matching the workspace's package manager.
  
  Verification: 33 pytest tests (66 simplified + 36 scheduling harness scenarios),
  `bun x tsc --noEmit -p tsconfig.tests.json`, root `bun run typecheck`,
  `bun run pack:check` (21 manifests), `bun pm pack` (including the new
  `src/inflight.ts`), and all five native Pi CLI/PTY probes pass.
- a3ee3e3: Use TypeBox directly for Goal tool schemas and declare the TypeBox peer in Goal
  and pi-kit. Pi 1.5.0 removed the `Type` re-export from `@earendil-works/pi-ai`;
  the isolated Docker acceptance now loads the packed Goal package on Pi 1.5.0.
  Add an explicit opt-in Docker E2E for `hunyuan-eval/hy4-dev` that keeps the real
  Magpie credential on the host and records one native Goal lifecycle.
  
  Independent review fixes bound delegated-result waits to their Goal, recognize
  terminal monitor/subagent reports, stop provider errors that skip the settle
  boundary, and stop a hung child after three quiet turns.
- 366d812: Show one `[goal] requesting` row for `/goal <request>`. The row carries the typed words under it, and the complete request body stays out of the terminal transcript. The request no longer leaves the transcript silent until the model creates or revises the goal. The label stays distinct from the `[goal] started` row that reports the created goal.
  
  The below-editor row for a running check is one neutral activity line. It no longer carries a redundant `[goal] checking...` heading above that line, because the position already belongs to the running goal.
- 4a80dc3: A `/goal <text>` request now counts as the user's own turn. The command delivers the request as a
  custom message, so the run it starts was never marked user-initiated: a model that only recorded the
  objective in that run produced no tool receipt, and the goal paused itself with `No effective work was
  recorded. Use /goal resume to continue.` before any work happened. The runtime now recognises the
  `goal-procedure` message as that user turn, and settlement lets a user-initiated run pass the
  no-effective-work stop, so the request earns exactly one real run. The run after it is judged
  normally, so one unproductive turn cannot hold the loop open, and three runs that change nothing
  still stop it.
  
  Goal transcript rows also stop repeating `Tokens used: <n>`. Usage stays recorded on the goal and
  reported in the run-start counters; the `[goal] started`, `[goal] updated` and `/goal` status rows
  carry the objective and any stop reason alone.
- b3daa7f: `goal_resumed` records which actor lifted the pause.
  
  `scheduler.resume` hard-coded `reason: "user"` on every resume, while `goal_paused` had carried an actor since the beginning. A resume activated by a revision under an accepted `/goal <text>` request therefore reported that the user typed `/goal resume`, which nobody did. Two facts were written as one, so a durable history could not tell a user action from a runtime one.
  
  **What changed**
  
  - `resume(goal, settings, reason)` takes the actor. The `/goal resume` command in `commands.ts` passes `user`; `activateRequestedRevision` passes `revision`.
  - The parameter is required rather than defaulted, so a future caller has to name the actor instead of inheriting the wrong one.
  - The new `ResumeReason` type in `record.ts` is the closed set. The ledger event field stays a `string`, because an older line, or a hand-written one, carries whatever text it carried and the reader must keep ignoring it. `goal_store.mts` proves that tolerance with values this runtime never writes.
  - `tests/goal_thread.mts` pins both actors: the accepted-request revision records `revision`, the management verb records `user`.
- b3daa7f: `/goal <text>` now asks the model to revise the focused goal instead of superseding it.
  
  `goalRequest` told the model: form a NEW goal that carries the earlier objective forward, create it with `supersedes: true`, and do not revise the existing goal in place. That contradicted four other sources and disabled the path the command builds for itself.
  
  **Why it mattered**
  
  The command keys one activation token to the focused goal id, and only `update_goal` consumes it. When the delivered body forbade an in-place revision, a paused goal could not be revived through `/goal <text>`: the model superseded instead, the paused record was archived with `goal_cleared` / `superseded`, and the ledger never recorded the `goal_resumed` it owed. The busy path was worse, because the command had already revised in place and then told the model to replace the goal it had just revised. A live model had to disobey the instruction to reach the documented behaviour; the seeded unit tests never noticed, because they script the model's tool call rather than obeying the body.
  
  **What changed**
  
  - The seeded request keeps the existing objective, adds the new request to it, and revises that goal in place with `update_goal`. It names why: a revision is the only path the command can activate.
  - `/goal <text>` never asks the model to supersede: the seeded body revises the focused goal in place, and new work after a finished goal follows an explicit clear.
  - The research step still runs first when repository facts are missing; the final paragraph now says to record the objective with `update_goal` or `create_goal` rather than naming creation alone.
  - `tests/goal_session.mts` pins the invariants: the body asks for `update_goal`, it does not forbid an in-place revision, and it never names `supersedes`.
- 2bba220: Preserve multiline goal results, preserve Markdown blank lines, and omit the redundant Goal prefix consistently in error rows. Token-capped goals now recommend clearing and starting a new goal rather than an unusable resume. Repair native terminal acceptance to decode complete repaint frames with a finite scripted provider, and document every TUI trigger.
  
  Treat explicitly provided revision fields as decisions even when empty: an empty objective is rejected, and an empty revision still obeys decision exclusivity. Clarify that reason and completion_summary alone do not record an update.
  
  Show settled Goal subjects and bodies in full with width-aware wrapping, preserve complete requirements in TUI while paging long model reads with content-bound cursors, unify summary and objective reads, constrain updates to mutually exclusive operations, and distinguish rejected updates from goal failure. Keep legacy blocked calls compatible, simplify final-refusal headlines, and reuse passive status widgets for repaint. Add opt-in fullSummary to pi-kit without changing existing consumers.
- e86a44f: Keep monitor deadlines responsive by evaluating JavaScript result contracts in
  interruptible workers with bounded queues. Match unterminated tails independently
  for stdout and stderr, preserve diagnostics on timeout and stop, and await process
  group escalation and worker termination even after a monitor leaves the active list.
  Natural shell completion also reclaims remaining descendants in its process group.
  
  Return terminal results directly for mixed and nested Pi v1 tool batches; retain
  one asynchronous terminal notification per monitor-only UI call. Correlate direct
  and custom results with cross-instance unique monitor IDs, render synchronous
  outcomes truthfully, and validate development against Pi v1.0 with its Node baseline.
  
  Bound the monitor console by terminal dimensions, preserve selection, hide logs
  until requested, and route paging keys through Pi's focused overlay API.
  Goal completion evidence uses structured monitor status, ignores pending starts,
  and correlates modern IDs while preserving historical counter-based records and
  the chronological position of updated outcomes.
  
  Honor append-only context edits when collecting goal evidence: omitted receipts
  and assistant calls contribute no observations, replacements change only content,
  and original role and terminal metadata remain authoritative. Retain raw receipt
  coverage across compaction and preserve last-edit semantics.
- 0010f51: Move the development Pi core cohort to 1.2.0 and stay type-correct on it. `before_agent_start` handlers in the goal runtime, Agent Teams and utils now test for the prompt instead of reading it directly, so they compile against both the older event shape and the current union Pi discriminates by run kind.
- 8662e95: Contribute Goal context once per run through Pi 1.2 before_agent_start prompt sections. Remove runtime-message replay. Deliver Memory discovery at run start only; context filtering no longer inserts missing references.
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
