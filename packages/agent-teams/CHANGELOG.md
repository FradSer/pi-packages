# @fradser/pi-agent-teams

## 1.0.0

### Major Changes

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

### Minor Changes

- 53cb34f: A spawned Agent child no longer inherits the leader's complete environment.
  
  `spawnResident` used to launch the child with `{ ...process.env, ...options.env }`, so every Agent received every variable the developer had exported — provider keys, cloud credentials, personal encryption keys, registry auth tokens. One `env` call inside a child granted `bash` dumped all of them, and they propagated into every subprocess that child spawned and every crash report it produced.
  
  **What changed**
  
  - `src/child-env.ts` resolves the child environment from an explicit allowlist instead of the leader's whole environment: runtime and locale, editor/pager, Git and `SSH_AUTH_SOCK`, proxy and trust anchors, Node and language toolchain locations, and the Pi process markers and configuration variables. Names are matched exactly; the single admitted prefix is `LC_`.
  - `PI_CODING_AGENT_DIR` passes through, which is what lets the child resolve the same `auth.json` and `models.json` as the leader. Pi stores OAuth credentials in `auth.json` and reads a literal or `$NAME`-interpolated `apiKey` from `models.json`, so a child needs the config directory rather than the parent's credential set.
  - `PI_TEAMMATE_ENV_ALLOW` opts additional variables back in by exact name, comma-separated. Opting in a credential-shaped name works and is reported, so an operator's widening is visible rather than silent. A name the leader does not have is reported as missing instead of materialized as an empty placeholder.
  - Spawn overrides remain authoritative over both the allowlist and the leader environment, and an override with an `undefined` value removes the name instead of passing the literal string `"undefined"`.
  - The allowlist variable itself does not travel to the child, so a child that spawns in turn reaches its own strict default rather than inheriting a widening of its parent's.
  
  **Observability**
  
  The withheld count, the credential-shaped names, and the recovery instruction are recorded on the teammate and shown in the `/agent-teams` detail view. Per ADR-0002 this stays passive console telemetry and never wakes the leader. Names that embed a private URL — npm's `npm_config_//registry.example.com/:_authToken` shape — are redacted to a recognizable prefix, and no withheld value is ever rendered.
  
  **Scope of the guarantee**
  
  This is defense in depth against accidental leakage, not a containment boundary. A child granted `bash` can still read `~/.pi/agent/auth.json`, `~/.aws/credentials`, or a project `.env` directly from disk. Kernel write and read confinement is the sandbox-profile layer and is not part of this change.
  
  **Migration**
  
  A setup whose provider resolves credentials through environment interpolation now needs those exact names in `PI_TEAMMATE_ENV_ALLOW`. Nothing else changes: literal and OAuth configurations are unaffected because they resolve from the config directory.
  
  Contract: `features/spawn-env-policy.feature`.
  
  **Verification**
  
  - `tests/test_child_env.py` covers the policy directly (16 tests), and
    `test_spawned_child_environment_is_the_policy_output` proves the wiring by
    spawning a real child that dumps its own `process.env` to stderr. A resolved
    environment that is not the environment the child receives would prove
    nothing, so the assertion is made from inside the child. macOS blocks
    `ps eww` environment inspection (it returns the header only), which is why the
    probe reads from inside.
  - That integration test asserts the precise property, not a spot check: every
    name the child received must be allowlisted, supplied by that spawn, or
    declared runtime-injected; strictly fewer leader variables reach the child than
    the leader exports; and the reported `withheldCount` equals that difference
    exactly.
  - `tests/live-child-env.ts` is the opt-in counterpart (`LIVE_AGENT_WORK_MODEL`):
    one real resident, one real model turn, confirming the allowlist did not remove
    anything the provider needs. On the reference machine it withheld **115**
    leader variables, **45** of them credential-shaped, and the child still
    completed its turn.
  - `tests/test_teammate_package.py::test_resident_unterminated_output_is_terminated_without_partial_success`
    had to change. It configured its fake child through the leader's ambient
    `PI_LINE_LIMIT`, which the policy now withholds — a test that depended on the
    leak. It passes its knob through the spawn's own `overrides` instead, which is
    authoritative by design. The production allowlist was deliberately not widened
    to satisfy it.
  
  **Hardening applied after self-review**
  
  - `withheldSecretNames` is bounded to 16 **at the source** and
    `withheldSecretCount` carries the true total. It was previously unbounded in
    the persisted state, with the diagnostic and the console each applying their
    own cap — so a shell exporting many tokens could grow `envPolicy` on disk and
    the two surfaces could disagree.
  - `RUNTIME_INJECTED_ENV_NAMES` declares `__CF_USER_TEXT_ENCODING`. libuv adds it
    to every macOS child regardless of the supplied environment, so no allowlist
    can withhold it; its value is a UID-derived locale hint, not a credential.
    Declaring it lets the test assert against an explicit narrow set instead of
    excusing any unexpected name, so a genuine leak cannot hide behind "the runtime
    probably added it". A name can be withheld by the policy and still present in
    the child this way; the withheld count reflects the policy's decision and is
    not reduced by the runtime putting the name back.
  - `isAllowedEnvName` is exported for that subset assertion.
  - The static tripwire tightened from `"...process.env" not in spawner` to
    `"process.env" not in spawner`. The weaker spelling would have passed on
    `Object.assign({}, process.env)`. The spawner now never reads the ambient
    environment directly; `child-env.ts` is its only reader.
  - The `ALLOWED_EXACT` header now states that "non-secret" is not "inert":
    `NODE_OPTIONS`, `NODE_PATH`, `GIT_SSH_COMMAND`, `GIT_CONFIG_GLOBAL`, `EDITOR`,
    `VISUAL`, `PAGER`, `GIT_EDITOR`, `GIT_PAGER`, `SSL_CERT_FILE`, and
    `SSL_CERT_DIR` cause code execution or credential redirection in the child.
    They stay allowlisted because they originate in the developer's own shell and
    are not model-controllable, and because a child granted `bash` can already run
    arbitrary code. None carries a credential value, which is what this policy
    removes.
  - `writeRoster` was verified to project only seven fields, so `envPolicy` never
    reaches the worker-readable roster file. It is persisted only in the
    leader-owned forensics state file, as names and counts, never values.
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
- e86a44f: Return one refusal shape from every task-store operation. A refusal is now `{ refusal, detail?, reason }`: a machine code from one closed set for a caller to branch on, the task, holder, or prerequisite it is about, and the sentence a caller or a model reads.
  
  Before this change the store returned the same sentence under five different shapes: `error` from a creation, `reason` from an edit, a completion, a reopen, and a bind, `refusal` with a `detail` from a take, and `error` again from a marker path. Only a take could be branched on without reading prose. The success flag is unchanged: `ok` for a task write and `applied` for a claim marker.
  
  This is a breaking library change for these pre-1.0 packages. Read `result.reason` where a result used `result.error`, and read `result.refusal` to branch on why. Every refusal word in the sentences themselves is unchanged, no rule about what may be done changed, and the four model-facing tools still report the same text. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together.
- e86a44f: Make a recovery hold a first-class status, at the same level as in progress. `TASK_STATUSES` gains `recovery_hold`, and the `recoveryRequired` flag is gone from the record, from every projection, and from the model-facing text. `pending` now means never attempted, and only that.
  
  A task that fails, that has its premise withdrawn by a reopen, or that is restored mid-attempt now sits in `recovery_hold` instead of `pending` under a flag. Taking from `recovery_hold` still needs a stated reason, and the refusal still names the state. A task row reads `recovery hold` in the status slot where it used to read `pending · recovery hold`, so a held task is no longer displayed as work that was never started.
  
  `claimable` and `ready` answer from the status alone: a claimable task is `pending` with every dependency met, and a completable one is `in_progress` or `recovery_hold`. The paired flag checks those predicates used to carry are gone.
  
  A task file written before this change restores correctly. A record with `pending` and `recoveryRequired: true` restores as `recovery_hold`, a record still in progress restores as `recovery_hold`, and the flag is never written back. The file format version is unchanged, because the reader normalizes both spellings rather than migrating the file.
  
  This is a breaking library change for these pre-1.0 packages. Read `task.status === "recovery_hold"` where a record used `task.recoveryRequired`, and drop `recoveryRequired` from anything that stored it. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together. Task file format version 2, completion evidence, dependency rules, ownership, and recovery rules are unchanged.

### Patch Changes

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
- e86a44f: Classify a known premature provider stream closure for Pi's native retry policy.
  Use its configured retry budget, backoff and cancellation in the same child input sequence.
  Preserve partial output and original diagnostics. Disabled or exhausted retry still reports unanswered.
- a0923d8: Unify Pi's hidden-thinking setting across above-editor agent activity rows. `pi-kit` now owns the label (`Thinking...`), the per-refresh `hideThinkingBlock` reader, the tool/reasoning/answer display policy, and an additive `activitySource` on worker progress snapshots. Subagents, agent-teams, context and plan-mode use that one contract, so a reader who hid thinking blocks sees Pi's label instead of streamed reasoning on every agent row; tool names and answers still take precedence, and visible thinking is unchanged.
- e86a44f: Add five intent tools for child execution and exact-session controls.
  Separate saved identities from display labels.
  Queue bounded next input in FIFO order and retain input IDs in complete results.
  Preserve the legacy library API and restore its recorded tool selection.
  Check the original team policy before input reservation and dispatch.
- 6603d43: Pi-kit never pre-truncates the content it derives, and every remaining bound is now either the row's own width-aware `fit` or an explicit limit that announces itself.
  
  **pi-kit**
  
  - A worker's tool activity showed only 40 characters of the command plus a literal ` ...`, even on a wide terminal, while streamed text or thinking activity showed its whole line. Progress snapshots now carry the tool's complete flattened command or query and the live widget row fits it to the terminal.
  - `formatToolLifecycleDetails` dropped every detail line past the 50th with no marker, so an expanded row could hide evidence the user had just asked to read. Expanded bodies are complete by default.
  - `detailLimit` now takes a number only: `"all"` was the same complete readback as the new default, so it is removed rather than left as dead vocabulary. Callers that passed it drop the argument.
  - An explicit numeric `detailLimit` renders a `… N more detail lines` row instead of dropping lines silently, and `0` still suppresses the body instead of advertising an empty one.
  - `fieldBlock` no longer clips a value at 2000 characters: the whole value survives. A package with a real content budget (prompt injection, memory index) applies and announces it where it owns it.
  - `renderPiWidgetRow` and `renderPiPanel` passed an empty ellipsis to the injected `fit`, so a status or panel row clipped at the terminal width stopped mid-word with no sign that text was missing — the `reviewer · bash: …` line the transcript rows already marked was the one that did not. Both now keep the host's truncation marker, so every clipped pi-kit row ends with `...` again.
  - `formatToolLifecycleDetails` no longer accepts a `maxLines` fallback bound, which no caller used.
  
  **@fradser/pi-agent-teams**
  
  - Coordination titles clipped a Work subject or task preview at 90 characters with no way to read the rest, and expanded bodies clipped a kickoff prompt at 2000 characters. Titles now carry the whole value and the kit row truncates them at the terminal width while expansion reveals every line, so the removed caps leave no text unreachable.
- 0010f51: Move the development Pi core cohort to 1.2.0 and stay type-correct on it. `before_agent_start` handlers in the goal runtime, Agent Teams and utils now test for the prompt instead of reading it directly, so they compile against both the older event shape and the current union Pi discriminates by run kind.
- e86a44f: Reject linked or non-regular JSONL session-history candidates before provisioning
  or spawning a resident. Both public standalone and hosted resume selection use
  the same validation, with a second check at the shared spawn boundary.
- 842b92e: A tool call now names its pattern instead of the directory it searched.
  
  Pi's built-in `grep` and `find` take `{ pattern, path? }`, and every package that labeled a tool call from its arguments read `path` first, so a search that named a root rendered as that directory (`file: <directory>`, `grep: <directory>`, or `<tool> <directory>`) while a search without a root fell back to the bare tool name. The pattern is what the call is doing; the path is only where it looked.
  
  **@fradser/pi-kit**
  
  - `classifyToolActivity()` and `inlineToolActivity()` are new exports: one precedence rule — an explicit command, then a search's pattern, then a path, a query, a subject, and a delivery target — shared by every labeling call site instead of restated per package.
  - Live worker progress labeled a `grep` or `find` call `file: <directory>` whenever it carried a `path`, and fell back to the bare tool name otherwise. It now reports `search: <pattern>` and keeps `file: <name>` for genuine file reads.
  
  **@fradser/pi-agent-teams**
  
  - A teammate running `grep`/`find` with a `path` showed `file: <directory>` in its live activity row. It now renders `search: <pattern>`, and its labeler consumes the shared classifier rather than keeping its own copy of the ordering.
  
  **pi-open-deskos**
  
  - `summarizeToolCall` ignored `pattern` entirely, so a `grep` call read as `grep: <directory>`. It now renders `search: <pattern>` and still prefers an explicit command, then a path, for every other tool.
  
  **pi-continual-learning**
  
  - The dreaming widget showed a `grep`/`find` call as `<tool> <directory>`, because a consolidation worker holds `grep`, `find`, and `ls` alongside `read`. A search now names its pattern, and the label is the testable `dreamingToolActivity()` rather than inline argument parsing.
- e86a44f: Classify automatically generated direct-input records as execution history. Keep failures and results readable without treating them as actionable task reminders or autonomous claim candidates. Explicit tasks retain their dependency and recovery checks.
  
  Restore earlier generated UUID work records as execution history when no explicit record classification exists. This read-side classification preserves status, evidence, and recovery holds. It does not mark failed attempts completed or alter user files directly.
- 53cb34f: The subagent execution layer moved out to a new workspace package, `@fradser/pi-subagents`, which now owns the `agent` tool and the child roster outright.
  
  This step alone changed no behaviour. The tool surface changed later, in the same 1.0.0 release: see `three-package-split.md`. `/agent-teams` is unchanged.
  
  **What moved**
  
  `src/agents.ts`, `src/child-env.ts`, `src/leader-reports.ts`, `src/spawner.ts`, `src/work-context.ts`, and `src/worker-tools.ts` are now `@fradser/pi-subagents`, along with `WorkerUsage`. (`src/worktree.ts` moved here too and was later deleted, superseded by `src/workspace.ts`.) `src/types.ts` re-exports that type because `Teammate` references it.
  
  What stays here is the coordination core: `state.ts`, `statefile.ts`, `team-machine.ts`, `worker.ts`, `tools.ts`, `ui.ts`, `tool-copy.ts`, `tool-render.ts`, `agent-actions.ts`, `recipient.ts`, `guidance.ts`, and `activity.ts`.
  
  **Why the spawner had to change shape first**
  
  `spawnResident` hardcoded two things belonging to this package: a `WORKER_EXTENSION` constant pointing at its own `src/index.ts`, and `WORKER_CAPABILITY_TOOLS = ["agent_event", "work"]`. Moving the spawner without removing those would have made the execution layer load this package's worker entry and grant two tools it does not register — installing `@fradser/pi-subagents` alone would have advertised a coordination surface nothing implemented.
  
  Both are now contributed per spawn:
  
  - `extensions: [WORKER_EXTENSION_PATH]` — `--extension` is repeatable and `--no-extensions` still loads explicit paths, so several packages can each contribute a worker extension to one child.
  - `capabilityTools: WORKER_CAPABILITY_TOOLS` — `resolveWorkerTools`, `workerToolUniverse`, and `unknownWorkerTools` all take the contributed set.
  
  Declaring capability tools with no extension to register them is refused rather than silently granting ids the child's `--tools` filter would drop.
  
  The declaration lives in a new dependency-free `src/capability-tools.ts` because both the registration site (`worker.ts`) and the presentation site (`tool-copy.ts`) read it, and `worker.ts` imports `tool-copy.ts` — declaring it in `worker.ts` would close a cycle.
  
  **Publishing order**
  
  `@fradser/pi-subagents` must reach the registry before this package can publish, because the packed manifest now depends on it at an exact version (`0.1.0`, resolved from `workspace:*`). It is listed directly after `@fradser/pi-kit` in `scripts/publish-release.mjs` `PUBLISH_SCOPE`. Its first release needs the interactive bootstrap and npm trust setup, not a Changesets bump.
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
- e86a44f: Use one `tasks` transcript label for the four tools and settlement status messages. Display actions and readable statuses without changing tool names or structured data. Name expanded fields with `Description:` and `Verify:`, then show dependencies. Keep dependency previews in collapsed rows and bounded summaries in expanded status messages. Full continuation instructions stay in model context.
  
  Return each unchanged task snapshot for continuation only once. Report waiting without another model request when no task progress occurs. Ignore timestamp-only writes when checking progress. Keep the three-continuation allowance for changed task state and preserve explicit recovery and authorization checks.
  
  Keep a clean idle agent closure in the console mailbox when it owes no result or unread input and releases no unfinished work. Preserve stopped-state evidence without an unexpected-stop notification or another leader turn. Continue to report crashes, signals, unconfirmed input, unresolved results, unread current-incarnation mail, and interrupted work. Inspect unread mail without consuming it or changing delivery records. Treat malformed or incomplete unread records as unresolved input.
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
- 53cb34f: The task board domain moved out to a new workspace package, `@fradser/pi-tasks`, which now owns the `task` tool and the board container outright.
  
  This step alone changed no behaviour. The tool surface changed later, in the same 1.0.0 release: see `three-package-split.md`. `/agent-teams` is unchanged.
  
  **What moved**
  
  `@fradser/pi-tasks` now owns the data model (`BoardTask`, `TaskStatus`, `TaskIntent`, `WORK_RUNTIME_VERSION`), the pure graph and resource rules (`taskIdFromSubject`, `normalizeResources`, `canonicalDependency`, `canonicalDependencies`, `hasDependencyCycle`, `resourcesConflict`), and durable board persistence (`tasksRoot`, `boardDir`, `boardFilePath`, `claimsDir`, `submissionsDir`, `readBoardFile`, `writeBoardFile`, `createTaskIntent`, `takeTaskIntent`, `INTENT_PUBLISH_GRACE_MS`).
  
  What stays here is the stateful half: the in-memory board container and its transitions in `state.ts`, the roster, peer mail, the verification gate, and both `work` tool slices. Those need the `ChildHost` / `WorkStore` seam before they can move.
  
  **Two duplications removed**
  
  `worker.ts` carried its own private copy of `resourcesConflict` with a wider signature than the leader's. Both now call the one implementation in `@fradser/pi-tasks`, so a worker and the leader cannot disagree about whether two leases conflict.
  
  `sessionKey` moved to `@fradser/pi-kit`, because the board directory and the teammate runtime directory are scoped by the same key and two packages must agree on which session a directory belongs to.
  
  **Deliberate changes**
  
  - Operator-visible board errors now say `Work snapshot` instead of `Agent Teams Work snapshot`. `@fradser/pi-tasks` owns the file and may be installed without the team runtime, so naming Agent Teams would be wrong. `test_snapshot_version.py` was updated to the corrected wording; the version numbers and the refusal to treat an unreadable board as empty are unchanged.
  - `TaskStatus` became a plain TypeScript union. The previous TypeBox construction existed only to be converted straight back into a type with `Static<>`, and no tool parameter ever used the runtime value. This keeps `@fradser/pi-tasks` free of a typebox peer.
  - `WORK_RUNTIME_VERSION` keeps the value `2`, inherited from `TEAM_RUNTIME_VERSION`, so boards written before the extraction still load. `TEAM_RUNTIME_VERSION` remains for this package's own runtime snapshot; the two files now version independently, which is correct since their schemas are independent.
  - `canonicalDependencies` and `hasDependencyCycle` became public. They were private to `state.ts`; a board-only consumer of `@fradser/pi-tasks` needs the same cycle refusal the leader applies at creation.
  
  **Publishing order**
  
  `@fradser/pi-tasks` must reach the registry before this package can publish, because the packed manifest now depends on it at an exact version. It is listed after `@fradser/pi-subagents` and before `@fradser/pi-agent-teams` in `PUBLISH_SCOPE`, and `test_publish_allowlist_orders_split_layers_before_their_consumer` pins that ordering. Its first release needs the interactive bootstrap and npm trust setup, not a Changesets bump.
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
- 135dd1e: Collapse every tool result and status row by default and retain full details through native expansion.
  Correct current blocker reads, recovery evidence retention, outstanding work updates, and retained-text budget checks.
  Reject malformed task storage and preserve accepted edits when completion input is refused.
  Require deliberate recovery before successful blocked delivery.
  Prevent Agent Teams from announcing task outcomes after refused store transitions.
- e86a44f: Return no result on a settlement that cannot continue in a session with no UI. The waiting and paused notices are transcript rows, so a headless `pi --print` run that ended with unfinished work printed nothing. A continuation result keeps its status message in every mode, because the model reads it on the next request.
  
  Apply the completion holder check only while a task is in progress. A pending task is unheld, whatever a restore kept in `claimedBy`, so a restored pending task that names a departed holder completes through the fallback path instead of a refusal naming a holder who is gone. A task nobody ever took is still refused when the checks are on.
  
  Clear `completionVerdict` and `completionGate` when an attempt fails. A failed attempt answered no gate, so a reader never sees an earlier attempt's verdict on a task whose current attempt failed.
- 53cb34f: Stop `setActiveTools` toggle writes from deactivating tools the harness has not published yet.
  
  `setActiveTools` is an allowlist write: the caller passes the complete set the
  model may call, and anything absent is deactivated for the rest of the session.
  Every extension that toggled a tool read the active-tool snapshot, adjusted it,
  and wrote it back, so a snapshot that had not yet reported an extension's own
  registrations silently erased them. `pi-matt-pocock` then kept delivering routing
  prompts that name `matt_pocock_workflow`, instructing the model to call a tool it
  could not see.
  
  `@fradser/pi-kit` gains `setOwnedTools`, which re-asserts the extension's own
  tools instead of trusting the snapshot, and all five call sites now use it:
  `pi-matt-pocock`, `pi-monitor`, `pi-utils` sessions and worktree-session, and
  `@fradser/pi-agent-teams`' worker disclosure. Repeated identical writes are now
  idempotent rather than accumulating a duplicate entry.
- Updated dependencies [b3daa7f]
- Updated dependencies [95b15ac]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [e86a44f]
- Updated dependencies [8662e95]
- Updated dependencies [e86a44f]
- Updated dependencies [97e9add]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [a3ee3e3]
- Updated dependencies [2bba220]
- Updated dependencies [a0923d8]
- Updated dependencies [e86a44f]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [2116b41]
- Updated dependencies [e86a44f]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [95b15ac]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6aff737]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [257261e]
- Updated dependencies [71770f3]
- Updated dependencies [a3ee3e3]
- Updated dependencies [e86a44f]
- Updated dependencies [197b903]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [1c81c7a]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [7ac2735]
- Updated dependencies [df91761]
- Updated dependencies [1c81c7a]
- Updated dependencies [7ac2735]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [135dd1e]
- Updated dependencies [e86a44f]
- Updated dependencies [8662e95]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-subagents@0.2.0
  - @fradser/pi-kit@0.6.0
  - @fradser/pi-tasks@0.2.0

## 0.10.0

### Minor Changes

- 746bc7e: Bind worker communication and submissions to the Assignment Attempt that started the turn, so an old turn can never send or submit as replacement Work, hold the cancellation tool while a superseded lease must be acknowledged, and stop re-sending acknowledged cancellations. Failed, interrupted, or crash-released Work now returns as `pending/recovery-required` and is excluded from autonomous claim notices until the Leader explicitly assigns the next attempt. Nonterminal worker reports from a retired attempt stay in session history but no longer act as current leader instructions, while accepted terminal results and harness diagnostics keep their delivery contract. Leader and Worker guidance gained the two sentences that state the new contract; the governed prompt-budget ceilings for those sections were raised accordingly (5,250 and 2,150 with a 16,100 total).

### Patch Changes

- 67d7d19: Declare `type: "object"` on the union-root coordination tool schemas (`agent`, `work`, worker `work`). Google's GenerateContent API rejects a tool whose `parameters` carries `properties` without an object type (`parameters.properties: only allowed for OBJECT type`), so every Gemini-routed request that included those tools failed with a 400; OpenAI and Anthropic routes tolerated the omission.

## 0.9.2

### Patch Changes

- 906b5bc: Accept coordination tool parameters that arrive as JSON strings. A harness that JSON-parses each tool parameter by name reads the root schema's `properties`, but the `agent`, `work`, and worker `work` tools describe their per-action contracts as a root union, which exposes only `anyOf`, so `definition`, `target`, `dependsOn`, `resources`, and `supersedes` reached validation as unparsed strings and every branch rejected the call before its handler ran. Each root schema now mirrors the parameters of its branches as optional string-tolerant properties while every branch keeps its strict per-action contract, handlers parse those parameters back into objects and arrays before branching on them, and a structured parameter that cannot be parsed is rejected explicitly instead of being used as a literal.

## 0.9.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.9.0

### Minor Changes

- f177948: Keep the compact agent and agent_event interface while making new delegations independent Work Sessions. Add optional fork (fresh context by default), exact work and message routing for concurrent assignments, and runtime-owned final-answer reporting after execution settles. Completion evidence and finish announcements now belong to each assignment attempt rather than an entire resident process.
- 28c908c: Introduce persistent Agent delegation (`agent`) and symmetric shared communication (`agent_event`), transitioning from ephemeral teammates to cross-project persistent Agents.

### Patch Changes

- e614d0d: Close the leader coordination loop after Agent starts, steers, and deliberate presence inspections. Tool results and guidance now state that kickoffs are already delivered, routing acknowledgment does not require confirmation, presence is not a completion signal, and leaders should continue independent work or end the turn for automatic result delivery instead of echoing, polling, or requesting reports.
- b0231e3: Render coordination message previews against the actual terminal width rather than a fixed character limit, reserving the complete configured expansion hint. Expanded message rows wrap the full message inline after the recipient and outcome exactly once instead of repeating a clipped preview above a duplicate body. Preserve semantic line breaks, native theme bands, and safe display text, including visible labels inside terminal OSC-8 hyperlinks. Keep literal JSON empty strings, punctuation spacing, and quoted newlines intact by separating handle replacement from prose cleanup. Reuse the same pi-kit lifecycle abstraction as context research; native Ctrl+O, mouse expansion, and terminal resizing are covered by isolated Pi integration tests.
- b0231e3: Deliver explicit and automatic Work outcomes through the same attempt-bound acceptance path after execution settles. Prevent false finalization reminders, duplicate automatic submissions, stale-attempt acceptance, and implicit Work creation from ordinary messages. Expose bounded result evidence in Work lists and clarify push-based result delivery.
- b0231e3: Await native unassigned-resident readiness in the public start result so immediate exact-session Work assignment succeeds without polling. Surface startup failures and preserve the existing assignment when the same exact owner is assigned its still-claimed Work again. Later autonomous board acquisition remains enabled.
- b0231e3: Expose effective session tool grants and coordination-only warnings in lifecycle results, clarify canonical minimal capabilities and unknown-Agent recovery, and require explicit failed submissions for blocked work. Clarify ungated acceptance and actionable leader communication without expanding permissions or inferring outcomes from prose.
- d3180eb: Harden agent lifecycle coordination, durable intent handling, and transcript presentation:
  - Publish board intents atomically through a fully written temp file that is hard-linked into place, so a consumer can never observe or destroy a partial claim or submission record
  - Retry an unparseable intent while it is younger than the publish grace instead of deleting it, so an in-flight intent cannot strand its author
  - Archive and diagnose an unreadable persisted Work snapshot instead of silently continuing with an empty board
  - Rotate a fully consumed oversized inbox instead of truncating it, so a concurrently appended peer message is never lost
  - Abort an in-flight gate reviewer when a holding's authority is invalidated by release, stop, supersession, a new claim, or resumed owner execution
  - Reject a late passing gate while teammate shutdown is pending
  - Reject completed submissions during an unexpected-execution review park
  - Report the residual write window when Work is released while its holder is still working
  - Reconstruct the full brief — subject, description, criteria, and diagnostics — for an authorized verification revision
  - Route steer and delivery feedback to an active teammate when the leader releases its Work
  - Keep expanded agent delegate, inspect, and stop rows free of duplicated prompts, stale states, and retired activity
  - Drop the expanded inspect row's state word, which repeated the row's own header and could contradict it
  - State the coordination-only warning on delegate and start rows, matching the documented grant disclosure
  - Write each snapshot artifact only when it changed, and throttle the forensic whole-state file while a teammate streams, instead of rewriting every artifact twice a second
  - Bound the mailbox by total bytes as well as by message count, so long reports cannot grow the debug snapshot without limit
  - Bound confirmed-stop and finish bookkeeping per session instead of accumulating one entry per incarnation
  - Stop claiming the completion gate is read-only: its grant excludes edit and write, but a shell can still write
  - Carry a single-line Work subject with the complete brief retained as the Work description
- 43b51c5: Remove leader heartbeat and stall notices. Silence, spawn age, and usage stay as passive console telemetry in `/agent-teams` (roster "stalled" marker at `PI_TEAMMATE_STALL_SILENCE_MS`, default 5 minutes); the leader context is never interrupted by health prompts, and provider hangs surface only through the standard terminal close-path diagnostic. See `docs/adr/0002-no-leader-heartbeat-notices.md`.
- b0231e3: Start unassigned residents without a fabricated Work ID or an empty-assignment model turn. Establish idle readiness through a native RPC acknowledgement while preserving subsequent autonomous board claims. Clarify recovery by releasing and reassigning the same Work instead of delegating competing duplicate Work.
- 34c5b62: Start every new Assignment Attempt in a fresh correlated Pi RPC session before delivering its prompt, while preserving working memory for guidance within the same attempt and releasing work when the reset cannot be completed.
- ac83f4e: Prevent pre-cancelled child workers from spawning, fail closed on bounded worker stream violations, and disable extension discovery for isolated side-question and research children.
- 9cabb0d: Bump every package by one patch version.
- b0231e3: Clarify agent orchestration with scoped dependency-aware assignments, one integration verification owner, candidate-bound review evidence, and a finish line that waits for blocking review results. Distinguish review Work completion from an implementation PASS, describe `verify` accurately as a reviewer prompt, and refresh candidate briefs explicitly before bounded rechecks. Review-only assignments finish with their reports rather than implementation repairs; reuse completed Work only with an authoritative current-attempt brief, otherwise create a linked bounded follow-up. Make Matt Pocock reviews proportional and support confirmed conversation requirements plus scoped uncommitted baselines without changing runtime lifecycle or persisted state.
- d3efa47: Teach leaders to continue independent work or yield the turn while teammates run, relying on automatic result delivery instead of extending the turn with polling or wait commands.
- c5d658f: Render `agent`, `work`, and `agent_event` transcript rows for people instead of
  models. A started Agent now shows its name, role, the full kickoff text, granted
  tools, and model; inspect shows the live status and current activity; Work and
  message rows lead with the Work subject and show the message that was sent.
  Session, Work, and assignment handles stay in model-facing tool content and are
  scrubbed from every rendered line (a Work id becomes its subject, a session route
  becomes `@name`), while text a person wrote themselves is preserved verbatim.
- 6d21149: Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.
- 919504f: Fix agent presence and work control to use current-session state instead of reporting a fabricated idle result. Deliver leader direction through native priority steering that also starts idle execution, and isolate completion reports by assignment so an earlier PASS cannot close reopened work. Align first-delegation guidance, terminal-report rejection, and transport outcome wording with these contracts.
- 919504f: Wrap custom transcript lifecycle messages in host ToolExecutionComponent so mouse click toggling works symmetrically with tool result rows.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- bc42356: Keep requested Agent names unchanged when starting or delegating, without appending a UUID. Preserve incarnation-bound session handles.
- 2033c26: Remove unreachable legacy Agent control, unused internal helpers and constants,
  and the unused keyboard HID encoder (hardware commands already use via-rgb).
  Retain active entry points, shared public APIs, configuration compatibility,
  and behavioral regression coverage. Remove superseded planning documents and
  checks that only assert documentation wording or recreate implementation in tests.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.
- c5d658f: Run the verification-gate reviewer as a bare Pi child. `buildVerifyReviewWorkerOptions` now supplies the whole worker options with `minimal: true` and the read-only `VERIFY_REVIEW_TOOLS` grant (read, bash, grep, find, ls), so a gate review no longer loads the project's extensions, skills, prompt templates, context files, or themes, cannot trigger another package's automatic memory learning, and leaves no session record behind.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0

## 0.8.3

### Patch Changes

- c568d73: Apply customMessageLabel color only to the [agent] prefix in teammate spawn rows

## 0.8.2

### Patch Changes

- 91dfc9a: Optimize worker guidance and kickoff prompt so teammates with assigned tasks execute them directly without redundant task board queries.
- 731f1cd: Clarify agent and sub-agent conceptual equivalence in teammate_spawn tool descriptions and prompt guidance so third-party skills and workflows routing to agents hit teammate_spawn seamlessly.
- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- 92944c1: Apply progressive tool disclosure across runtime packages. State-dependent capabilities are now hidden until their workflow state is active, and continual-learning no longer couples its guardrails to Matt Pocock workflow state.
- b28ef2d: Return a teammate's recorded terminal report in a pi-kit lifecycle event so the leader never needs to force a duplicate resend, and extend leader guidance against resend steers and task_list polling.
  
  Allow lifecycle renderers to explicitly preserve every expanded detail line for user-requested readbacks while retaining the default 50-line bound.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.8.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.8.0

### Minor Changes

- dcf3806: Deliver every teammate report to the leader: intermediate send_message(to="leader") reports now reach the leader as their own follow-up turn instead of parking in the console-only mailbox, and queued reports are never coalesced — one message, one leader turn, in arrival order, with an authored-at timestamp in the envelope. Leader-relevant harness events ride the same channel: clean-shutdown summaries, worktree diff notices (bounded preview plus branch retrieval command), and verify-gate escalations; task outcome notices and operational diagnostics stay console-log only to avoid double reporting. Worktree cleanup now commits remaining work onto the kept branch before removing the directory — previously the branch deletion destroyed uncommitted captured work — while failed-spawn teardown still deletes the empty branch. Worker guidance rations messages by value instead of throttling: every leader-bound message costs a full turn, bare status pings are forbidden.
- 953f548: Two-tier stall watchdog: a working teammate silent since spawn with zero lifetime model output and no running tool — the provider-hang signature — is flagged after five minutes (`PI_TEAMMATE_SILENT_STALL_MS`, 0 disables) instead of the general thirty-minute window. Stall notices carry silence duration, spawn age, and lifetime token/cost diagnostics, and the zero-output notice names shutdown plus respawn as the effective remedy since steering cannot unstick an in-flight request. Streaming usage is now persisted to the roster, making zero-token hangs visible before shutdown.
- 9a80d93: Fixes from the first live analysis of the stall watchdog and tool-grant work, plus the delivery-gap root cause it surfaced: a spawned teammate runs its kickoff turn immediately, so marking prompt-less spawns idle at birth mislabeled an actively-running turn as idle — queued leader messages were then delivered into that running turn and lost (the teammate kept reporting "board empty" until a steer landed). Status now stays "starting" until real stream events arrive and flows starting→working→idle from stream truth. The provider-hang classifier now keys on recognized stream activity (text/thinking/toolcall/tool events) instead of usage totals — providers that omit usage after real output are no longer misclassified, and an empty message_end artifact never counts; usage stays diagnostics. The grant is flushed to both rosters before the kickoff is written, and historical spawn renders read persisted details only so name reuse cannot display another incarnation's allowlist.
- ab0feb8: Spawn surfaces now expose each teammate's effective tool allowlist: `teammate_spawn` records the granted tools in the roster before the first wake, the spawn result line and console detail name them, and a role derived inline without a `tools` field visibly shows its narrow capability-only grant. Leader guidance now requires matching definition tools to the assignment — file-inspecting work needs explicit `read`/`bash` — and prescribes shutdown-plus-respawn instead of steering when capabilities are missing. This prevents workers from burning turns discovering they cannot execute their kickoff.
- a7fbc11: Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.

### Patch Changes

- dcf3806: Dispatch the first teammate report to Pi's native follow-up queue even while the leader is active, rather than holding it in Agent Teams until the complete leader run settles. Later reports remain FIFO-serialized until the dispatched report settles.
- dcf3806: Keep requested teammate shutdowns in the tool lifecycle and console instead of emitting misleading agent-message follow-ups, and use an explicit harness-event envelope for lifecycle diagnostics that do wake the leader.
- fde16ae: The leader's send_message no longer rejects a stray `status` field with "status is reserved for worker reports to=leader". The shared message schema exposes `status` to leaders too, and leader models occasionally copy it from worker report patterns — which hard-failed the call and blocked teammate delivery (observed live in hud-playground). A stray status on a leader-sent message is now ignored with a one-line corrective note appended to the tool result, and the leader tool description no longer mentions `status` at all. Worker-side semantics are unchanged: status is still honored only for reports addressed to "leader".
- fde16ae: Clarify message routing truth: active control-stream writes render as `steered`, inbox/outbox and wake-up paths render as `queued`, and neither outcome implies recipient processing. Stall diagnostics now render independently as teammate health events instead of message suffixes.
- fde16ae: Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
- dcf3806: Reject non-finite teammate report timestamps and keep malformed metadata from interrupting follow-up delivery.
- dcf3806: End the current worker turn after a terminal leader report, and suppress subsequent reports until a new wake-up while preserving distinct intermediate reports and assignment boundaries.
- fde16ae: Clarify task creation handoff: `task_create` now reports that it never spawns teammates, identifies the current session board, immediately offers newly-created work to existing idle teammates, and explains how pending work proceeds when no teammate is available.
- dcf3806: Preserve the configured expand hint for lifecycle tool rows when a result has structured details but an empty visible content body, such as teammate_spawn's `{ started: true }` result. The title truncates before the hint so `ctrl+o to expand` remains visible within the available TUI width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.7.0

### Minor Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · steered|queued` row carries only the synchronous routing outcome, replacing the duplicated call-plus-sentence transcript rows. Teammate stall health renders independently as an `[agent] event` rather than decorating a message row. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.

### Patch Changes

- 82b8e8b: Honor multi-line YAML tool lists in agent frontmatter and make unfinalized teammate reports self-finalize before escalating. `parseFrontmatter` now parses dash-list `tools:` blocks — flush-left or indented items, interleaved blank/comment lines, no-space `-item` entries — which previously collapsed silently into an empty execution allowlist. When a teammate's sequence ends while its last leader-bound report lacks terminal status, the machine drains outboxes before deciding, sends one inbox finalize request per spawn incarnation instructing `status="completed"`/`status="failed"`, escalates to the leader reminder only on a second miss, cleans up nudge bookkeeping on every shutdown path, and the worker-side `send_message` result reminds when a leader-bound message carries no terminal status.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.6.0

### Minor Changes

- 7ad11b4: Rebuild Agent Teams as a Claude-Code-style collaborative organization layer: named resident teammates (long-lived RPC child processes), a shared task board with atomic self-claim and verify-gated completion, and direct peer-to-peer inbox messaging. The former DAG API (`teammate_run`, `teammate_fanout`, `teammate_cancel`, `teammate_retry`) remains removed. Simplify the new team surface to seven unique tool names: `send_message(to, message, status?)` is the one messaging primitive for worker reports, peer mail, and leader steering; `task_list` is shared by both sides; and `teammate_spawn` now accepts only name, agent, and optional prompt, with model/worktree moved to declarative agent frontmatter.
  Agent definitions gain a fourth scope for custom teammates: inside `.pi/agents/`, a `<name>.local.md` file declares a personal project-local override that stays out of version control, while `<name>.md` remains the git-managed team-shared layer; same-name pairs deduplicate into one definition with local winning. Precedence is project-local > project > user > bundled, and `resolveAgent` exposes each definition's scope and gitManaged flag so guidance and tooling can show provenance.
- 7ad11b4: Add an output-silence heartbeat for resident teammates. A teammate wedged mid-turn (for example, blocked forever in a provider request) never accumulates assistant turns and produces no RPC output, so nothing could alert anyone while the roster showed "working" indefinitely. The harness poll now tracks `lastOutputAt`: after 30 minutes without any output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) the leader receives one actionable notice per silence episode naming the teammate and its recovery options. The notice is the last automatic action — continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any stream activity or prompt delivery re-arms the watchdog. The health notice states that steer delivery may be uncertain without changing the message-routing result, and the widget, console roster, and detail views show how long a working teammate has been silent.
- acbadc7: Adopt full teammate autonomy as the package constitution: the harness detects and notifies, the leader model decides — no configuration may automatically terminate a working teammate. Remove the per-wake-up turn budget (the former 100-assistant-turn ceiling that silently killed long sequences) and do not ship any duration-based auto-reclaim. Turn counts and silence durations remain visible as telemetry and heartbeat signals; the stall notice is informational and names the recovery options (keep waiting, steer again, shut down, or respawn a successor whose prompt composes context from the original kickoff, mailbox reports, board claims, and the console detail transcript). Leader guidance gains a "recover, never punish" section teaching this workflow.

### Patch Changes

- 1503fdb: Use `teammate_message` for teammate completion and run notifications instead of the legacy `teammate-update` custom message type.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.5.2

### Patch Changes

- a1b37a0: Remove the `Console: /teammate` navigation hint from the `[teammate-update]` run summary follow-up message. The console affordance stays in the live widget, but the completion message no longer prompts the user to open the console.
- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.5.1

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.5.0

### Minor Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.4.0

### Minor Changes

- f3b5cd7: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - `teammate_run` dispatches a dependency-aware task graph in one call. Tasks support `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`; root nodes start immediately, downstream nodes auto-start when dependencies complete, and overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - The leader surface is `teammate_run`, `teammate_fanout`, `teammate_message` (for steering a running RPC worker), `teammate_cancel`, and `teammate_retry`.
  - The worker capability is `teammate_message` (progress, blockers, and final deliverables to the leader). There is no peer delivery, worker inbox, leader broadcast, or separate worker report capability.
  - Removed: `teammate_wait` (replaced by automatic completion follow-ups and inline gather), `teammate_cleanup`, `teammate_inbox`, and the legacy registry tools (`teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, `teammate_cancel_task`).
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Messages are validated through per-worker append-only outboxes and collected in one leader inbox; DAG handoffs inject upstream results into downstream prompts (`=== UPSTREAM HANDOFF ===`).
  - Advisory write-conflict coordination spans all runs in the session: overlapping shared-workspace write nodes are deferred unless worktree-isolated. `paths` and `access` are scheduling and prompt metadata, not filesystem permissions; there is no OS or container sandbox and no true read/write enforcement.
  - Full-screen `/teammate` console with live activity stream and mouse-wheel scrolling.
  - Worker protocol keeps per-spawn identity validation, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.

## 0.3.0

### Minor Changes

- e16cd3f: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - `teammate_run` dispatches a dependency-aware task graph in one call with `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`. Root nodes start immediately; downstream nodes auto-start after dependencies complete; overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - Automatic completion follow-ups for background runs, bounded inline gather, `teammate_fanout`, `teammate_cancel`, `teammate_retry`, and leader-side RPC steering through `teammate_message` provide the run lifecycle surface.
  - Removed: `teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, and `teammate_cancel_task`.
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Read-receipt protocol removed: messages have no read flags or receipt events.
  - Workers use the worker-only `teammate_message` capability for progress and final deliverables. Messages have one destination: the leader's inbox; there are no peer mailboxes, worker inboxes, leader broadcasts, or separate report capability. DAG prompt handoffs provide upstream results to dependent workers.
  - `paths` and `access` coordinate scheduling and prompt context only. Shared-workspace protection is advisory write/write coordination; it is not true read/write enforcement and does not provide an OS or container sandbox.
  - Worker protocol keeps per-spawn identity validation, one leader inbox, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.
