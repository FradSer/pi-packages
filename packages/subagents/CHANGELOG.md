# @fradser/pi-subagents

## 0.2.0

### Minor Changes

- 53cb34f: Spawned Agents now have their own durable workspace and their own memory. Two of the three requirements behind the subagents / task / agent-teams split; the third, peer coordination, already existed.
  
  **Durable per-Agent workspaces**
  
  Isolation is now the default rather than opt-in. Each Agent gets a linked worktree at `~/.pi/agent/workspaces/<agent>/<project-slug>/`, reused across attempts instead of created per task and deleted on completion.
  
  This is not cosmetic. Pi stores sessions under the agent directory grouped by working directory, and `--continue` reopens the most recent session for the current working directory, so the working path *is* the memory key. The previous per-task worktree was removed on completion, which orphaned its session group every attempt — fragmentation that looks like amnesia and also accumulates storage without bound.
  
  - `worktree: false` in a definition opts out explicitly and shares the leader's tree. A definition that omits the field is now isolated, which is a behaviour change for existing definitions.
  - A working directory that is not a git repository, or a repository with no commit, falls back to the shared tree and records a `reason`. Nothing claims the child was isolated when it was not.
  - Completion calls `preserveAgentWorkspace`: it commits the attempt's output onto the Agent's durable branch and leaves the directory in place. Only an explicit `releaseAgentWorkspace` removes one, and the branch survives so preserved work stays retrievable.
  - A failed spawn removes a workspace only when that spawn created it and nothing ran in it. A reused workspace holds earlier attempts' work and session history and is never discarded.
  - The leader now receives a "Workspace preserved" report instead of a worktree diff. A durable branch accumulates across attempts, so a per-attempt diff against a base commit is no longer meaningful.
  
  `src/worktree.ts` is deleted. It implemented the disposable per-task model that `src/workspace.ts` replaces, no consumer imported it, and its three git-mechanics tests tested behaviour the product no longer has; `tests/test_agent_workspace.py` covers the durable model instead, including preserve-commits-and-keeps-directory, release-removes-only-on-explicit-request, and a-failed-spawn-never-removes-a-reused-workspace.
  
  **A blocker this surfaced, and its fix.** Pi's `defaultProjectTrust` setting is `"ask"`, and a freshly created directory is an untrusted project. A child started in a new workspace therefore blocked forever waiting for a trust decision that `--mode rpc` has no UI to make — the spawn succeeded, the process lived, and nothing was ever reported. `spawnResident` gained `approveProjectTrust`, which passes `-a`, and `agent-teams` sets it only when the workspace is one the harness created. Approving is correct there and only there: the workspace is a linked checkout of a repository the leader session already trusts. A child sharing the caller's directory inherits that directory's existing trust record and is deliberately not force-approved, which is also why the shared path never showed this bug.
  
  **Working memory is Pi's own session storage**
  
  No session scheme is implemented here, on purpose. `spawnResident` gained `session: "none" | "persist" | "resume"`:
  
  - `persist` for a newly created workspace, so Pi stores the session under that Agent's own working path.
  - `resume` (`--continue`) for a reused workspace, reopening the Agent's working memory.
  - `none` (`--no-session`) when the child shares the leader's tree, because persisting there would put the child's turns into the user's own session group.
  
  A supplied fork `context` still wins: `--session` cannot be combined with `--continue`, and a fork is a new session by definition. This reuses Pi's compaction, branching (`/tree`, `/fork`, `/clone`), `/resume` picker, and `/export` rather than rebuilding them, and no `--session-dir` is introduced to compete with Pi's storage.
  
  **Agent Memory**
  
  A persisted Agent can own a capability record at `~/.pi/agent/agents/<name>/`, user scope only. There is no per-project Agent Memory: a project-scoped capability folder cannot serve a cross-project Agent, and an existing project directive already requires local memory to live under `~/.pi/`.
  
  - Opt-in through `memory: true` in the definition. A session-scoped (Temporary) Agent resolves to `memory: false` whatever it asked for; Agent Promotion is what creates a folder, and that is a separate decision from approving any entry.
  - Content is capability, not project fact. Injection follows ADR-0003: a bounded index of filenames and one-line descriptions, never entry bodies, with the root declared once and all content marked as untrusted reference data. Descriptions are shortened with a visible marker before entries are dropped, and dropped entries are counted and reported rather than silently lost.
  - Writing is gated by the tool grant. A `bash` or `powershell` grant counts as write-capable because a shell can write; a read-only Agent is told to report the lesson in its result instead. Entry names cannot escape the memory root, an oversized body is refused rather than truncated, and an entry without a description is refused because the description is what the index carries.
  - `MEMORY.md` is derived from the folder on every write, so it cannot drift from what it describes.
  - A generalizing lesson is recorded as a **Memory Proposal** under `proposals/`, never merged directly. Review and merge stay with `pi-continual-learning`; absent that package proposals accumulate for human review, which is a safe degradation. A read-only Agent may still propose, because proposing is reporting.
  
  **Two worker extensions in one child**
  
  `agent-teams` now contributes `[SUBAGENT_WORKER_EXTENSION_PATH, WORKER_EXTENSION_PATH]` and the union of both capability sets. `--extension` is repeatable and `--no-extensions` still loads explicit paths, so neither package has to know about the other. This is the first real use of the contributed-extension seam, and it adds one tool, `agent_memory`, registered by `pi-subagents` and refused with a clear reason when the Agent has no memory folder or a read-only grant.
  
  The subagent extension reads `PI_SUBAGENT_ROLE`, `PI_SUBAGENT_TOOLS`, and `PI_SUBAGENT_MEMORY` — named for its own package rather than reusing `PI_TEAMMATE_*`, so the execution layer never has to learn the coordination package's vocabulary.
  
  **Not included**
  
  Kernel write confinement (Seatbelt/Landlock sandbox profiles), tool and usage budgets, the nesting depth guard, `Handoff` as an atomic transfer, and a durable `Agent Inbox`. A linked worktree separates the filesystem; it does not confine what a `bash` grant can touch, and no confinement is claimed.
  
  Contracts: `packages/subagents/features/agent-memory.feature`, `packages/subagents/features/agent-workspace.feature`.
- e86a44f: Agent startup is no longer bound to a Git worktree. An Agent starts in the leader's working directory unless its definition declares `worktree: true`.
  
  **@fradser/pi-subagents**
  
  `resolveIsolation` in `src/agents.ts` now resolves an absent `worktree` field to `shared` rather than `isolated`, and the two default sites follow it: `normalizeAgentInput` defaults a generated role to `worktree: false`, and `loadDir` reads `worktree: true` as the only opt-in instead of `worktree: false` as the only opt-out. `worktree: false` stays valid and means the same thing it always did.
  
  The default was the wrong way round. Most Agents only read, or edit files nobody else is working on, and a linked worktree bought them nothing but a full checkout of the repository — `~/.pi/agent/workspaces` had reached 1.0 GB, most of it under `*-review` and `*-reviewer` role names. It also cost correctness: a reused workspace is never synchronized with the leader's tree or HEAD. `ensureAgentWorkspace` returns a usable worktree as-is, the `agent/<name>` branch is cut once at first use, and nothing in either package fetches, merges, or resets it — so a role pointed at a workspace to read the current state read the state of its own first spawn. The leader's uncommitted changes were never in there at all.
  
  `worktree: true` keeps everything it had: a durable per-Agent workspace, `session: "persist"`/`"resume"`, `setTaskContext` recording the path, and completion committing onto the branch. Use it for a role whose output must not share files with the leader or with other Agents running at once. The one thing to know is that a reused workspace is still pinned to first-use HEAD, so point a role at a worktree for its own output, not for the leader's state.
  
  Write isolation remains unimplemented and unclaimed. A linked worktree separates the filesystem; a shared tree separates nothing at all.
  
  **@fradser/pi-agent-teams**
  
  `team-machine.ts` passes `agent.isolation` through unchanged, so the spawn path follows the role. The `liveWorkspaces` map, the `session` policy, `approveProjectTrust`, `setTaskContext`, and the completion-time `preserveAgentWorkspace` call were all already conditional on the worktree actually being provisioned, so a shared child inherits the leader's directory and its existing trust record instead of being force-approved for a directory this harness never created.
  
  A shared child runs with `--no-session`, because a child persisting into the leader's own session group would put its turns among the user's. That is the real cost of not giving it a directory of its own: a shared child is not resumable after a crash or a Pi restart. It is the pre-existing `worktree: false` behavior, unchanged.
  
  Contract: `packages/subagents/features/agent-workspace.feature`.
- e86a44f: Make disk agent.md the only durable identity declaration. Remove invocation
  persistence/Memory/worktree switches and automatic identity creation. Every child
  settles to IDLE and stays sendable until explicit stop or parent shutdown; temporary
  contexts remain memory-only. Fold private Memory, scratch workspace and per-project
  history into the Agent home, remove Git workspace/commit machinery, expose saved
  offline identities separately, and provide explicit non-destructive legacy migration.
  Provisioning and Memory updates share one locked atomic state mutation boundary
  that preserves creation time and existing metadata. Confirmed parent shutdown
  retires exact resident/host control closures without touching replacements or
  unconfirmed execution.
- e86a44f: Add five intent tools for child execution and exact-session controls.
  Separate saved identities from display labels.
  Queue bounded next input in FIFO order and retain input IDs in complete results.
  Preserve the legacy library API and restore its recorded tool selection.
  Check the original team policy before input reservation and dispatch.
- e86a44f: Retire the task board vocabulary and the `board.json` persistence fallback. Load and write only `tasks.json`. Remove the retired path and resolver exports. Preserve old files without automatic migration or deletion.
  
  Rename shared assignment kind `board` to `task`, use task-prefixed attempt ids, and rename worker binding to `PI_TEAMMATE_TASKS_FILE`. Use task names in coordination callbacks, notices, and console navigation. Update all contributing packages together and restart existing children before using the new bindings.
  
  This is a breaking library and worker-protocol change for these pre-1.0 packages. Task file format version 2, completion evidence, dependency rules, ownership, and recovery remain unchanged.
- e86a44f: Remove the `agent` tool, its six-action API, its selection branches and its
  uppercase receipt. The four intent tools `agent_start`, `agent_input`,
  `agent_stop` and `agent_list` are the only child tool surface: `agent_inspect` is
  retired with it, because a roster read plus the delivered Session Result already
  answers every question the per-child inspection existed for, and a tool the model
  can call repeatedly is a tool it will call repeatedly instead of waiting.
  A recorded branch whose selection named `agent` receives the intent family on its
  next session start. No user data moves, no migration runs on discovery or start,
  and no compatibility adapter remains.
  
  Rename the shared executor to `executeChildIntent` and name its operations after
  the intent operations. The published coordinator seam keeps its authority, so
  `@fradser/pi-agent-teams` behaviour is unchanged apart from calling the renamed
  executor.
  
  Every child result now paints one collapsed row. A single-child row reads
  `[tool] label · @name · status`, names the child once, and does not repeat a
  state word the label already carries. The authored prompt or steer headline stays
  on the row. A roster subject has no state, so `agent_list` reads
  `[agent] listed · @children · N of M`. Every other fact is expansion detail, and
  a moved line is dropped when the detail list already carries it.
  
  This is a breaking tool-surface change for recorded `agent` scripts in these
  pre-1.0 packages. Anything that parsed the legacy `AGENT ·`, `GRANT ·` or
  `RESULT ·` lines must read the structured `details` instead. Definitions,
  Memory, storage, result delivery and child lifetime are unchanged.
- 95b15ac: A standalone child returns its Session Result: its settled answer now reaches the main session.
  
  `@fradser/pi-subagents` is installable on its own, and with only that package loaded a child's work never came back. The answer existed in exactly one place — the spawner's progress stream, where an `agent_settled` event becomes a final frame — and the standalone spawn passed no `onUpdate`, so it was discarded at the moment it existed. The `agent` tool's description promised the opposite: "Results arrive automatically: continue your own work or end the turn rather than polling." The gap survived review because every configuration in daily use had `@fradser/pi-agent-teams` installed, and that package's published host owns the spawn and delivers reports itself.
  
  **What changed**
  
  - One **Session Result** per settled turn, delivered as a custom message with a `followUp` delivery and a triggered turn. The child's final text is the body, verbatim, behind an `<agent-result from=… session=… turn=…>` envelope; structured fields go in the message details.
  - The message renders as one pi-kit lifecycle row — `[agent] reported · @name` with the result's first line visible, the rest of the answer on expansion, and no session handle in the row. An ended Work Session paints on the error band: one visible line with an explicit `triggerTurn: false` and `deliverAs: "nextTurn"`, because recoverable execution is internal (ADR-0002) and a death is not a decision the Leader has to make. The explicit false matters — pi reads an *absent* `triggerTurn` as permission to steer the turn in flight.
  - A settled child is listed as `idle` with its answer as `liveText`, a shutdown the Leader requested produces no death notice, and a delivery that fails records itself on the roster instead of vanishing.
  - The spawner now reports a settle the moment it is parsed. It previously coalesced progress to one frame per stdout read, so a read carrying a settle *and* the next turn's start hid the settle completely — the exact failure this feature exists to remove.
  - The roster records the child's live text on every frame and projects it, so a delivered result stays readable and the delivery decision is auditable from the roster.
  - A published coordinator host suppresses execution-layer delivery, so installing both packages delivers each result once, exactly as today.
  - The contract lives behind the entry that holds the session API: a tool's execution context has no `sendMessage`, so the library takes an injected sender and stays TUI-free. A consumer embedding the library directly still spawns, records, and inspects — without delivery, as before.
  
  **Two defects a live session found, which no offline test could see**
  
  - A real child settles **empty** before it settles with its answer. The first version treated that empty settle as the turn's result, armed the dedupe, and suppressed every real result for the life of the Work Session. The dedupe is now armed by the turn, and a textless settle neither delivers nor arms it.
  - The standalone path handed the child its kickoff prompt **twice** — once as the spawn description, which the spawner writes to the control stream itself, and once through the resident-wake call. Every prompted start ran the same turn twice: twice the child's tokens, and twice the Leader's turns now that a settled turn is delivered. The prompt now travels once.
  
  The first version of this feature passed its entire offline suite and delivered nothing to a real session.
  
  **Vocabulary**
  
  `Session Result` joins `CONTEXT.md` as a term owned by this package: the settled output of one Work Session turn, distinct from a Submission (which needs a Task and an Assignment Attempt a standalone spawn has neither of), from a Message (the team runtime's), and from Agent Presence (state, not result). ADR-0007 records why the execution layer delivers at all.
  
  Contract: `features/session-result.feature`, ADR-0007, `docs/spec-standalone-session-result.md`.
  
  **Verification**
  
  - `tests/test_session_result.py` drives the real entry, the real tool, and the real delivery with only the child process mocked: a settle delivers verbatim with its provenance, an empty settle does not, an empty settle followed by the answer delivers exactly one result, every wake of a resident delivers, a hosted spawn delivers nothing, a child that dies produces one visible non-triggering line, a death that leaves a later turn unanswered is announced, a Leader-requested stop is not a death, a host with neither renderer nor session API still works, and the library barrel loads no pi-tui.
  - `tests/coalesced-settle-fixture.ts` drives the real parser with a settle and the next turn in one stdout read, because a hand-written frame list cannot catch the parser dropping an event.
  - Nine findings from an independent review of the first version are fixed: the ended notice steering an in-flight turn, two owners for a delivery failure, an unconsumed `sendMessage` promise, a roster frozen at `working`, a death that silenced a later turn, a Leader-requested stop painted as a death, a settle lost to read coalescing, notice text naming a call the tool refuses, and a README that contradicted the manifest.
  - A live RPC session with only this package installed: the leader delegates, the Session Result arrives as a custom message, it enters the model's context, the next turn reads it, and exactly one result is delivered.
- e86a44f: Make prompt delegation temporary by default, with explicitly persistent named
  roles, private resumable sessions and optional Memory; persistence never implies
  a background process or required worktree. Complete the standalone execution contract: preserve final UTF-8 output,
  confirm RPC startup and input, apply workspace and Memory configuration, narrow
  existing tool grants, and expose exact-session resident prompting. Add
  provider-compatible lazy tool activation and bundled responsibility/authority
  policies; preserve workspace data on failed or unconfirmed operations.
- e86a44f: Validate flat lifecycle inputs strictly at the native and library boundaries,
  preserve authored prompt bytes, and return declared structured output for agent,
  activation and Memory tools. Page and budget management readbacks without altering
  complete asynchronous final results. Caller cancellation releases waits while
  already dispatched exact controls keep their eventual acknowledgement/close
  authority. Clarify that activation is availability, Memory append creates or
  replaces a same-name entry, and read-only execution roles may write unaccepted
  proposal files under the existing narrow exception.
  
  Programmatic callers now receive structuredContent instead of receipt strings.
  Wrong types and action-inapplicable fields are refused; list accepts offset/limit
  and returns page continuation metadata. No new identity, storage migration,
  Memory-authority or child-lifetime policy is introduced.
- e86a44f: Add an explicitly granted child-only `agent_message` capability for bounded intermediate messages to the direct parent session. Preserve exact input attribution and existing grants, render these messages separately from final results, and keep queued inputs and settlement unchanged.
  
  Separate durable child history by the parent Pi session ID and project while sharing identity Memory and ordinary scratch. Reopening a parent restores only its own child history. Preserve existing project-only histories without importing, moving or deleting them; headless embeddings can supply a stable parentSessionId in runtime options.
  
  Require a prompt at the intent startup boundary, preserve final RPC records without a trailing newline, and keep successor turn counts independent during reentrant close callbacks. Reject malformed result metadata and out-of-range report timestamps without corrupting authored text or Unicode diagnostic previews.
  
  Give a new Pi process thirty seconds to load and confirm its initial prompt, idle readiness or fork setup. Keep running-resident input controls on their five-second acknowledgement deadline and preserve uncertainty on expiry without repeating input.
  
  Protect private Memory, definitions, and legacy migration sources against hard links. Publish private replacement files atomically, give same-title Memory proposals distinct names even when their timestamps match, and reject proposals over the complete serialized UTF-8 budget before writing files.
- e86a44f: Name the resident verbs apart, and let a working child be steered.
  `agent action=prompt` becomes `agent action=send`, and the new
  `agent action=interrupt` steers a turn already in flight — the one case `send`
  refuses — without opening a new turn or suppressing that turn's settled result.
  The schema stays one flat object: per-action requirements remain the handler's
  job, and the refusals that carry them name what is missing.
  
  A saved definition is the record of its own persistence: a start that omits
  `persistent` reuses that Agent's private session and Memory instead of silently
  running as a Temporary Agent, `persistent: false` is the explicit opt-out, and
  deriving persistence never writes a definition. The receipt names which of the two
  supplied it.
  
  The grantable built-in tool universe gained a drift check against Pi's own
  canonical set, and the `tools` parameter now advertises that universe where the
  model reads it.
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

- b3daa7f: State what a child can be given, in the contract a caller reads before spending a call.
  
  Three facts about starting a child lived only in the refusal of a real call.
  
  An optional `identity` carried `minLength: 1` and a name pattern from the shared string schema, so an empty value was rejected before the extension ran. The extension already read that value as absence: it trims the field and tests it for truth, so an empty identity never reached the identity-not-found path. A caller that took the temporary-role branch of the description was refused by a rule the code did not have. The field is now declared without either constraint, a blank value is normalized to absence, and the description says to omit the field for a temporary role.
  
  The `tools` description said the list was minimal and narrowed a saved grant, and never named a single id a child accepts. The grantable set is fixed — `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`, `powershell`, `agent_memory` — and a project-extension or MCP tool is not in it, because a child runs a bare pi process. Both facts are now in the description.
  
  An `agent_list` page with no entries reported the count and nothing else. A caller with no saved identity had to find the layout on disk, and the first path it reaches is the user scope under the agent home. The notice now names the project-local path, `.pi/agents/<name>/agent.md`, and states that a temporary role needs no file at all.
  
  Still missing, deliberately: an `agent_save` tool. Creating a saved identity in-session needs its own decisions about scope, naming, and overwrite, and inventing them here would pre-empt that design.
- 95b15ac: The `agent` tool paints a lifecycle row, and only a fixed Agent's spawn carries `agent_memory`.
  
  **The row**
  
  Starting a child printed its raw receipt into the transcript:
  
  ```
  AGENT · calc1 · started · session:calc1:00e8aac4-494c-4dec-af76-74385ab7f077
  WORKING · 回答:1+1 等于几?
  GRANT · agent_memory, message, task
  ```
  
  `registerAgentTool` already accepted a `renderResult` and the entry never supplied one, so every `agent` result fell through to Pi's default text rendering. `src/rows.ts` now binds the shared pi-kit band with real terminal geometry, and `src/extension.ts` passes it in, so a spawn reads like any other lifecycle event:
  
  ```
   [agent] started · @calc1 · ctrl+o to expand
   回答:1+1 等于几?只回复结果本身,不要额外说明。
  ```
  
  Expansion adds `role ·`, `model ·`, `tools ·`, the coordination-only warning, and the remaining prompt lines. A session handle never appears in a row; the model keeps the exact handle in the result text.
  
  The reason the entry could not do this earlier is worth recording, because the stated reason was wrong. Both `src/extension.ts` and the `@fradser/pi-tasks` entry claimed that importing pi-tui executes theme code that throws outside a rendered session. It does not: `truncateToWidth`, `visibleWidth`, and `wrapTextWithAnsi` are pure string functions. What throws is `keyHint()` before `initTheme()`, and `bindLifecycleRenderers` already resolves the expand hint through a guarded thunk. The entry is the right layer for the binding, so it now owns it, and the test loads the entry and renders before any theme exists to keep that property true.
  
  `src/agent-tool.ts` also drops a duplicated `publishRosterAsBoardStore()` call, and an idle resident's row now states it is waiting instead of filtering the receipt line that said so.
  
  **The grant**
  
  Every spawned child was granted `agent_memory`, and `@fradser/pi-subagents`' worker extension was loaded into every child, whatever the Agent's memory opt-in. The child registered nothing when memory was off, so the grant line promised a capability the child did not have: `agent_memory` in `--tools`, no such tool in the child.
  
  `spawnTeammate` now contributes the subagents capability set and its worker extension only when the resolved definition has Agent Memory, which `agents.ts` grants solely to a persisted definition with `memory: true`. A Temporary Agent is spawned as a bare `pi --no-extensions` process holding its own grant plus this package's `message` and `task`, and nothing else. A role naming `agent_memory` without the opt-in is refused by name instead of being silently dropped by the child's allowlist.
  
  ```
  memory: true      →  --extension <subagents worker>   --tools read, bash, agent_memory, message, task
  no memory field   →  --extension <teams worker>      --tools read, bash, message, task
  inline role       →  --extension <teams worker>      --tools read, message, task
  ```
  
  `references/agent-roles.md` documents `memory: true`, since that file is where a leader generating a role looks and the field was previously undiscoverable.
  
  Contract: `packages/subagents/features/agent-row-tui.feature`, and a new rule in `packages/subagents/features/agent-memory.feature`.
  
  **Verification**
  
  - `packages/subagents/tests/test_agent_row_tui.py` drives the real `executeAgentAction` and paints through the entry-registered renderer: the entry registers one, a render before `initTheme()` produces rows rather than throwing, the collapsed row is one band naming the child and its prompt, expansion carries the grant and the prompt tail, no handle leaks, and a clipped row advertises the configured expand key.
  - `test_agent_memory_reaches_only_a_fixed_agents_spawn` asserts the grants behaviourally, from the real spawn path with a mocked child: a fixed Agent, a persisted Agent without the opt-in, and a Temporary Agent each produce a recorded grant equal to the child's `--tools` argv, only the fixed one carries the memory extension, and the refused spawn starts no child at all.
  - Against the real `pi` binary: a bare child with `--tools read` reports `read`; the same child with the worker extension and `PI_SUBAGENT_MEMORY=enabled` executes `agent_memory`; with `PI_SUBAGENT_MEMORY=none` it does not. A fresh `pi --print` process loading the edited extension starts a temporary agent and reports `GRANT · coordination only`.
  - `packages/subagents` (64), `packages/agent-teams` (242), `packages/tasks`, and the root suites pass; `pnpm typecheck`, `pnpm pack:check`, and `pnpm check:install` are clean.
- e86a44f: Clarify asynchronous input receipts and exact session handles, distinguish malformed
  handles from missing children, and expose bounded output and diagnostics in roster
  readbacks. Drive standalone startup and streaming activity through pi-kit's passive
  above-editor widget, clean it up on settlement and shutdown, and avoid duplicate
  team rows. Render effective model configuration once in expanded startup details
  without duplicating the model-facing MODEL receipt. Cover the arithmetic delegation with isolated native Pi print/RPC and
  resizable TUI verification.
- 8662e95: Use additive run-start prompt contributions instead of complete prompt overrides. Do not use custom messages for context injection. Handle custom startup without a user prompt. Keep unrelated workflow records and authorization checkpoints.
- 97e9add: Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
- e86a44f: Bind hosted closure controls when the new exact incarnation is reserved, so a
  cancelled startup wait remains explicitly stoppable before acknowledgement. Refuse
  late confirmations that do not match the original reservation or conflict with a
  successor's control owner. Check existing ownership before eager binding or
  pinning, so synchronous reentrant starts cannot seize an already-owned successor,
  even under the same host object. Preserve returned late control failure diagnostics on
  only the originally pinned current incarnation after caller cancellation, without
  guessing idle, reviving processes or changing automatic final-result delivery.
- e86a44f: Classify a known premature provider stream closure for Pi's native retry policy.
  Use its configured retry budget, backoff and cancellation in the same child input sequence.
  Preserve partial output and original diagnostics. Disabled or exhausted retry still reports unanswered.
- e86a44f: Display each successful subagent answer once, without a repeated result/turn
  label or duplicated expanded body. Retain original message content and provenance
  metadata; use pi-kit width-aware summary expansion instead of a fixed preview cap.
- e86a44f: Render start/send/interrupt input from its complete bounded prompt so native
  expansion reveals long first-line tails and authored paragraphs exactly once.
  Send and interrupt expose exact session, observed state, pending intent and next
  actor only in expanded details; collapsed rows retain the shared compact preview
  and configured expansion hint. Original receipt data and process control behavior
  are unchanged.
- e86a44f: Retain native final-message stop reasons, errors and tool-call evidence, and
  report empty, failed, truncated or missing final answers as explicit unanswered
  follow-ups rather than blank success envelopes. Preserve original output, bound
  provider diagnostics, render an error-band row and expose the outcome in roster
  readbacks while leaving the resident IDLE for explicit subsequent input.
- e86a44f: Reset authoritative completion evidence on each new assistant message, including
  content-event fallback for transports without message_start, so an unfinished
  later message cannot inherit a previous successful stop. Normalize stop reasons
  to bounded protocol tokens at parsing, result delivery and rendering boundaries.
- a0923d8: Unify Pi's hidden-thinking setting across above-editor agent activity rows. `pi-kit` now owns the label (`Thinking...`), the per-refresh `hideThinkingBlock` reader, the tool/reasoning/answer display policy, and an additive `activitySource` on worker progress snapshots. Subagents, agent-teams, context and plan-mode use that one contract, so a reader who hid thinking blocks sees Pi's label instead of streamed reasoning on every agent row; tool names and answers still take precedence, and visible thinking is unchanged.
- e86a44f: Preserve the first migration write/fsync failure when descriptor closure also
  fails. Report close uncertainty separately without retrying recycled descriptors,
  and retain/disclose exclusively created destinations whose inode could not be
  verified, while continuing rollback of known invocation-owned files.
- e86a44f: Continue copy-only migration rollback after missing paths, preserve replacement
  inodes, and retain original failures plus residual cleanup diagnostics. Preserve
  parser-supported whitespace tool grants and mixed newline/body bytes, while
  blocking duplicate, invalid-UTF-8 or semantically lossy legacy definitions.
- e86a44f: Align the split package development checks to the root Pi 1.0.0 cohort without
  changing published wildcard peers. Remove obsolete tool-activation metadata from
  legacy forked history using a structural check compatible with the current core,
  while preserving conversation content and parent state.
- e86a44f: Reject linked or non-regular JSONL session-history candidates before provisioning
  or spawning a resident. Both public standalone and hosted resume selection use
  the same validation, with a second check at the shared spawn boundary.
- e86a44f: Render reported agent answer bodies with native Markdown inside the shared lifecycle band.
  Preserve exact final text, width bounds, expansion hints, and plain summaries for other consumers.
- e86a44f: Acknowledge public resident steering through its correlated native RPC response
  without resetting the active answer or sequence. Verify queued/rejected, wrong
  command, process-close and timeout outcomes through the real control parser.
- e86a44f: Keep saved-definition persistence and Memory on the private standalone execution
  path when a coordinator is installed, rather than silently handing an omitted
  persistence flag to a host with no private-session contract.
- e86a44f: Allow read-only inspection of known stopped exact incarnations still retained on
  the roster, including their bounded output and errors, without reviving them or
  reporting a liveness failure. Unknown or replaced handles report no known session;
  process controls continue to require a living exact incarnation. Sanitize and
  bound error diagnostics on both inspection and listing without modifying the raw
  roster record, with an explicit marker when the preview is truncated.
- 6aff737: Show a running child above the editor when the extension was loaded into a session that never fired a session start.
  
  Both halves of the activity area were installed by `session_start`. An extension loaded or reloaded into a running session never sees one, so the roster observer was never armed and the live context was never adopted: a child could start, work and settle while the above-editor row never appeared, and its settlement never reached the participant registry. The observer is now armed once for the life of the runtime and re-armed idempotently by whatever session start does arrive, and the live context is adopted from `tool_call`, which the host fires before it executes the tool — so the context is in place before the child that call starts is registered.
  
  Reload Pi for this to take effect in a session that is already open.
- e86a44f: Preserve explicit partial and complete intent-only selections during native Pi startup.
  Allow their selected loader without requiring the excluded legacy tool.
  Verify configured package continuation, recovery, and pending-input cancellation through real Pi print and TUI.
- 257261e: A working child's status row follows Pi's `Hide thinking` setting instead of streaming reasoning the reader asked for.
  
  The above-editor activity row read `liveThinking` directly, so a reader who hid thinking blocks in the transcript still had the reasoning streamed at them in the status line. That is the same reader's surface and the same fact, so it now obeys the same setting: with thinking hidden, the row reads `Thinking...` in the muted activity color — Pi's own label for a hidden thinking block — and the reasoning text never reaches the area.
  
  The label describes thinking, so it yields to newer evidence. Tool activity and answer text take the row as soon as they exist, which is what keeps `Thinking...` from lingering while the child is writing its answer. With thinking visible nothing changes: reasoning still streams through the shared markdown activity.
  
  Read per refresh rather than cached at session start, because the setting is toggled mid-session and a cached copy would keep the old answer until the next session.
  
  Contract: `packages/subagents/features/agent-row-tui.feature`.
  
  **Verification**
  
  - `packages/subagents/tests/test_agent_activity_widget.py` drives the real extension entry with a mocked child: hidden thinking renders `quiet · Thinking...` through the muted color token and never the reasoning text, a tool replaces it, answer text replaces it, and switching the setting back restores the streamed reasoning. A host without `getSettings` keeps the visible behavior.
  - `packages/subagents` widget, row, roster, activation, and intent suites pass, and the extension project typechecks.
  - Not verified live: no PTY session with a real child was run; the row text and its color token are asserted through the native harness that loads the real entry.
- 71770f3: An Agent's display name is one identifier-shaped token, and a start reads as `@task-sql-work` rather than as the phrase a caller typed.
  
  **The rule**
  
  A caller writes free text into `agent_start`'s `label`, and every surface painted that text as the child's name:
  
  ```
   [agent] reported · @Task SQL measured optimization · ctrl+o to expand
  ```
  
  A row names a child; it does not quote a sentence. A person also copies that name out of a transcript, and a name with spaces and capitals is not one token to copy. `agentDisplayName` in `src/intent-tools.ts` projects the authored label once, at the `agent_start` boundary, so the roster entry, the receipt, the Session Result notice, the parent message, the result envelope, the activity area and the stop row all carry the same name:
  
  ```
   [agent] reported · @task-sql-measured-optimization · ctrl+o to expand
  ```
  
  The projection lowercases the label, replaces each run of other characters with one hyphen, trims the edge hyphens, and bounds the result. It is deliberately ASCII, because a letter outside ASCII renders as a word rather than a token. A label that holds no ASCII letter or digit therefore projects to nothing, and the child keeps its own name: an identity name, or `subagent-<8 hex>`. `Task  SQL  work` and `Fix OAuth 2.0!` read as `task-sql-work` and `fix-oauth-2-0`.
  
  The authored text is not discarded. A temporary child's role keeps it as its purpose, which is what a coordinator hands its teammates, so the receipt still reports `role · Fix OAuth 2.0!` beside `Label: fix-oauth-2-0`. The `label` parameter description, the README, `VISION.md` and `references/agent-roles.md` state the rule, and the Agent Teams leader guidance names it.
  
  Contract: the new rule `A label is one identifier-shaped display name` in `packages/subagents/features/intent-tools.feature`.
  
  **Verification**
  
  - `packages/subagents/tests/test_intent_tools.py` starts a child for each of three authored labels and asserts the receipt, the roster entry, the Session Result notice and the `<agent-result from=…>` envelope that real Pi delivered, plus the role line that keeps the authored text. A label holding no ASCII letter or digit keeps the child's own name.
  - `packages/subagents/tests/test_intent_tui.py` renders the real rows: input, stop and list subjects read `@friendly-reviewer`, `@original-reader` and `@storage-reviewer`, and the authored phrase never reaches a row. `test_agent_activity_widget.py` asserts the same for the working row above the editor.
  - `test_intent_host.py` keeps `definition.description == "friendly label"` and adds `receipt.label == "friendly-label"`, which records the split between the role's purpose and the display name.
  - Real `pi` against a loopback provider (`tests/test_live_intent.py`, cases `print-prose-label` and `tui-prose-label`) starts a child with the label `Task SQL measured optimization`. One real process reports `label=task-sql-measured-optimization` on the start receipt, on the stop receipt and on both result notices. The captured 70-column composer shows `[agent] started · @task-sql-measured-optimizat…`, `[agent] queued · …`, `[agent] stopped · @task-sql-measured-optimization` and `⠦ task-sql-measured-optimization · FIRST RESULT`, and never the authored phrase.
  - `packages/subagents` passes (584 tests), `packages/agent-teams` passes (302 tests), `tsc --noEmit -p tsconfig.extensions.json` and `node scripts/publish-release.mjs --check` are clean, and `tests/test_prompt_budget.py` still holds the Agent Teams prompt ceilings.
- a3ee3e3: Keep runtime bookkeeping out of expanded subagent control rows. An `agent_start`, `agent_input` or `agent_stop` row now expands to the authored input plus substantive outcome facts (model, tools, role description, evidence, preview, error); exact session/input handles, observed state, pending intent, queued count and next actor remain in the model-facing structured details instead of the transcript. `agent_list` keeps its expanded handles and live facts because looking up exact incarnations is that tool's purpose. Child-to-parent intermediate messages and cancelled-input notices likewise show their body/reason without session, input or sequence identifiers.
- e86a44f: Keep intent operation rows readable with consistent child display names and task
  previews, placing session/input identifiers in expanded details. Retain a static
  idle row for resident standalone children after settlement and preserve the display
  label in failure notices.
- 197b903: Name the roster in the `agent_list` row only when the page hides something.
  
  The collapsed row read `[agent] listed · @children · N of M`. `@` is the prefix of a real child's name, so the roster read as a child called "children" on a row where every other subject is one agent; and `4 of 4` answered a question the absence of a count already answers. The row now reads `[agent] listed`, and `[agent] listed · 3 of 9` only when the page omitted entries — the one fact a collapsed page cannot state any other way. Expansion still shows the remaining count and the next offset.
- e86a44f: Transfer temporary fork history as a versioned control-pipe payload into a
  child-only request-local context extension, retaining --no-session. Await a
  dedicated native setup acknowledgement before kickoff or idle readiness, and
  refuse malformed, repeated, late or over-limit setup without writing history.
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
