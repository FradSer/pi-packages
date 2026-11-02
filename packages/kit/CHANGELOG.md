# @fradser/pi-kit

## 0.6.0

### Minor Changes

- 426ef90: Judgment: an optional decision surface that observes the Memory Selector in shadow mode, and the shared transport it runs on.
  
  Judgment answers bounded questions with typed answers and probabilities instead of generated prose. It never authors Memory, Harness, or AGENTS.md content — the request builder admits only `noul`, `choice`, and `score` questions, so a generative answer is unrepresentable rather than merely discouraged.
  
  **It is off by default.** It activates only when an API key resolves from `TYPESAFE_API_KEY` or from an `api` block in `~/.pi/agent/continual-learning.json`. The environment wins, so one run can be pointed elsewhere without editing persisted state. An unreadable file, malformed JSON, an unsupported field, or a configuration without a key all fail closed to inactive with a reason: a configuration fault never changes what a run produces. The model is pinned to a versioned id rather than a moving alias, and the version that answered is recorded.
  
  **In shadow mode it changes nothing.** The selector's selection is the one that reaches the parent, always. Every run appends one observation record holding the run's context digest, each verdict and its confidence, the selector's own answer, and whether the two agreed. Refused connections, throttling, malformed answers, and cancellation are recorded and otherwise inert — an observer failing must not stop the observed work.
  
  **New in pi-kit**
  
  - `askSystemOne(options)` — ask one bounded question set and return typed answers. The judgment counterpart to `runPiWorker`, with the same lifecycle obligations: abort propagation, bounded response, explicit failure classification. Throttling and 5xx are retried with backoff honouring `retry-after`; a refusal, a malformed answer, and a cancellation are not.
  - `DecisionServiceError` with a `failure` of `cancelled`, `timeout`, `unauthorized`, `throttled`, `unreachable`, `rejected`, or `malformed`.
  - `SystemOneQuestion`, `SystemOneAnswer`, `SystemOneResult`, `AskSystemOneOptions`, `DecisionFailure`.
  
  Uses `fetch` and no new dependency. The endpoint is one authenticated POST; the SDK's 209 KB and a mandatory install for an off-by-default feature were not worth it, and pi-kit's dependency-free manifest is a tested property.
  
  A request with no questions is refused before it is sent, and a silently missing answer is reported as a service fault rather than read as an absent judgment — a caller that treated it as one would record a decision nobody made.
  
  **Contract:** `packages/continual-learning/features/judgment-shadow.feature`, `packages/kit/features/pi-kit.feature`. **Design:** `docs/adr/0006-judgment-shadow-mode-and-projection.md`.
  
  Three properties are structural rather than prompted. Judgment receives a bounded, code-derived projection — clipped request text, regex-classified harness event summaries, touched paths, registered skills, Memory metadata — and never raw tool-result content, because the Task Slice is verbatim user text and tool output that this package already treats as untrusted evidence, and a decision model does not treat request content as hostile by default. Candidates carry opaque index-derived identifiers, so an answer can never name a Memory file and invalid names, wrong casing, and duplicates leave parent-side validation rather than gaining checks. An observation is a judgment record, not a content record: no request text, no tool output, capped and rotated, written beneath the private agent directory and **outside both Memory roots**.
  
  Two of these were found by their tests rather than by review. Rotation reserved no space for the incoming record, so a full log ended 464 bytes over its cap. And rotation rebuilt the retained text once per candidate line, which made a full log cost seconds of CPU on every subsequent append — the sort of cost that turns a background observer into a stall. Retention now walks byte offsets once.
  
  Promotion out of shadow mode is measured, not assumed. Committed adversarial and agreement fixtures gate the package tests, and promotion additionally requires an agreement rate and an injection-resistance rate read from observations. The report proposes no threshold; choosing one stays a human decision. No threshold is encoded in code.
  
  **Memory proposals are judged, and nothing is dropped.** When a validated Memory plan is about to be applied, Judgment is asked whether each proposal is durable, how far it generalizes, and which indexed entry it restates. The parent still applies every proposal exactly as it does today; no proposal is dropped, narrowed, or reordered. What is recorded is the *baseline* — how good is a single proposal — which is the control the later question of proposing K candidates and choosing one needs. Asking for several candidates before this exists is an opinion rather than a measurement.
  
  The questions mix primitives on purpose. `noul` alone would leave every answer without a confidence, and confidence is what separates a settled judgment from a coin flip, so generality is a `score` and duplication is a `choice`. Against the live service a reusable build-command lesson scores 0.62 durable and 1.26 general; a one-off CI flake scores 0.19 and 0.09 at 0.91 confidence; a proposal restating an indexed entry is matched to it at 1.00 confidence. A plan with no proposals makes no request at all.
  
  **Every generative phase runs on the configured consolidation model.** The package header has always promised that "consolidation uses a separately selected Pi model when configured", but only the Memory phase honoured it: the Harness planner and the AGENTS.md extractor inherited the session default. A run could therefore propose a Memory with one model and a rule with another, and the token accounting would describe a model that produced neither. Both now receive the same `provider/model` resolved once per run, and a test asserts all three bind it, so the promise cannot silently regress again. Judgment resolves its own model from a separate configuration surface, so configuring one never substitutes the other.
  
  **All five surfaces are now reached in a real run.** The live smoke previously proved only the selector, the proposal surface, and the Harness surface. The two missing ones were unreachable for structural reasons, not test gaps. The Memory plan's operations on existing entries need the selector to have something to select, which needs seeded Memory; and the AGENTS.md phase was disabled in the smoke's own setup, and then had no project document to consolidate against once enabled. The smoke now seeds both, and its task carries the two signals that reach them: a reference to a seeded entry, and a correction naming an AGENTS.md workflow. The check is now strict — it requires all five surfaces and names the missing ones — so a broken hook fails the gate rather than passing on the two that happened to work.
  
  Two hooks were silently dead. The Harness and AGENTS.md observations both sat in the *apply* branch, so under the default propose policy neither surface was ever judged. The Harness one had appeared to work only because that run happened to use the apply policy. Both now fire before the branch, so they observe a plan whether it will be applied or only proposed.
  
  Verified: 671 package tests pass; tsc reports 0 errors; a full real-Pi live run observes every surface — phases selector, proposals, operations, and surfaces memory-operations, harness-operations, agents-operations — with agreeRate 0.8 and no request text, tool output, credential, or filename key reaching the wire or the record. A full suite run adds zero scopes to the real agent directory.
  
  **Promotion is a configuration change.** Judgment is shadow-only until a surface is named in `continual-learning.json`, so turning authority on or off never needs a release and the kill is one edit. Only `proposals` can be named: it is the only surface whose authoritative behavior is implemented, and asking for another is refused rather than silently accepted, because a switch that changes nothing would read as authoritative while doing what shadow mode did. When it is on, the judgment arrives before the parent validator and can only narrow — applied names always come from the plan, never from the model — and a failed, throttled, or unanswered judgment drops nothing, because a service outage must not discard real knowledge. Durability is a probability and generality is a score level, validated on their own scales. The receipt carries a gate clause reporting what was measured and proposes no threshold.
  
  **The measurement rides the receipt `/consolidate` already prints.** There is no second read-only command: the observation log would otherwise be written and never read, which defeats the premise of measuring first. A run that opted in reports one bounded clause naming the answering model, the observation count, the agreement rate, the surfaces judged, and proposals as a reusable-versus-one-off distribution. An unmeasured rate reads as "agreement not yet measured", never `0%`, and a user who has not configured Judgment sees the line unchanged.
  
  The first version of that reporting set the reusable cut at generality level 2, "reusable in any project". That is wrong for this package, whose whole purpose is project-specific knowledge: live runs score real project knowledge at 1.0-1.3 and genuine one-off noise at 0.09, so the kept list was structurally always empty — which reads as "the model thinks nothing is worth keeping", the opposite of what was measured. The cut is now level 1, "generalizes beyond this occurrence within this project", which is the meaningful cut for this corpus, and a distribution is reported alongside it so one number cannot imply more than the data supports.
  
  Suite hermeticity is part of the contract. Judgment activates from an environment variable, so a contributor who has configured the feature also has the key set — wiring Judgment into the selector made `pytest` silently make live billed calls to the decision service and write observation scopes into the caller's real `~/.pi/agent`. Six such scopes accumulated before it was noticed. A session-scoped `conftest.py` now strips `TYPESAFE_API_KEY`, `TYPESAFE_MODEL`, and `TYPESAFE_BASE_URL` for the whole suite, the selector tests isolate the agent directory, and a test asserts a run cannot add a scope to the caller's real agent directory. The suite must not depend on whether the person running it has a credential. Live calls belong only in the explicit, never-collected live scripts.
  
  Existing behaviour is unchanged: with no configuration, a run is indistinguishable from a run without the feature.
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
- e86a44f: `directorySessionsDir` resolves the shared directory-sessions registry directory from `PI_DIRECTORY_SESSIONS_DIR`, then `PI_CODING_AGENT_DIR` / `PI_AGENT_DIR`, then `~/.pi/agent`.
  
  **@fradser/pi-kit**
  
  - Callers had to spell the registry path themselves, and a package that hardcoded the home directory kept updating the user's real registry while the rest of the session ran against a sandboxed agent directory — one feature's state silently split in two. `directorySessionsDir` is that decision in one place, and `open-deskos` already resolved it independently.
  - Consumers to migrate onto it: `keyboard` (`src/global-sessions.ts`), `utils` (`extensions/sessions.ts`), and `open-deskos` (`src/discovery.ts`, which keeps its existing precedence). `recap` now uses it.
- 53cb34f: Pi-kit gains the shared worker-runtime primitives: the file and environment mechanics that every package spawning or running inside a child Pi process needs, and that the agent-teams split into subagents / task / agent-teams needs in more than one package.
  
  **New exports**
  
  - `readJsonlBatch(file, byteOffset, endOffset?, maxBytes?)` — incremental read of complete JSONL records after a byte offset. A truncated or recreated file restarts from zero so callers deduplicate by record id; an unterminated trailing record is left for the next read; a record larger than the batch cap is skipped with a diagnostic so one sender cannot block a drain; a missing file is empty rather than an error.
  - `appendJsonlLine(file, value, { maxBytes?, label? })` — capped append that creates a private `0700` directory and writes `0600`, refusing an oversized record instead of truncating it.
  - `writeJsonAtomic(file, value)` — atomic tmp-plus-rename replacement, leaving no temporary file behind.
  - `createExclusiveJsonFile(dir, name, value, { maxBytes?, label? })` — the single-writer intent race. `wx` makes the temporary file unique to the process and `linkSync` fails with `EEXIST` when the destination exists, so exactly one racer among any number of concurrent processes returns true. The name is escaped with `safeFileName` so a caller-supplied value cannot escape the directory.
  - `takeJsonIntent(dir, validate, { graceMs?, label? })` — drains the lowest-named intent. Malformed records are consumed and reported so one broken file cannot block the queue, but an unparseable record younger than the publish grace is retried, because destroying an in-flight intent would leave its author waiting forever.
  - `readRequiredEnvBinding(names, env?)` — an all-or-nothing environment binding. Any absent or empty required name yields `undefined`, so a partially configured child is treated as "not a worker" rather than as a worker with missing fields. An empty string counts as missing: treating it as present would yield a binding whose paths silently resolve against the current directory.
  - `safeFileName(name)`, plus `DEFAULT_JSONL_BATCH_BYTES`, `DEFAULT_JSONL_RECORD_BYTES`, `DEFAULT_INTENT_BYTES`, and `DEFAULT_INTENT_PUBLISH_GRACE_MS`.
  - `sessionKey(sessionFile, cwd)` — the scope key for per-session state on disk. It derives from the session file when there is one and falls back to the working directory, so two leader processes holding the same session share one directory and two sessions in one project do not. Shared because `@fradser/pi-tasks`'s board directory and `@fradser/pi-agent-teams`' runtime directory must agree on which session a directory belongs to.
  
  **Design notes**
  
  Diagnostics and oversize errors take a `label`, so a consumer can adopt these without changing wording its own tests and operators already read. `agent-teams` passes `"Worker event"` and `"task intent"` to reproduce its existing strings exactly.
  
  Domain validation, path layout, and coordination authority deliberately stay with the consumer: `takeJsonIntent` receives a validation callback rather than knowing any intent shape, and attempt-bound authority is not extracted here yet because both of its consumers are not visible until the split lands.
  
  These stay inside `src/index.ts` rather than a sibling module. That file's single-module layout is a documented loader-compatibility invariant — a zero-internal-import module resolves identically under Node's native type stripping, tsx, pi's extension loader, and tsc with any moduleResolution — so adding `src/worker-runtime.ts` and re-exporting it would reintroduce exactly the relative-specifier edge case the invariant avoids. Two tests now pin the layout.
  
  The section imports no Pi core package and no consumer package, keeping pi-kit's dependency-free manifest honest.
  
  Contract: `packages/kit/features/worker-runtime.feature`. Tests: `packages/kit/tests/test_worker_runtime.py`, where the single-writer race is asserted against eight real concurrent processes rather than two sequential in-process calls.
  
  No consumer is rewired yet; this is additive, so existing behaviour is unchanged.
- 842b92e: Pi-kit owns the canonical minimal worker grant (`read`, `bash`, `grep`, `find`), and a minimal worker without a supplied allowlist now receives it instead of Pi's default active tool set.
  
  **pi-kit**
  
  - `minimalPiWorkerArgs()` had no default, so a package that wanted the canonical grant had to name its own tools. The new `MINIMAL_PI_WORKER_TOOLS` export names it, and `minimalPiWorkerArgs()` falls back to it.
  - `runPiWorker({ minimal: true })` without `tools` disabled extension, skill, prompt-template, context-file, and theme discovery but left Pi's default active tools — `read`, `bash`, `edit`, and `write` — available, so a minimal worker could still write. It now receives exactly the canonical grant. `grep`, `find`, and `ls` were not part of that default set either.
  - A supplied allowlist stays authoritative, including an explicit empty list, which still grants no tools and does not fall back to the default.
  - An empty-string allowlist is a degenerate spelling of "no allowlist supplied": it now means the same thing in minimal and full mode instead of granting nothing in one and the default selection in the other. Only an empty array asks for no tools.
  - `grep` and `find` come from Pi's built-in tools, so discovery costs no extra model turn per lookup with no extension or third-party search package added.
  
  **@fradser/pi-context**
  
  - The research child's grant was a package-local `RESEARCH_TOOLS = ["read", "bash"]`, and every file lookup cost a separate model turn. It now uses `MINIMAL_PI_WORKER_TOOLS` (`read`, `bash`, `grep`, `find`), which keeps the grant inspection-only in intent and single-sourced while cutting the turns a research question costs.
  - The bundled worker prompt names the allowlisted tools and asks the child to prefer `grep` and `find` for locating files and matching lines.
- e86a44f: Retire the task board vocabulary and the `board.json` persistence fallback. Load and write only `tasks.json`. Remove the retired path and resolver exports. Preserve old files without automatic migration or deletion.
  
  Rename shared assignment kind `board` to `task`, use task-prefixed attempt ids, and rename worker binding to `PI_TEAMMATE_TASKS_FILE`. Use task names in coordination callbacks, notices, and console navigation. Update all contributing packages together and restart existing children before using the new bindings.
  
  This is a breaking library and worker-protocol change for these pre-1.0 packages. Task file format version 2, completion evidence, dependency rules, ownership, and recovery remain unchanged.
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

- e86a44f: Clamp shared scroll offsets at zero. Allow consumers to supply a horizontal-rule callback without changing legacy defaults.
  
  Delegate btw focus to its native input. Preserve loading animation during cache invalidation. Handle normalized fullscreen wheel events.
  
  Keep the composer visible in compact layouts down to 20 columns and 8 rows. Home and End edit the visible composer.
- e86a44f: Use Pi 1.3.0 for fresh continuous learning acceptance, with exact runtime pins
  and the declared CLI entry. Preserve historical Pi 1.0 and 1.2 results and costs.
  
  Run normal Memory body-consistency questions in a separate body-only job. Keep
  complete source, description, permission and preservation review. Count the new
  job within the existing prepared-request bound. Retain failed transport attempts
  and their known or unknown costs. Recognize explicit maintenance-purpose labels
  without treating draft claims as facts. These fixes do not prove learning benefit.
  
  Point historical Memory counter instructions at the actual `supportEvidence`
  and `reviewEvidence` fields. Keep source-support fields, complete evidence,
  historical bounded encoding and every approval gate unchanged.
  
  Use complete Memory content for evidenced maintenance purpose or applicability,
  with supported Why/How sections. Require an exact declaration only when the
  knowledge concerns an inspected declared API contract. Behavior and failure
  observations retain explicit source-backed subjects, dependencies and conditions
  without a required declaration excerpt. Keep the source-only
  excerpt interface and existing records unchanged. This is generation guidance,
  not evidence of better learning.
  
  Retain a safe Memory setup failure reason and zero generation calls when frozen
  evidence is refused before the planner starts. Sensitive evidence still blocks
  learning and later planners.
  
  Give semantic Memory rewrite repair the same exact old/new line comparison used
  by review, beside complete records and original evidence. Clarify that metadata
  edits do not by themselves resolve a separate preservation hold. Keep supported
  scope corrections, empty refusal, high reasoning and every semantic gate.
  
  Bind actual `/consolidate` and explicit backfill invocations separately from source-task evidence. Preserve the exact current command, session, run, project and source digest. A maintenance invocation supplies no facts, policy correction or privacy waiver; historical invocations do not grant current permission.
  
  Focus normal Memory rewrite support checks on the complete new record, original citations and bound current source. Keep complete predecessor records and historical purpose in every separate counter, permission and preservation review. Preserve uncertain holds, atomic approval, privacy, source bindings and all thresholds; this input change alone does not establish better learning.
  
  Keep explicit `/memory` commands after their older task evidence. Preserve the current request under the existing evidence bounds and bind its retained index through fresh source reads and planning. Use Pi 1.3 for fresh native acceptance; preserve historical Pi 1.2 runtime records.
  
  Refresh complete original-task source during explicitly requested Memory
  backfill, retaining original evidence and binding the fresh read-only observations
  through validation and writes. Keep stored Memory out of that collector's scope,
  and account for its failed calls and costs. Preserve complete historical coverage
  obligations and claim-condition relationships instead of flattening their questions.
  Bind failed manual Memory requests to their own native invocation, original source
  and cost-bearing receipt so authorized backfill can recover their correction input
  without acknowledging another task or broadening beyond Memory. Superseded or
  abandoned requests cannot replay; a new input or session change cancels active
  manual work. Process the newest pending manual invocation first without skipping
  an invalid request into ordinary learning. Failure planning
  prioritizes observed pitfalls without treating API inventory or unverified causes
  as learned fixes. These changes do not establish accepted knowledge or later benefit.
  
  Give automatic Harness planning and repair a bounded read-only case evaluator using the same parent validation. Retain real rejected cases as regressions; passing a preview grants no evidence, semantic approval, ownership or mutation authorization.
  
  Describe Harness case selector membership accurately during semantic review. Matching guidance, confirmation and retired-rule cases are no longer mislabeled as blocked actions; retain complete expected outcomes, predecessor rules and all authorization gates.
  
  Clarify knowledge, executable validation and scoped guidance throughout learning protocols. Recognize explicit knowledge and verification lessons, preserve skipped task references by project, and stop safely on invalid settings or session shutdown. Freeze evidence before asynchronous preparation, reject Memory creation that bypasses new-knowledge evidence, protect mirror roots, and prevent Harness annotations from triggering their own rules. Preserve installed rule protections and consistent scoped-user precedence.
  
  Keep one model across planning and repair, serialize bounded backlog writes and monotonic scoped cursors, and prevent legacy cursors from consuming new scoped references. Extend sensitive-material rejection to direct AGENTS extraction and expose effective learning state through `/memory status`. Add real Pi offline learning-loop and interactive verification without external provider calls.
  
  Make incremental planning and repair declare the same exact new-knowledge schema, and retain the original rejection when repair fails. Strengthen real-model verification with exact answer scoring, successful native reads bound to the candidate Memory files, complete shared-surface privacy checks, and fresh-session tool-call evidence.
  
  Render exact parent-owned identity JSON for incremental planners, retain per-candidate original citation associations in Memory support reviews, and separate Harness counter-evidence from repeated authorization. Preserve semantic thresholds, complete review windows and rejection of identity drift.
  
  Distinguish source-comment explanations and historical test counts from durable verified knowledge. Keep queue-completion knowledge scoped to the inspected callback phase; an empty queue does not guarantee that future caller continuations have drained. Complete only strict-prefix display messages of new literal rules from a single validated user quote, retaining both plans and revalidating the actual reviewed and applied candidate.
  
  Retain a bounded fifteen-second default semantic-service request deadline after a real frozen response exceeded the old five-second deadline. Honor explicit deadlines and cancellation, preserve connection-only retry bounds, and distinguish task-local verification instructions from independently observed reusable source knowledge during planning and repair. Semantic thresholds and full evidence remain unchanged.
  
  Separate an assertion's printed failure label from the state that its complete test and observed execution establish. Require Memory generation and correction to trace completed callbacks and unfinished work before naming the blocking subject, or preserve the state as unresolved. Keep all original evidence, prior rejections and semantic gates.
  
  Allow a fully reviewed new Memory fact to persist beside a held byte-identical rewrite only with complete original mixed bindings, direct independence against the persisted record, standalone and body review. Never write the held record or clear its pending status. Keep source, privacy, ownership, transaction, Harness and backlog gates.
  
  Keep partially learned tasks pending until the latest phase disposition has no unresolved candidates, and render those counts as warnings. Route source-verified empty-index backfill consistently with automatic learning and retain rejected selector output in a bounded private diagnostic artifact. Clarify that permanent executable restrictions remain Harness-owned rather than being relabeled as Memory workflow facts.
  
  Limit semantic Memory correction to sparse replacements for parent-marked candidates, retaining all omitted intents unchanged and rejecting unrelated changes, new names, kind changes and privacy changes. Revalidate the complete merged plan; retain bounded repair responses privately with sensitive-material omission. Include individual original citation associations in body and description counterevidence questions without removing any evidence windows.
  
  Preserve uniquely paired original tool invocation provenance alongside cited results without promoting assistant prose to evidence. Associate Harness support questions with each candidate's exact original quotation while preserving all later corrections. Distill automatic Memory toward non-obvious reusable lessons rather than routine source inventories; preserve explicitly requested knowledge and personal preferences.
  
  Preserve independently accepted Memory fields during bounded semantic repair and retain their citations before full revalidation. Add optional parent mutation-batch attribution to learning receipts, preserving legacy readability. Strengthen the real continuous-project study with source-bound actual verifier feedback, exact receipt acknowledgments, later consumption of failure lessons, and independent full-source correction auditing; incomplete coverage cannot be reported as completed learning evidence.
  
  Unify bounded unique-plan framing between initial and repair workers, reject damaged later drafts, and report controlled repair failure stages. Preserve type-level versus runtime evidence scope in independently reviewed index descriptions.
  
  Review cited rewrites and deletions through complete original evidence windows while retaining mutation and preservation context. Keep existing Memory bodies, exact citation validation, full counterevidence coverage and unchanged wire/semantic bounds.
  
  A selector response with the current identity but missing required routing fields may receive one structural correction using the unchanged task and metadata. Every present authoritative field must already be valid; corrected responses pass full selection and dossier validation. Preserve the original failed attempt and both calls’ usage in receipts, and omit sensitive response material from private diagnostics.
  
  Split whole counterevidence windows against actual encoded request size and existing question-batch bounds, preserving complete support and mutation context and rebuilding final review bindings. Retain private structural-repair response diagnostics through the existing sensitive-material filter.
  
  Require independently retrieved Memory descriptions to preserve observable meaning and material conditions; explicitly distinguish API invocation from outcomes and Promise adoption from settlement without changing judgment thresholds or body acceptance.
  
  Bind each Memory question batch to its candidates' complete original cited entries and invocation provenance instead of repeating unrelated support unions. Group questions by candidate and preflight the resulting encoded requests, preserving full per-candidate counterevidence coverage, old/new mutation state and all existing limits.
  
  Replay the longest independently digest-verified same-task prefix extension, retaining actual failure feedback and original observations. Bind covered references in one parent receipt, recover durable completions before choosing new work, and acknowledge the receipt owner last without duplicating usage ledgers. Preserve retry limits, cancellation, failed attempts and incomplete-evidence policy through replay.
  
  Preserve source branch eligibility in generated and repaired Memory bodies and descriptions, and explicitly check guarded state transitions in semantic review. Conditional source behavior must not become unconditional knowledge; evidence and acceptance thresholds remain unchanged.
  
  Restore only uniquely matched source indentation within the existing structural
  Memory correction slot, retain exact quote/role/privacy and semantic gates, and
  record parent-controlled citation rejection and correction provenance. Mixed
  citation failures receive exact source spelling hints without changing claims,
  indexes or mutation authority.
  
  Apply independently verified new Memory records from mixed plans in the ordinary
  Jev-enabled, apply-authorized pipeline. Preserve held proposals and pending work,
  require full relationship and standalone proofs, retain atomic rewrites/deletes,
  and make persisted knowledge available to later tasks. Additional review costs
  remain visible; partial learning is never reported as complete.
  
  Separate Memory relationship review from mutation preservation context so proposed
  knowledge cannot be judged as its own duplicate. Compare corrections with other
  established records while retaining exact predecessors, complete original evidence
  and all proposed operations in grounding and preservation checks. Deletions retain
  those checks without requiring novelty. Keep semantic thresholds and wire bounds.
  
  Allow knowledge corrections to cite exact original successful-edit patch lines,
  so a generic replacement-success message does not hide the changed declaration
  from eligible evidence. Preserve diff markers, original indexes and all semantic,
  privacy, snapshot identity and mutation gates; reject failed/ambiguous edits and
  assistant arguments as patch sources. Keep TypeScript and final Python validation
  consistent for both initial plans and bounded repairs.
  
  Bind selector artifact identity and exact Memory names in the parent. Model
  responses select frozen metadata positions and explicit phase decisions instead
  of copying digests and filenames. Reject invalid, duplicate or ambiguous choices;
  retain strict legacy validation and all downstream mutation gates.
  
  Review selected retained Memory against full evidence even when the planner
  proposes no operations or only changes other records. Prevent contradicted or uncertain retention from being
  acknowledged as completed learning, and permit one cited, scope-preserving
  amendment covering every held record through the existing parent gates. Preserve
  original proposals exactly while combining a retained-record amendment.
  
  Recover a current-digest selector response with an invented schema through one
  bounded structural correction, retaining both calls and costs. Preserve independent
  Harness and AGENTS routing and every ordinary evidence and mutation gate.
  
  Allow planners to learn a bounded observed failure before a successful correction,
  without claiming a verified cause, fix or standing user constraint.
  Keep task execution and isolation constraints out of permanent Harness rules
  unless current user evidence explicitly establishes future scope.
  
  Use the same bounded selector correction for valid current-index responses with
  missing phase fields. Require independently decided complete output rather than
  filling routing defaults; preserve the actual rejected response and both costs.
  
  Align Memory support review with source-bound unresolved defect learning while
  rejecting permanent failure generalizations, guessed causes and invented fixes.
  Preserve original candidate arrays omitted by a sparse semantic repair, instead
  of rejecting a valid unchanged intent; malformed arrays and all later gates remain.
  
  Review retained and proposed Memory failures before the same bounded correction so an early retained hold cannot consume correction without exposing new unsupported claims. Preserve unflagged fields and revalidate the combined plan.
  
  Restore unique citation indentation before semantic-delta merge and avoid counting redundant new subquotes twice while preserving original evidence and bounds. Narrow new proposals with unsupported explanations to their fully reviewed original descriptions, with immutable review bindings, complete checklists and full final revalidation; never truncate existing Memory rewrites.
  
  Separate the single structural correction from the single semantic knowledge correction. A representation repair no longer prevents correcting subsequently held retained/proposed knowledge. Retain both attempts and costs, structural rejection metadata and screened response; apply once only after unchanged final validation.
  
  Allow bounded correction of both rejected Memory claim fields to replace their citation footprint. Keep original citations when either field remains protected, archive the rejected plan, and preserve all final citation bounds and complete semantic validation.
  
  Preserve structured state on the Jev wire and share exact per-candidate Memory
  support citations between independent body/description judgments. Avoid nested
  JSON escaping without trimming source evidence or relaxing byte/request/semantic
  bounds; retain over-bound proposals and their failed learning costs.
  
  Correct conflicting semantic-repair instructions that compressed multi-fact rewrites into one fact, discarding still-valid predecessor knowledge and observed failures. Keep description brevity separate from body preservation; full validation remains required.
  
  Preserve actual corrected Memory content and citations when considering optional description distillation. An original description checklist cannot replace a newer correction with the older wording; unchanged held proposals retain the existing fallback and full final validation.
  
  Deduplicate repeated proposal quotations only in semantic comparison context, retaining exact bodies, preservation intent, original source indexes, roles and quote digests. Each candidate keeps its full citations and source review; persisted evidence and all request/semantic bounds remain unchanged.
  
  Defer an older same-task replay when independently verified later feedback has reached its retry bound, instead of learning stale partial evidence. Keep the original limits, pending references and costs intact, and report that newer feedback requires review.
  
  Preserve protected field citations through a larger verified same-source quotation when it contains the entire original quote, avoiding duplicate-count rejection of a real correction without dropping source bytes or changing citation limits.
  
  Preserve parent-validated rewrite and retention context when reviewing Memory index descriptions independently. Replace only the reviewed text, keeping existing target, privacy and preservation intent without adding create metadata or relaxing semantic thresholds.
  
  Preserve held Memory feedback across independently verified same-task prefix extensions, bind diagnostics to the original whole or subset plan, and reject foreign completion receipts. Stop new learning calls when cancellation arrives during durable attempt saving. Rank complete Memory bodies using compound API cues without awarding relevance to generic instructions; preserve existing budgets and validation thresholds.
  
  Report bounded citation-location failures together to the existing single Memory correction, preserving quote limits and parent validation.
  
  Expose complete long evidence lines as numbered chunks and extract explicit same-line character spans without decoding or raising citation bounds.
  
  Bind structural new-Memory filename spelling corrections to a parent-supplied identity map, preserving privacy and existing-target validation.
  
  Clarify first-time `/harness` authoring and scoped operational safeguards when the target configuration is absent, without claiming that contextual guidance enforces traffic limits.
  
  Distinguish an unresolved empty retained-Memory correction from protected-intent drift, preserving the failed review and all mutation gates. Include retained-record review context when the initial delta is empty.
  
  Keep first-use Harness authoring on the project-relative target and prevent verification from requiring scratch files or additional configuration writes. Retain unavailable trigger checks as unverified; native acceptance checks plain positive/negative selectors and fresh-session delivery separately.
  
  Require read-only parent Harness trigger previews before authoring writes. Bind each preview to exact candidate and predecessor bytes, consume it once across concurrent calls and legacy confirmations, and reject empty first-use placeholders. Keep existing mutation authorization and effective-configuration validation.
  
  Reuse unchanged Memory indexes in context, list deduplicated filenames and descriptions without source suffixes, and read bodies only on demand. Restore missing references after compaction or branching.
  
  Revisit indexed Memory actually read by the model during automatic correction, using unique successful call/result pairs and keeping explicit maintenance scope and mutation gates unchanged.
  
  Declare automatic Harness preview arguments as structured rule and case objects so providers receive concrete transport types; preserve rejection of serialized strings and all parent validation gates.
  
  Bind missing-output Harness recovery reads to the original authoritative dossier path instead of inventing a dossier in the Harness run directory; preserve exact-file scope and the single recovery budget.
  - Bind semantic Memory claim corrections to parent-owned candidate IDs, preserving original targets, operation kinds and privacy while retaining citation, field-preservation and semantic gates. Empty corrections remain failures.
  - Remove only self-contradictory duplicate Harness negatives already covered by valid positives under the unchanged rule; retain all unique cases and semantic approval, and preserve the original plan in the private normalization record.
  - Account for all completed Harness worker calls and retain known incomplete usage separately instead of reporting a last-call cost as a run total.
  
  Allow one independent correction for the observed numeric selector field alias without accepting the malformed decision. Preserve complete and incomplete worker costs through parent-owned ledger identities and actual receipt matching, including crashes between worker completion and receipt persistence.
  
  Review complete Memory bodies for internal contradictions independently of source support, using the existing semantic correction slot for unsupported clauses. Give incremental planners the full frozen dossier without retrieval tools, preserving lossless original evidence and mutation gates. Persist numeric worker usage incrementally so later timeouts retain known costs.
  
  Ask native per-run consent before explicit private Memory maintenance can spend
  model calls on a plan that Jev privacy policy will refuse. Keep the original
  judge configuration frozen, preserve all semantic gates and refused proposals,
  and report preflight refusals with zero calls and known zero added cost.
  
  Inspect decoded JSON evidence for credentials so Markdown headings and escaped
  line breaks cannot falsely block Memory maintenance, while real credentials in
  values and keys remain refused. Report citation-count and coordinate failures
  together to the existing single repair without changing either acceptance bound.
  
  Recheck missing scoped source paths without treating them as facts or discarding
  independently verified reads. Explicitly disable OpenAI completions tool calls
  when a source audit exhausts its read budget, and abort excess calls while
  retaining their failed observations and costs.
  
  Label citation eligibility on each lossless evidence entry to keep assistant
  inferences out of learned knowledge, and send damaged-output recovery guidance
  only for actual damaged plans instead of confusing existing-record repairs.
  
  Admit the observed positional selector spelling with bounded surface notes to
  the existing single independent correction; never accept aliases or infer phase
  flags from those notes, and keep both failed and corrected call costs.
  
  Permit one independent selector correction for a confirmed missing terminal
  object brace; diagnostic reconstruction never becomes a routing decision.
  
  Allow explicit existing-Memory maintenance one independent fresh plan after a
  cleanly terminated incomplete JSON response. Recheck current source and Memory,
  reuse the complete frozen dossier, preserve the first failure and both costs,
  and keep every final citation, semantic, privacy and write gate unchanged.
  
  Ground existing-operation classifications in the frozen parent inventory during
  structural correction. Report classification conflicts alongside other repair
  errors instead of preserving an invalid model classification; new proposal and
  semantic amendment privacy remain immutable.
  
  Bound mutation review batches to exact candidate and preservation dependencies,
  keeping complete predecessor and same-plan replacement bodies in the request.
  Avoid repeating replacement bodies in questions, retain every original evidence
  window for every candidate, and count a window only after all its groups finish.
  Oversized joint source context remains refused; quotations and hashes cannot
  replace full cited context or authorize partial learning.
  
  Allow structural correction to reconsider an unvalidated selected deletion as a
  complete rewrite only when current Memory semantic review is enabled. Bind
  complete original-source and predecessor-preservation checks to the exact final
  candidates before application; disabled, partial or stale proof cannot write.
  Preserve the rejected deletion, correction costs and all existing mutation gates.
  
  Stop the read-only Memory source collector after complete budgeted result delivery.
  Bind its independently rechecked source prefix to actual calls, results and a
  trusted abort terminal event, while retaining the failed/cancelled worker state.
  Reject partial, refused, changed or externally cancelled evidence and retain known
  usage with incomplete usage/cost flags. Collection success never authorizes Memory.
  
  Bound unknown selector schemas to one independent redecision from the original task and index. Retain rejected output and both costs without copying rejected aliases into the correction prompt or deriving phase flags from them. Final identity, index and phase checks remain mandatory.
  
  Recognize a fully validated same-batch new Memory as a deletion preservation target in both parent validators. Preserve complete semantic predecessor/replacement review and transaction checks; a declared new name alone cannot satisfy preservation.
  
  Expose parent-generated citation references for frozen source lines and long-line chunks, resolve only exact displayed positions, and retain legacy locations and quotations. Keep missing/unsupported evidence rejected and preserve snapshot binding, role, privacy, semantic and mutation checks.
  
  Keep managed Memory readbacks and mixed local-tool aggregates as complete context while rejecting their use as independent factual citations. Bind classification to actual preceding call identity and invocation paths, including relative and Windows paths; retain independent source observations and observed read failures.
  
  Allow separately verified Qwen selector workers to request their exact strict JSON Schema through an explicit capability opt-in. Preserve legacy JSON mode, caller constraints, independent phase decisions and parent range/identity/semantic gates; never treat a schema-conformant decision as learned benefit.
  
  Extend the separately enabled structured worker output to incremental Memory deltas and candidate-bound semantic amendments. Require complete envelope and non-empty supported citation forms without selecting evidence or changing parent identity, intent, privacy, semantic preservation and transaction validation.
  
  Bind strict Memory generation to the complete parent-owned eligible citation
  index/reference catalog, excluding Memory self-evidence while retaining full
  context and independent parent validation. Refuse oversized catalogs only for
  capable workers; permit source-free abstention without claiming learning.
  
  Avoid encoding a complete Memory predecessor twice in a mutation counterreview
  when the exact body already exists in the unchanged original evidence. Use a
  hashed in-state UTF-16 reference with explicit complete-reading instructions;
  retain all source evidence, preservation dependencies, wire bounds and semantic
  thresholds. Unmatched bodies and retain-only reviews remain inline.
  
  Pass the parent-indexed Memory discovery metadata to explicit maintenance source
  collection. Keep it scoped and context-only, allowing bounded reads to focus on
  actual source instead of rediscovering old Memory topics.
  
  Replace maintenance worker directory navigation with bounded parent-scoped file
  discovery and a regular-file-only reader. Preserve ordinary planner directory
  listing, explicit inventory incompleteness, secure path checks and the same
  eighteen source-read budget; path metadata never becomes factual evidence.
  
  Bind maintenance collection proof to exact current messages and tool results
  instead of repeatedly storing native SDK cumulative context. Preserve all actual
  deliveries and the unchanged proof-size, digest, terminal and authorization gates.
  
  Keep explicit-maintenance collection source-only so repeated Memory readbacks
  cannot consume its independent-source budget. Discover audit topics through
  untrusted names/descriptions; preserve complete predecessor bodies and original
  frozen task evidence in the later planner and semantic review.
  
  When a complete citation domain is supplied, constrain strict Memory generation
  to its reference IDs instead of also allowing free coordinates/quotes. Align
  initial and repair guidance with this contract. Preserve legacy parent inputs,
  complete original evidence, quote bounds and independent semantic validation.
  
  For parent-classified citation failures, repair only candidate-bound reference
  arrays instead of regenerating complete Memory bodies. Keep all other proposal
  fields and omitted candidates exact; reject body patches, stale/duplicate IDs and
  empty amendments. Full citation and independent semantic review still follow.
  
  Avoid false semantic-review capacity failures by referencing exact duplicated quotations and source entries, and packing adjacent whole-entry windows only after actual wire checks. Preserve complete evidence and all review bounds.
  
  Keep unique matching invocation provenance with uncited Memory counterevidence results even when whole-entry windows separate the call from its result. This preserves verification scope without treating arguments as outcomes or changing review bounds.
  
  Separate body-only consistency questions from full source review without changing
  Jev wire limits. Add independent, complete-body no-tool review with parent-bound
  conflict spans and the existing single correction slot; split independent bodies,
  retain per-call costs, and recheck corrected bodies and complete sources before
  application. Preserve optional-judge behavior when infrastructure cannot start.
  
  Use configured model/service capacity for normal project requests instead of an
  artificial request-byte cap. Keep optional explicit byte bounds for historical
  experiments, full evidence, count/deadline limits, semantic thresholds and retained
  failures/costs.
  
  Admit one independent selector correction for the observed current-digest positional
  alias response, preserving strict identity/index checks and the rejected attempt.
  
  Remove duplicate retained Memory corpus state from source-counterevidence requests.
  Keep every target body, complete source coverage and full mutation-preservation
  dependencies; retain actual context refusals, failed retries and their costs.
  
  Use candidate-bound amendments in the existing structural correction slot for
  citation-rejected plans containing unvalidated deletions under complete semantic
  review. Permit only parent-inventory-bound same-name delete-to-rewrite replacement;
  preserve every unaffected candidate without regenerating the full plan.
  
  Recover normal-exit empty provider tool delimiters through the existing single
  scoped structural correction, retaining the failed output and all costs without
  recovering tool actions, sharing intent or bypassing semantic validation.
  
  Split normal-project mutation counterreviews per candidate, retaining complete source/preservation context and coverage gates; derive the normal mutation call budget from at most 32 candidates and 16 windows plus support/novelty (576 prepared calls) while historical modes retain 68.
  
  Clarify that Memory organization should correct specific source-backed claims while preserving unrelated knowledge, rather than summarize all selected records.
  
  Exclude whitespace-only fragments from generated citation choices while preserving full source text and legacy valid range endpoints.
  
  Preserve digest-bound held-field feedback from completed Jev requests when another
  request fails. Permit one existing semantic correction attempt while retaining
  the original transport failure and costs; incomplete observations never authorize
  writes, subset admission or skipping full review of the corrected plan.
  
  Require explicit combined repair coverage for held proposed and retained records.
  Send parent-bound internal-consistency text-change requirements to sparse and
  combined workers, rejecting unchanged inconsistent bodies before another paid
  review while preserving support-only same-text citation correction.
  
  Provide exact parent-bound old Memory bodies as untrusted maintenance questions
  for current-source collection, without treating readbacks as observed facts or
  expanding the collector's tools. Bind safe complete entry revisions before writes
  and keep source-only checks after application so legitimate corrections survive.
  
  Extend candidate-bound semantic amendments to mixed proposed/retained correction.
  Parent-owned proposal kinds and privacy cannot be regenerated into a different
  list; retained operations have their own exact scope. Constrain opted-in workers
  to the complete eligible candidate-ID enum and reject incomplete or malformed
  identity domains without changing legacy provider defaults or semantic gates.
  
  Do not force Memory body changes from uncertain coherence preferences. Require
  an explicit contradiction at the existing probability/confidence thresholds;
  keep uncertain fields held and preserve full revalidation and mutation gates.
  
  Include independent Memory body reviewers in explicitly opted-in structured
  output. Require one judgment per complete parent-bound slot while retaining
  legacy response validation, exact contradiction witnesses and all source gates.
  
  Recognize the exact literal command-family grammar with leading ASCII whitespace
  and command-ending separators. Keep matching proof separate from authorization,
  and distinguish newlines between command words from newlines after the command.
  Clarify the subject of learned API type contracts and independent descriptions.
  
  Separate command-family permission changes from factual explanation conflicts in
  each complete counterevidence window. Require both existing semantic gates before
  application; preserve all evidence, authorization checks and uncertain proposals.
  
  Review independently retrieved Memory descriptions against their complete records.
  Do not treat missing description witnesses in a whole-record hold as field approval;
  allow the existing single correction to reconsider both knowledge fields before
  fresh complete review. Prefer existing supported sentences over lossy index summaries.
  
  Preserve exact inspected API declarations when their syntax is the learned
  contract, avoiding duplicated prose that changes the contract's subject.
  
  
  Add an optional parent-materialized source-excerpt representation for new private
  project Memory. Bind it to an original successful read, exact evidence and current
  regular source-file bytes; retain all ordinary validation and complete semantic
  review, with source identity and byte checks around application and rollback.
  
  
  Allow an explicit generation-only planner thinking level, preserving model defaults
  when absent and independent complete-record review settings. Refuse invalid or
  unsafe configuration and verify the distinct levels through the actual Pi CLI.
  
  Repair feedback now retains independent body and description failures from complete semantic review. Eligible quoted descriptions can produce a narrower new proposal using only their exact bound checklist; a corrected proposal needs its own fresh review. One deterministic narrowing still requires full plan, body, source and semantic validation. Historical real descriptions with held checks remain rejected.
  
  Clarify source chronology and partial failed-command observations in Memory review: later applied source text does not establish runtime success, and earlier absent declarations do not alone contradict a later addition. Later reverts, failed edits and original full-window gates still apply.
  
  Allow new private project Memory source excerpts from complete added lines of a successful original edit, bound to its invocation newText and unchanged current regular source file. Original marked evidence, privacy and all semantic/write gates remain mandatory; attempted edits, removals, partial-line coordinates and stale source are rejected.
  
  Preserve complete project Memory contracts when semantic body review remains held; deterministic description-only narrowing is limited to preferences.
  
  Allow explicitly bounded Jev review concurrency for service backpressure while preserving full checks, request bounds and deadlines.
  
  Align semantic amendment output with parent document validation by requiring complete frontmatter and body when content is supplied.
  
  Bound semantic Memory repair workers to a recorded worker budget (600 seconds,
  ADR 0009), retain lifecycle/partial costs, and reconcile interrupted study costs
  without double-counting receipt copies or treating unknown calls as free.
  
  Make semantic amendment producer patterns consume the complete Markdown value,
  including its body, while preserving standard frontmatter search validation and
  all parent intent, citation and semantic checks.
  
  Persist single-task replay ranges with parent source bindings across crash recovery,
  and request relevant Memory reads before related implementation while keeping
  index-only discovery and current-evidence validation.
  
  Retain bounded literal source identifiers in excerpt descriptions for discovery,
  and clarify automatic learning ownership without expanding ordinary task write scope.
  
  Recover only lossless quoted JSON whitespace in a unique bounded Memory repair
  response, retaining its original output and conversion evidence before all parent
  identity, citation, intent and semantic checks.
  
  Move the shared declaration-knowledge precision contract ahead of untrusted generation and semantic-repair evidence; distinguish callable, parameter-return and invocation-result subjects without adding project facts or weakening review.
  
  Add an isolated Node HTTPS semantic-study transport that keeps the original hostname and certificate checks while routing through a verified lookup address, with one-attempt accounting, fixed TLS codes, unchanged deadlines and real local TLS positive/negative coverage. Production SDK transport is unchanged.
  
  Close experiment admission atomically and wait for all counted forwarders, including late usage, before releasing a reservation; unconfirmed termination remains reserved and cost-unknown.
  
  Reject whitespace and frontmatter-only new or rewritten Memory before semantic review in TypeScript and Python, and require non-empty bodies in opt-in producer schemas. Existing records and plain-body compatibility are preserved; a description never becomes knowledge automatically.
  
  Recover literal newline and tab serialization in initial Memory generation using the same bounded, lossless path as corrections. Preserve mutation intent and conversion hashes; keep all parent and semantic gates.
  
  Preserve explicitly successful native retries when recovering final Memory JSON string whitespace, keeping all failed responses and parent gates. Share the complete citation catalog through local schema references without changing any expanded constraint.
  
  Keep failure-derived knowledge and descriptions within the observed public contract instead of turning one missing-member check into a universal requirement for runtime properties.
  
  Review large Memory selector inputs in complete ordered record windows, preserving
  final revocations and requiring every window to finish confidently before routing.
  Routing unions only nominate full downstream review; privacy, mutation authority,
  semantic thresholds and unknown cost accounting remain unchanged.
  
  Record fixed TCP/TLS/response progress for isolated semantic-study failures,
  without response content, credentials, relaxed TLS, new retries or changed deadlines.
  
  Bind complete semantic checklists after an existing bounded connection retry
  succeeds: count successful logical requests separately from failed attempts.
  Keep all failed attempts and costs; require every original window, exact answer
  and source binding before the independent Memory body review can run.
  
  Rejected Harness initial/repair extraction now retains a private, run-bound transport artifact with a fixed parent error category. Encoded sensitive output stays hash-only. This closes a real diagnostic-loss gap; it does not recover the prior missing output, approve rejected plans, add retries, or demonstrate learning benefit.
  
  Memory mutation counterreview now considers the same original source chronology as creation review: verified successor source can supersede an earlier observation of the same subject. Reverts, failed edits, user permission, complete predecessor preservation and the original semantic gates remain intact. This corrects inconsistent review instructions, without admitting historical held plans or claiming downstream benefit.
  
  Memory rewrite/retention description counterreview now checks the short index claim independently instead of asking it to preserve the complete predecessor record. Full-body preservation and every original evidence window remain mandatory; inaccurate or condition-dropping descriptions still hold the whole plan. Historical held plans remain held.
  
  Memory retention windows can compare earlier source observations with exact, independently collected current source entries named by the retained record. The parent binds the observations and complete snapshot by hash and rechecks source revisions; source-path matching nominates comparison context only. All original windows, final revocations, independent semantic checks and thresholds remain required. Unbound audit labels, changed evidence, missing invocation provenance and failed reads cannot supply this context.
  
  Automatic learning now refreshes scoped current source after observed successful project edits, before Memory selection and generation. Original reads and patches remain intact; the collector receives source paths only, and current source revisions stay bound through semantic review and writes.
  
  Failure backfill now binds a prior source-extended review to its unchanged original task prefix, complete snapshot, parent manifest and original collector receipt/read log. Missing or ambiguous provenance remains rejected; old source observations do not become fresh learning evidence.
  
  Normal unbounded Memory review now supplies complete values inline instead of requiring semantic judgments to dereference body pointers or UTF-16 substrings. Explicitly byte-bounded historical studies keep their exact encoding; all source, preservation, privacy and semantic gates remain.
  
  Semantic Memory repair instructions now consistently require the complete parent-bound amendment envelope. Candidate patch restrictions no longer imply omitting kind/version or run identity; incomplete and foreign envelopes remain rejected without an extra repair attempt.
  
  Candidate-bound Memory patch generation avoids extra reasoning only for known description-only changes after complete bodies passed independent consistency review. Source, permission and preservation body holds, retained-record correction, unknown held fields and inconsistent bodies retain high reasoning. Fresh independent and full semantic validation, exact identity and the original worker deadline remain required.
  
  Reject a semantic amendment that reconstructs the unchanged rejected proposal after source materialization, citation resolution and protected-field restoration. Keep its output, usage and unresolved status without paying for the same review again. Effective source and citation changes still require full validation.
  
  Retain optional parent-observed origin bindings in applied private Memory history,
  with exact run artifacts, receipt creation sets and file revisions. Preserve
  unavailable origins and legacy data without changing mutation or undo authority.
  This metadata is not yet supplied to model context or semantic review.
  
  Normal unbounded Memory rewrites and deletions now receive parent-bound current-source comparison in every counterevidence window, using predecessor and replacement paths only as retrieval hints. Complete original windows, support, preservation, privacy and thresholds remain required; bounded historical wire encoding stays unchanged.
  
  Memory generation and semantic repair now distinguish observed source comments from verified behavior, compare them with current user requirements, and preserve supported unresolved documentation conflicts. Quotation and source-excerpt copying do not supply correctness; atomic submission, evidence and semantic gates remain unchanged.
  
  Normal source comparison now includes explicit original invocation/result order for uniquely paired successful same-path reads, including new project knowledge. Semantic correction generation receives the same validated index links alongside its unchanged complete original evidence, without duplicate source bodies. Invalid bindings stop before a model request. Existing Memory remains a correction target rather than source authority. This provenance does not decide supersession or truth; original source, privacy, complete-window and semantic gates remain unchanged, as does explicitly bounded historical wire encoding. The real V50 stale-declaration repair remains rejected; delivery of source order does not establish improved generation or learning.
  
  Review explicit durable corrections to still-owned Harness rules before task execution, retaining the existing semantic/fixture/transaction gates and a total 230-second bound. Prevent ordinary complete writes from silently changing owned declarations or markers; preserve explicit previewed authoring.
  
  Canonicalize selected Memory source-hash identity so mirror normalization cannot reject unchanged files solely because directory traversal order changes. Preserve exact file-content and frozen-dossier binding checks.
  
  Request the configured Jev service's supported long context for normal complete reviews, with an explicit opt-out. Preserve finite historical study modes, complete evidence, existing thresholds and deadlines; carry the fixed header through isolated study transports without changing TLS or retry behavior.
  
  Explain recognized literal Harness selector grammar for both sides of a correction,
  without dropping raw rules, entering new-rule authorization shortcuts or changing
  historical bounded requests. Keep uncertain judgments held. Give combined Memory
  repair workers an explicit retained-record operation contract distinguishing
  `rewrite`/`delete` operations from `project`/`preference` Memory types; malformed
  operations remain rejected. Real rejected responses and complete frozen source
  are regression evidence only, never seeded knowledge or learning-benefit proof.
  
  Keep automatic current-source collection usable after an edited file is renamed:
  retain unavailable edit hints as discovery metadata, grant them no exact read
  scope, and verify the remaining current sources. Missing-only sets, sensitive
  paths, symlinks and scope violations still fail; missing hints provide no facts
  or absence claims. Retain the original failed collection and its costs.
  
  Align normal Memory counterevidence choices with the question's complete source
  chronology. Only later verified observations of the same source subject and exact
  text can resolve earlier source differences; unresolved conflicts, later reverts,
  permission exceptions and preservation issues remain held. Keep every original
  entry, unchanged thresholds and finite historical/Harness criteria. Retain the
  actual old wire separately from offline legacy-criteria reconstruction.
  
  Give normal rewrite/retain description counter judgments criteria for the
  description's own claims and necessary conditions. Do not independently judge
  whole-operation knowledge preservation in that field. Keep the complete body
  preservation and authorization gates, all evidence, uncertain holds, probability
  thresholds and bounded historical request encoding unchanged. This corrects
  judgment scope; historical low-confidence causes and learning benefit remain
  unestablished.
  
  Keep normal retained-only counter criteria about actual corrections, revocations
  and observed source changes, matching the existing no-mutation review contract.
  Missing repetition or new citations alone neither contradicts nor verifies old
  knowledge. Preserve every original entry, independent body/description checks,
  uncertain holds and finite historical encoding; retention grants no write authority.
  
  Scope normal new-Memory counter criteria to each new record's claims and necessary
  conditions, with independent description criteria. Keep other operations' full
  predecessor/dependency preservation checks and atomic whole-plan admission intact.
  Explicit operation identity takes precedence over kind labels; finite historical
  wire and all original semantic thresholds remain unchanged.
  
  Align combined Memory repair examples with mandatory proposal and retained-record
  coverage. Preserve an explicit empty refusal on both sides, reject partial wire
  shapes, and keep all parent identity, privacy, source and semantic checks. Missing
  retained corrections stay unresolved rather than being reported as identity drift.
  
  Revisit actually read indexed Memory before automatic early screening, including
  when semantic phase selection is disabled and the task has no learning keywords.
  Keep current-source collection, disabled settings, exact command scope and all
  semantic and parent mutation gates. Native loopback proof establishes correction
  routing and validated writes only, not downstream learning benefit.
  
  Pin fresh continuous-study runtimes to the requested Pi 1.2.0 CLI/TUI baseline,
  including inherited workspace overrides. Check actual CLI startup before model
  transport, retain rejected-version containers and full source bindings, and keep
  historical Pi 1.0 cohorts separate.
  
  Keep normal CREATE-only Memory counterevidence state free of unrelated predecessor
  preservation obligations in mixed plans. Preserve complete original evidence and
  source context, separate rewrite/delete preservation checks, atomic approval and
  all semantic thresholds. Keep explicitly bounded historical encoding unchanged.
  
  Allow changed semantic Memory content patches to retain the exact candidate's
  original citations when the complete frozen snapshot and held fields are bound.
  Revalidate all original sources, preserve locked metadata and record provenance.
  Keep missing identity, explicit invalid evidence, unchanged effective content and
  citation-only omissions rejected. Require fresh complete semantic and mutation
  validation; source reuse does not approve learning or add a repair attempt.
  
  Preserve a separate held-review gate after saving Memory proposals. Semantically held records and partially applied subsets with pending review cannot start dependent Harness or AGENTS planners. Keep proposal outcomes, independent writes and every reported cost. Fully reviewed repairs and intentional validated propose policies still continue. Recheck run ownership before changing the gate after asynchronous work.
  
  Allow an explicitly enabled semantic correction candidate to select exact current
  audited source text instead of regenerating a quoted contract. Require full parent
  identity, explicit citations, audit membership and current regular-file hashes.
  Keep locked metadata, predecessor preservation and every fresh semantic gate;
  extraction grants no approval and adds no correction attempt.
  
  
  Let semantic Memory corrections select exact short parent-bound candidate
  references. Capture and recheck the full proposal digest and reference map;
  retain full snapshot identity, strict legacy IDs and all fresh semantic gates.
  Keep malformed historical responses rejected and add no correction attempt.
  
  Retain the exact original snapshot and selector dossier read grants for normal
  Harness repairs, as for missing-output recovery. Do not grant an agent-directory
  root or change source binding, correction budgets or semantic thresholds.
  
  Support Pi 1.2 retry logs in exact failed-task replay when a context edit removes
  only an empty assistant error. Sanitize removed metadata, preserve evidence
  indexes and source/task digests, and refuse all meaningful redactions. Keep the
  original failure and costs. Resolve workspace CLI and extension peers to Pi 1.2.0
  and narrow user-prompt access for custom-start events.
  
  Name the native read tool in relevant Memory guidance so ordinary knowledge
  consultation uses the same interface as correction nomination. Keep current-user
  exceptions, task scope and all evidence gates. Shell output remains uncredited.
  
  Separate normal unbounded Memory mutation evidence and preservation questions.
  Require both primitive 0.9/0.8 gates and a parent-computed conservative conjunction
  score lower bound of 0.9. Keep all original windows, complete predecessor and
  replacement bodies, separate description checks, exact answer coverage and atomic
  admission. Missing preservation answers stay invalid. Historical bounded wires
  remain unchanged; this protocol change does not establish learning benefit.
  
  Supply parent-computed literal source quote comparisons in normal unbounded Memory
  rewrite/delete review. Bind each quote to a unique successful same-path read and
  compare individual original text blocks. Scope facts to the reviewed candidates;
  retain complete source/knowledge/windows and every semantic threshold. Exact
  matches never grant approval. Preserve finite historical request encoding.
  
  Show exact unmatched predecessor and replacement line occurrences during normal Memory rewrite review. Preserve complete records, source review, semantic preservation gates and historical bounded transport. Text equality does not authorize mutation.
  
  Separate Memory factual compatibility from user permission and require both with complete predecessor preservation. Retain the 0.9/0.8 primitive gates and a conservative three-way score bound of 0.9. Preserve revoked user preferences even when writes are permitted. Fix bounded repair-field routing for held preservation checks and keep each held dimension in diagnostic feedback.
  
  Keep complete original user scope in every normal Memory rewrite/delete support and counter request. Preserve exact original entries, indexes, temporary restrictions and revocations; exclude quoted roles and reject conflicting wrappers. Keep citations, complete windows, historical transport and semantic gates unchanged.
  
  Copy original user context once and reject post-await changes to evidence, predecessor records or candidates. Retain known service usage without returning complete or partial review proof for changed inputs.
  
  Offer optional source-cited current-versus-earlier clarification in the existing semantic Memory repair. Require actual paired original observations and compatible task scope. Do not infer history, dates, releases, runtime success or Memory purpose. Preserve privacy, revocations, material conditions and every fresh review gate without adding attempts.
  
  Retain optional parent-bound Memory origin in private mutation history. Add a read-only interface that returns complete historical tasks only through a unique revision chain to creation. Refuse incomplete, changed, ambiguous, oversized or cancelled reads, and recheck captured records and artifacts before reuse. Keep legacy records unbound and undo based on bytes and mode. Supply complete historical tasks to normal Memory review and semantic repair only with explicit private authorization and full sensitive screening. Keep history separate from current source, citations and authority. Bind it across asynchronous work, admit only the exact parent pending transaction during writes, and publish subset audits after origin guards settle. Preserve all semantic gates and finite historical wire encoding.
  
  Keep Memory file revisions unchanged for exact rewrites with the same secure mode. Preserve transaction checks and report operation counts from actual content, presence or mode changes. This keeps complete historical origin usable across no-op consolidation without claiming a knowledge correction.
  
  Make semantic Memory correction distinguish source-backed changes, citation gaps and unsupported corrections before generating an amendment. Keep empty amendments failed. Copy exact original frontmatter into repair examples, including absent fields and locked descriptions. Use the selected record header when reconsidering an unvalidated deletion. Preserve all identity, citation, privacy and semantic checks.
  
  Pin the isolated Pi 1.2 runtime dependencies, including agent core, code mode, MCP and telemetry, to 1.2.0. Keep fresh dependency resolution separate from historical study images.
  
  Correct the Memory generation guidance that conflated declared roles with runtime object inequality. Require evidence for identity claims and prevent uncited reviewer cautions from becoming learned facts. Keep predecessor knowledge and all review gates.
  
  Reject semantic responses that do not match an explicitly pinned Jev model version. Keep actual response usage and known model prices; retain moving alias behavior. Add the published Jev 1.14 input-price estimate without changing confidence or mutation gates.
  
  Bind Memory relationship checks, partial review feedback, description correction and independent partition checks to the parent-requested Jev model. Preserve the legacy 1.13 contract for injected judges without a model binding. Keep complete evidence, protected fields, privacy, thresholds and fresh post-correction review.
  
  Keep the original rejected Memory plan in the existing run-bound structural rejection artifact before correction can replace it. Use the existing sensitive-output guard to retain hashes only for sensitive output. Keep rejection outcomes, usage and all validation gates.
  
  Record non-context Harness decision and native completion observations with exact canonical rule revisions and hashed call/rule identities. Preserve incomplete and ambiguous evidence as unverified. Keep observer failures outside execution policy and reject late confirmation across session changes. Handler invocation does not establish task success or learning benefit.
  
  Distinguish complete raw Memory snapshots from truncated metadata. Record hash-only section preparation and native full-body result observations only after a unique retained result matches the complete revision through the current branch. Keep model attention, source truth and task benefit unverified; do not add body injection, source reads or mutation authority.
  
  Let retained Memory corrections add original-source evidence without retyping unchanged knowledge. Copy exact parent-frozen Markdown only for an omitted body under complete identity and source bindings. Reject empty bodies, changed repair context and unchanged text that requires correction. Preserve complete semantic review and failed learning outcomes.
  
  Clarify the outer and inner return annotations of a function that returns a callable. Keep the exact observed declaration, declared members and invocation result distinct. A function-typed input parameter keeps its callable type separate from its call-signature return annotation. Retain the rejected real proposals and all source, consistency and correction checks.
  
  Name the Memory maintenance actors in the fixed retrieval protocol. The user enters maintenance commands; the parent owns automatic maintenance. Indexed reads do not authorize configuration discovery or agent launches. Keep separately authorized diagnostics possible, and retain all privacy, source and mutation checks.
  
  Keep independently observed failure conditions when the cause remains unknown. Separate missing causal evidence from established source state. Require useful failure observations to retain supported applicability and the new evidence needed for later review, without creating permanent instructions or task logs. Retain rejected real drafts, unresolved corrections, costs and all semantic gates.
  
  Keep support diagnostics separate from full Memory approval. Capture the current production question with isolated configuration and blind case labels. Require an accounting owner proxy for real requests; keep one SDK call per case, reject redirects, and retain numeric answers, usage, partial rows and unknown costs. Authored examples grant no threshold change or learning claim.
  
  Generate each supported Memory fact once. Keep complete declarations, independent named-type requirements, known failure conditions and necessary source scope. Avoid duplicate interpretations and incidental inventories without imposing a length limit or shortening correct stored records. Preserve all semantic gates and historical failures.
  
  Require a separate evidence-bound Memory coverage account and independent whole-plan, record and named-omission judgments in the parent. Review empty plans, bind exact records and original references, and preserve the existing source-blind consistency check. Reject source observations and removed records as storage witnesses. Combine new judgments with the original probability, confidence and conservative joint gates before mutation.
  
  Allow the existing bounded correction slot to fix a coverage-only body omission. Keep rejected-version questions, full fresh review and protected identity. Save each actual semantic decision and its exact plan binding separately. A complete-plan proof cannot authorize a changed subset. Preserve historical bounded protocols and hold any subset without its own complete obligation proof.
  
  Retain coverage-worker costs after parent interruption. Own retained-record judgment costs before another source check or artifact write, keep cancelled runs separate and count actual invocations once. Preserve all failures and unknown costs. Controlled and native Pi checks establish these mechanisms only; real-model learning and later task benefit remain unverified.
  
  Keep a complete rejected coverage account invalid while allowing the original
  independent source and body checks to diagnose a genuine draft error. Use only the
  existing single plan repair when those checks hold the knowledge. Require fresh
  complete reviews before writing. A rejected account alone cannot retry or write.
  Keep unsafe, incomplete, cancelled, unavailable and unsaved output blocked.
  Clarify the Memory-only coverage scope and existing cross-field output rules.
  
  Preserve complete rejected coverage questions and version-specific draft bodies
  for failed-task backfill. Bind every artifact and original answer distribution
  to its original receipt. Keep these historical diagnostics separate from fresh
  source and require all current reviews before mutation.
  
  Keep diagnostic labels separate from executed operations during Memory
  generation and correction. Limit simplified traces to their observed scope and
  preserve relevant original setup order and unreleased work. Retain the actual
  rejected plans; this guidance change does not establish learning benefit.
  
  Retain each learning receipt by batch before updating the latest-result view.
  Keep cancellation in the same canonical batch record. Preserve earlier command,
  backfill and policy receipts and all known or unknown usage. Deduplicate only
  identical receipt views. This fixes observed receipt loss during native backfill;
  it does not establish that later tasks improve.
  
  Compare confirmed retained-Memory text corrections with a copied frozen
  predecessor when the record is absent from the original delta. Reject unchanged
  required bodies, including description-only patches, before full re-review.
  Keep uncertain evidence-only and valid description-only corrections available.
  Shorten duplicate repair guidance and replace the blanket explanation ban with
  the existing source constraints. State supported dependency relations in the
  body rather than relying on descriptions or citations. All semantic thresholds
  and final review remain unchanged; no real learning benefit is established.
  
  Keep Harness authoring preview available across follow-up turns, while session
  and branch changes clear the request. Scope preview and predecessor checks to
  the exact target; ordinary source writes and other targets retain their normal
  checks. Deduplicate unchanged text-guidance events while delivering each
  matching run-start section and preserving skill delivery metadata. Exclude only
  identified configuration operations from matching; ordinary text and mixed
  commands remain eligible even when they mention a rule ID or config path.
  
  Bind corrected body sections and their original references as atomic knowledge units.
  Use separate parent-labelled body positions for coverage witnesses, and enforce the
  knowledge-body boundary after frontmatter so descriptions cannot cover absent body facts.
  Keep exact body offsets and choose valid body positions in format examples. Enforce the
  initial paired source-task boundary before native tools execute. Keep all semantic
  thresholds and retain rejected plans and usage. These changes do not establish a
  learning benefit.
  Retain the existing shared knowledge output contract once when atomic correction
  replaces the output framing. Remove duplicate content instructions from that
  framing without dropping its source, identity or permission rules.
  
  Use one bounded source catalog for semantic body corrections so the citation
  limit applies to the complete candidate. Keep body witness and original source
  reference domains separate, and report citation failures without claiming an
  identity change. Preserve all original review thresholds and failed attempts.
  
  Reject line-ending and boundary-whitespace changes as required body corrections.
  Recognize leading BOMs when separating metadata from knowledge, so description-only
  edits of a BOM record cannot satisfy a required body correction.
  Keep returned Markdown and internal formatting unchanged during comparison.
  Materialize admitted description-only patches with their explicit source evidence
  while preserving the original body bytes and every complete review gate.
  
  Extend the existing explicit JSON syntax opt-in to documented DeepSeek models,
  the current gateway alias and exact gpt-6.1-sol no-tool workers on Responses.
  Preserve caller output formats and use Responses text.format for JSON objects.
  Keep Qwen strict-schema support separate. Record Responses system discovery,
  reasoning and output-format metadata without storing prompt text. Preserve all
  semantic gates and reject incomplete outputs without extra retries.
  
  Retain the existing source-order guidance when atomic Memory correction replaces
  the output format. Keep the complete bound observations and all review gates.
  
  Include native Harness decision and handler-result records in the learning
  summary. Keep exact rule revisions, bounded omissions and unknown outcomes.
  Rule execution does not establish task success or learning benefit.
  
  Derive the necessary facts and conditions within each Memory record's scope
  from original evidence before matching its body. Keep optional nominations
  optional, retain every actual claim in review, and preserve all independent
  judgments. This review-order change does not establish better learning.
  
  Clarify state relations in existing Memory generation and coverage guidance. For relational API knowledge, connect a source-established factory or call site to the named return type and relevant declared member. Do not expand unrelated definitions or hardcode project answers. A retained public record omitted this direct declaration bridge; its original negative runtime claim remains correct, and the omission does not establish the cause of historical scores. Real learning improvement remains unverified.
  
  Keep initial incremental Memory generation on its complete parent-reference
  template and knowledge contract. Remove the appended legacy quote-index and
  semantic-repair guidance from that entry point; maintenance and correction keep
  their existing guidance. Source evidence, namespace and replay isolation, output
  bounds and all review gates remain unchanged. This phase simplification does not
  establish why a historical model omitted a relationship or improve its verdict.
  
  Pass parent-collected source bindings into the existing initial and structural
  Memory excerpt materialization paths. Fresh audited reads now have the same
  required snapshot, call, source-hash and private-storage checks as their existing
  semantic-repair counterpart. Keep ordinary read/edit excerpts and all review
  gates unchanged. This restores exact source copying, not omitted knowledge.
  New project entries use ordered knowledge units combining parent-copied source selections with
  ordered explanatory units using the existing knowledge citation catalog. Derive
  the complete body and evidence together; retain exact source checks, body limits
  and all later semantic gates. Ordinary content, standalone excerpts and existing
  correction formats stay compatible. Exact copying does not establish complete
  knowledge relations or later task benefit.
  Keep the original safe/private classification and all sharing gates; source
  copying does not grant public permission. User-stated project facts may use only
  cited text units. Standalone source excerpts remain private-only.
  
  Pass the existing parent-bound unchanged-knowledge coverage restriction to the repair worker. Qualify citation-only guidance when that restriction is active, and permit an evidence-supported knowledge correction or empty refusal. Preserve citation-only corrections on other paths and all validation gates. This feedback repair does not resolve low semantic certainty or establish learning benefit.
  
  Retain actual manual Memory command phase provenance through frozen review
  snapshots, separately from original task evidence. Reject citation-only redraws
  of a coverage-only hold on unchanged knowledge. Also preserve an independently
  held coverage question when source or counterevidence is held: citation-only
  corrections cannot obtain another coverage draw for the same knowledge. Validate
  the complete bound question set and its actual positive probabilities. Evidence-only
  correction remains available when coverage itself passed; changed knowledge still
  requires every fresh review gate. This conservative rule may reject citation-only
  repairs that previously reached another review. These fixes do not
  establish accepted learning or subsequent task benefit.
  
  Align normal counterevidence answer criteria with their transmitted indexed
  window and supplied context. Preserve all original windows, independent global
  coverage and approval thresholds; bounded historical wires remain unchanged.
  
  Retain safe worker failure categories and native exit status in Memory review
  diagnostics. Keep provider error text private, failed output unusable and
  incomplete usage unknown. No retries or semantic gates change.
  
  Preserve the typed cause of initial knowledge-catalog citation failures and use
  the existing citation-only structural slot. Replace only its same-length source
  catalog while retaining ordered body units and metadata; current source and all
  semantic gates still follow. Align the generic structural project example with
  the existing knowledge producer format. Keep the 2000-character bound, failed
  proposals and all correction costs; this repair does not prove learning benefit.
  
  Replace the incremental generator's preference for one minimal failure pitfall
  with complete evidenced relationships and their applicability conditions. Keep
  unrelated inventories out, retain local corrections to existing records, and
  clarify preference prose versus project knowledge output. This prospective
  selection policy changes no validation gate or call count and does not establish
  the cause of historical omissions or learning benefit.
  
  Pass parent-generated source-catalog positions and validation categories to the
  existing citation correction worker. Keep unexpected error text private. This
  repairs feedback lost between a typed citation error and the worker input; it
  does not select replacement sources, change bounds, retry a held plan or prove
  that a model corrects the cited knowledge.
  
  Enforce the existing project-knowledge output contract at the fresh incremental
  producer boundary, independently of provider schema support. Reuse the existing
  single structural correction; legacy reads, preferences and retained corrections
  keep their existing formats. Retain the bound parsed initial candidate with
  hash-only handling for sensitive output, without reasoning or full transport.
  This prevents a generation-format bypass and distinguishes selection from
  materialization; it does not prove complete extraction or learning benefit.
  
  Expose a bounded, generation-only view of observed declaration syntax beside
  unchanged original evidence. Direct outer return annotations can identify a
  unique type candidate within the observed region and its direct member spans;
  callbacks, imports, merged declarations and shadowed type parameters do not
  supply guessed bindings. Keep all original references and citation bounds. The
  view neither generates stored knowledge nor establishes complete extraction,
  semantic approval, runtime behavior or improved later tasks.
  
  Change the representation of new project knowledge to retain complete observed
  function declarations already selected and used by a text unit's citations.
  Preserve explicit units and references, avoid duplicate source blocks, and count
  the added observed-source blocks toward the existing limits before full review.
  This adds declaration context, including parameter types, to the proposed body;
  it is a prospective representation policy, not a claim that the previous
  materializer lost explicit units. Do not infer current truth or runtime behavior,
  change existing-entry correction contracts, or rejudge historical held plans.
  Keep the original privacy, source and semantic gates and all failures and costs.
  
  Constrain fresh source-unit generation with a parent-derived file-reference domain
  and an explicit reference paired with the model-selected citation index. Verify
  the pair before the unchanged current-file resolver. Keep terminal observations
  as ordinary text evidence, and retain the same frozen domain in the existing
  single structural correction. Do not infer file authority, convert terminal
  results, repair source indexes or change legacy and semantic-correction formats.
  Before source materialization, let the model update both paired references in
  that same correction; keep materialized citation-only correction unchanged.
  
  Validate source-derived role closure before reviewing newly generated project API
  knowledge. An observed export map and selected local wrapper/call context must
  prove one factory, named return owner and direct member. Send missing roles to
  the existing single structural correction and retain the parent obligation across
  that rejected draft's correction, until complete materialization. Require explicit model-selected citations before preserving
  neutral observed relationships in the body. Keep the original user's explicit
  same-sentence topic constraint, while allowing related statements across sentences
  within one used source-cited knowledge unit. Do not combine separate units or
  descriptions. Do not resolve imports, infer runtime
  truth, add unselected references, change semantic thresholds or rejudge old plans.
  Native and local checks do not establish extraction quality or later task benefit.
  
  Preserve explicit proxy transport in the initial Memory planner without
  inheriting unrelated credentials or arbitrary Node startup code. Verify Harness
  scoped delivery across native Pi reload, skill invocation and Bash results;
  require every authored revision in live acceptance and run native tests in CI.
- ff9b7ff: Keep learning management lists and document readers usable in narrow terminals, preserve navigation and explain effective automatic policies. Report partial failures and semantic lifecycle colors accurately, start Harness requests with compact procedure rows, and retain complete diagnostics and readable history summaries. Fix model-search letters, width bounds, selected-model inspection and live resize.
  
  Preserve logical reading position across reflow, prioritize history targets, keep model hints readable, default rule readers to Close, and retain nested settings navigation with separate policy help. Remove redundant learning event labels.
  
  Deduplicate mirrored history targets and bound their summaries so applied and undone results remain visible in 48-column terminals.
  
  Group new learning history by exact parent-owned pipeline identity, distinguish index setup, preserve legacy history and per-change undo, and harden live acceptance isolation and immutable per-run evidence.
  
  Keep ordinary task writes out of reference Memory, align Memory and Harness tool path resolution, and preserve validated evidence on existing-memory updates. Apply the same citation gate to initial and repaired plans, including frozen repair evidence with Jev disabled. Add real-model paired downstream task evaluation with explicit failures, harms and independent task-artifact scores.
  
  Expose empty scoped Memory discovery explicitly and direct retrieval to supplied roots and indexes instead of guessed locations.
  
  Authorize only the exact parent-supplied AGENTS dossier alongside the frozen snapshot, preventing required evidence reads from being refused outside the project. Preserve failure categories in receipts without copying worker text or labeling successful attempts as failed. Add explicit real-Pi reliability probes and a Jev-enabled paired complex-feature study on pinned public projects, with hidden behavioral checks, upstream-check integrity and hard training gates.
  
  Transport large shared-worker prompts through a pipe into the Node CLI's in-memory arguments, avoiding operating-system argument limits while preserving exact text, boundary whitespace, cancellation and bounded output. Cover actual Pi input capture as well as child pipe failures.
  
  Preserve complete longer task traces within the existing 512 KB evidence budget
  (up to 256 entries), prioritize user/tool evidence and tool-call provenance over
  plain assistant narration, and retain proposals-only safety when primary evidence
  is omitted. Initialize incremental receipt source metadata and distinguish omitted
  assistant context from missing evidence in result details.
  
  Account for bounded question batches in every Jev evidence-review window, rather
  than refusing complete real-source reviews at an aggregate twelve-request cap.
  Preserve wire limits, concurrency, complete counterevidence and description
  checks, thresholds, and fail-closed behavior; expose the increased cost bound.
  
  Use the existing bounded correction slot for unambiguous malformed incremental
  JSON on empty scope. Keep regenerated records private and retain citation, frozen
  evidence, identity and semantic gates; preserve multiple-plan rejection.
  
  Keep complete counterevidence windows within actual request bounds instead of
  merging raw entries without support and escaping overhead. Reference exact
  colocated cited entries once, retain at most sixteen windows and 68 logical
  requests (136 with the existing retry), preserving full evidence and wire limits.
  
  Label Memory planner and repair evidence with explicit original snapshot indexes,
  without modifying raw snapshots or relaxing role, quote, privacy or Jev checks.
  
  Add bounded complete Memory retrieval with revision records and correction scope,
  reviewed replacement/retirement of owned automatic Harness rules, and source-verified
  learning backfill with shared leases, individual acknowledgments and attempt/cost
  ledgers. Retain interrupted learning receipts without overwriting current results.
  Add an explicit real-project longitudinal comparison protocol with failures,
  unchanged-source checks and separately reported unknown costs.
- 2bba220: Preserve multiline goal results, preserve Markdown blank lines, and omit the redundant Goal prefix consistently in error rows. Token-capped goals now recommend clearing and starting a new goal rather than an unusable resume. Repair native terminal acceptance to decode complete repaint frames with a finite scripted provider, and document every TUI trigger.
  
  Treat explicitly provided revision fields as decisions even when empty: an empty objective is rejected, and an empty revision still obeys decision exclusivity. Clarify that reason and completion_summary alone do not record an update.
  
  Show settled Goal subjects and bodies in full with width-aware wrapping, preserve complete requirements in TUI while paging long model reads with content-bound cursors, unify summary and objective reads, constrain updates to mutually exclusive operations, and distinguish rejected updates from goal failure. Keep legacy blocked calls compatible, simplify final-refusal headlines, and reuse passive status widgets for repaint. Add opt-in fullSummary to pi-kit without changing existing consumers.
- e86a44f: Accept a pre-styled detail block in a lifecycle band. A `details` entry that is
  a string array keeps its host escapes, receives no text color, and still wraps,
  fits and bands each row, so a caller can place highlighted code inside a band.
  String entries keep the existing sanitize and color behavior.
  
  Add the field-name vocabulary `labelField` and `labelFieldVerbatim`. They read
  `Label: value` on one line. `labelField` collapses whitespace like `fieldLine`,
  and `labelFieldVerbatim` keeps the value's own spacing for a command, a regex
  or a payload. `fieldLine` keeps the `label · value` vocabulary, so no existing
  row changes.
- 6416992: Omit the separator when a lifecycle row has no subject.
  
  A row renders `[tool] label · subject`, and the separator was part of the label, so a caller with no subject to name produced `[agent] listed · ` — a `·` advertising text nobody wrote. The head now stands alone in that case, exactly as it already did for a block subject with nothing authored, and `formatToolLifecycleTitle` follows the same rule.
- fc0d801: Sum completed model requests in worker-run usage, retain a separate known-usage ledger for incomplete runs, and preserve the legacy final-reply parser contract.
- ceb8e23: Record a 600-second Memory correction worker budget (ADR 0009) for independent
  body review and semantic Memory repair, and retain distinct started and closed
  repair lifecycle markers. The Harness correction path keeps its own 230-second
  bound, and every semantic threshold, request bound, retry count and mutation gate
  is unchanged.
  
  Keep completed worker usage when a lifecycle artifact write fails. Attempt usage
  and closed-marker retention independently, return known costs, and reject the plan
  when required artifacts cannot be retained.
  
  Record repair activity counts and relative first/last progress times without
  storing reasoning text. A missing complete answer alone does not establish
  whether the service continued generating.
  
  Resolve installed Pi workers through the package-declared CLI entry, including
  Pi 1.3 bundled entry points, while refusing paths outside the package.
  
  Keep declared type members separate from own or inherited runtime properties in
  Memory generation and correction. Require implementation citations for ownership
  claims.
  
  Keep populated Why and How to apply sections when semantic repair changes a
  candidate or an existing record. Permit evidence-backed changes to their text
  and conditions. Do not replace these sections with bare source excerpts. Keep
  legacy records compatible and retain the existing authorized deletion path.
  
  Let semantic repair explicitly decline parent-reviewed optional new drafts that
  have never been stored. Review the complete declined set with the final remaining
  plan and keep user storage, correction and preservation obligations. Report these
  drafts as not learned with zero applied changes. Retain every failure and cost.
  Keep populated purpose sections during deterministic preference distillation.
  
  Recognize purpose labels with a colon inside or outside bold Markdown. Keep
  other bold section headings from filling an empty purpose section.
  
  Keep compatible Promise inputs when describing a PromiseLike contract. Do not
  turn a type-name distinction into an unsupported exclusion of valid values.
  
  Keep a submitted description correction when a body consistency repair changes
  its meaning. Permit that paired correction without changing other metadata, and
  require fresh source, description, body and complete-record review before writes.
  
  Clarify the assertion level in normal Memory consistency review. A quoted type
  contract does not itself claim verified runtime behavior. Keep explicit runtime
  contradictions, complete review, existing thresholds and finite historical wires.
  
  Preserve learning purpose written with plain `Why:` and `How to apply:` labels.
  Classify absent project instruction documents as no-op consolidation so verified
  Memory and Harness work can complete its original backlog reference. Keep
  protected targets and unresolved reviews pending.
  
  Refuse non-regular consolidation files without blocking when opening a FIFO.
- b3daa7f: Reject failed and aborted assistant output even when the worker CLI exits successfully. Preserve cancellation until a successful reply, stop learning before repair or application, and report unavailable usage and cost without exposing provider error text.
- e86a44f: Render reported agent answer bodies with native Markdown inside the shared lifecycle band.
  Preserve exact final text, width bounds, expansion hints, and plain summaries for other consumers.
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

## 0.5.1

### Patch Changes

- 52e25f9: Match Pi's typed mouse handler in the structural component contract. `PiMessageComponent.handleMouse` was declared as `(event: unknown) => unknown`, which stopped satisfying the host's `Component.handleMouse` once Pi typed it as `(event: TuiMouseEvent) => TuiMouseEventResult | undefined`, so a package returning a lifecycle component from `registerTool` or `registerMessageRenderer` no longer compiled against the current host. The interface now mirrors that result as the structural `PiMouseEventResult`, keeping kit free of Pi runtime imports while a consumer's type-checker accepts the component again.

## 0.5.0

### Minor Changes

- 28bdae2: Add `searchModelFromPicker`, an interactive type-to-filter model picker built on `ctx.ui.custom`. Packages can pass the full registry model list (e.g. `ctx.modelRegistry.getAll()`) instead of only scoped or available models; the picker offers live search, keyboard navigation, a current-model marker, and empty-list warning fallback.
  
  `pi-recap`, `pi-vision`, and `pi-continual-learning` model menus now use the searchable picker and enumerate all registered models instead of limiting selection to scoped models.
- 707c4c5: Add `verbatimSubject`, `subjectBlock`, and `bgToken` to the lifecycle spec so user-authored text renders raw on the band: one row per authored line, wrapping instead of merging, no `@name` recoloring, no expand hint for text that is already visible, an optional block layout (head row, blank band row, then the authored lines), and an opt-in band tint such as `userMessageBg`. Hidden details still expand and keep their hint.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.

### Patch Changes

- b0231e3: Render coordination message previews against the actual terminal width rather than a fixed character limit, reserving the complete configured expansion hint. Expanded message rows wrap the full message inline after the recipient and outcome exactly once instead of repeating a clipped preview above a duplicate body. Preserve semantic line breaks, native theme bands, and safe display text, including visible labels inside terminal OSC-8 hyperlinks. Keep literal JSON empty strings, punctuation spacing, and quoted newlines intact by separating handle replacement from prose cleanup. Reuse the same pi-kit lifecycle abstraction as context research; native Ctrl+O, mouse expansion, and terminal resizing are covered by isolated Pi integration tests.
- ac83f4e: Prevent pre-cancelled child workers from spawning, fail closed on bounded worker stream violations, and disable extension discovery for isolated side-question and research children.
- 9cabb0d: Bump every package by one patch version.
- 919504f: Remove the obsolete shared package-agent prompt helper from pi-kit.
- bcb0054: Move continual-learning planner protocols into package-owned prompt resources, add typed local builders with fail-closed placeholder validation, migrate every one-shot planner caller, and launch children with the shared minimal read-only Pi environment.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- 919504f: Wrap custom transcript lifecycle messages in host ToolExecutionComponent so mouse click toggling works symmetrically with tool result rows.
- 274cc90: Unify lifecycle expansion across normal and static tool/message renderers. Internal metadata and empty detail bodies no longer create empty expansion prompts; width-clipped titles and summaries reveal their full text through the injected native wrapper. Preserve full readbacks, paragraph spacing, error evidence, and the explicit legacy low-level host override.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- b0231e3: Replace the recap line with a single identity-only `Recapping...` activity row while a recap is generating instead of stacking the marker above a stale `✦ Recap:` line, and let pi-kit live activity widgets omit the `· <activity>` suffix when no fallback activity is configured.

## 0.4.2

### Patch Changes

- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- b28ef2d: Return a teammate's recorded terminal report in a pi-kit lifecycle event so the leader never needs to force a duplicate resend, and extend leader guidance against resend steers and task_list polling.
  
  Allow lifecycle renderers to explicitly preserve every expanded detail line for user-requested readbacks while retaining the default 50-line bound.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.

## 0.4.1

### Patch Changes

- Republish the shared lifecycle helpers, including `eventToolLifecycle` and `renderToolLifecycle`, in the package artifact.

## 0.4.0

### Minor Changes

- dcf3806: Converge lifecycle titles on the spec API and delete `formatToolEventLabel`: semantic verbs (`listed`, `created`, `gathered`, `to @name`) now ride `ToolLifecycleSpec.label` instead of an ever-growing kind union, so `formatToolLifecycleTitle` with the `startedToolLifecycle`/`eventToolLifecycle` builders is the only title path. Expand behavior keys off data inside `renderToolLifecycle`: any collapsed row carrying detail lines appends the configured hint and expands to reveal them. Monitor, utils/sessions/worktree-session, and pi-git-agent session_context migrate onto it.
- a7fbc11: Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.

### Patch Changes

- fde16ae: Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
- dcf3806: Preserve the configured expand hint for lifecycle tool rows when a result has structured details but an empty visible content body, such as teammate_spawn's `{ started: true }` result. The title truncates before the hint so `ctrl+o to expand` remains visible within the available TUI width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.

## 0.3.0

### Minor Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.

## 0.2.0

### Minor Changes

- 50c45ff: Share compact tool lifecycle labels through pi-kit and standardize monitor startup and terminal event rendering.
- 7ad11b4: Render `list_directory_sessions` with the shared compact tool display pattern: self-rendered shell, empty call slot, and one `[sessions] listed · N other sessions in <dir>` result row styled like monitor terminal events (custom-message label color on the custom-message background). Expanding reveals a bounded block per session with status, pid, relative age, goal, recap, and recent files; every display field is sanitized with the new shared `safeDisplayText` and truncated to bounded lengths.
  
  Registry reads now normalize untrusted records on read (numeric pid/timestamps, known status union), merge records from multiple writers (extension state and keyboard glow state use different id conventions) into one logical session per owning process, and exclude records owned by the current process regardless of id, so counts and listings are no longer doubled.

## 0.1.1

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
