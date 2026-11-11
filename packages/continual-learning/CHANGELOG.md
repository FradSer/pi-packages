# pi-continual-learning

## 1.0.0

### Major Changes

- a3ee3e3: Replace the `learn_current_memory` model-facing tool with a single zero-argument
  `learn` tool. This is a breaking change with no alias, no compatibility layer
  and no recorded-branch migration.
  
  The one tool covers two explicit request families: organizing/remembering
  Memory ("整理记忆", "记住这个", "remember this") and authoring a lasting Harness
  rule ("以后禁止 npm", "纠正旧规则"). The model passes no intent, type, content,
  path or file; the parent freezes the task evidence and routes the request. A
  Harness request opens the existing guarded `/harness` procedure and returns an
  honest `authoring-started` outcome. The follow-up turn may use the new declared
  `harness_write` tool, whose required `cases` field survives strict tool-schema
  sampling; the parent validates positive and negative fixtures, confirms, writes
  atomically with readback, and records a receipt plus an undoable history row.
  The existing two-step `harness_preview` path remains available. Memory requests
  keep the existing Memory-only pipeline, receipts and undo.
  
  The parent classification reads one real user entry. The consolidation
  pipeline's evidence screen (`screenLearningEntries`) and the frozen historical
  proofs are unchanged; planner-child structured-output flags and the
  `learning_read` evidence marker remain. See ADR-0014.

### Minor Changes

- f377cf2: Split learning triggers into independent `autoSettledLearning` and
  `autoContinualLearning` settings (both off by default) and retire `autoMemory`.
  When enabled, the parent registers `learn`, a no-parameter tool that lets the
  agent request current-task Memory or Harness learning once before its final
  answer. The request carries no content: the parent freezes the task evidence and
  applies the configured `automaticPhases.memory` policy, so `apply` writes only
  validated changes, `propose` saves them for review, and `off` refuses. The settled
  learner skips Memory for a task the agent already processed while still handling
  Harness and AGENTS.md.
  
  All user-level configuration now lives in one file,
  `<agent-dir>/continual-learning.json`: the learning model (`model` as
  `provider/model` or `{provider, model}`), the two learning triggers, phase
  policies, AGENTS.md budget, Jev and the capability flags. `/memory model` and the
  settings menu merge into it and preserve every other section. The retired
  `<agent-dir>/memory.json` pair and `<agent-dir>/memory/settings.json` learning
  fields are neither read nor written; with no unified `model`, learning follows
  the session model.
  
  Learning also preflights the model against the no-extensions view used by planner
  children. An extension-registered session or configured model now blocks with an
  actionable `/memory model` message before any worker spawns, instead of failing
  the selector with `Model not found`.
  
  
  Agent-requested learning no longer treats replay-backlog bookkeeping as a
  precondition: a malformed backlog or an unavailable replay reference now reports
  the real learning outcome instead of failing with `learning was not started`.
  
  
  All Memory is reviewable by default. `allowPrivateMemory` is removed from the
  configuration schema, `createJevJudge`, the judge surface and the consent
  helper, so agent-requested and settled learning no longer stop with
  `private-memory-denied`. Frozen research source copies keep their historical
  form.
  
  
  Selector workers now default to off thinking; an empty worker decision falls
  back to a bounded parent-routed minimal selection instead of failing the whole
  learning run, while undecidable nonempty output stays a reported failure.
  Agent-triggered results report a failure in any phase, not only Memory.
  
  
  Coverage and body-review workers may wrap their JSON decision in a single
  Markdown fence; the parent now parses it without relaxing the reject rules for
  prose, extra objects or digest binding.
- a3ee3e3: Remove the pre-pipeline privacy hold entirely, including the immutable-dossier reader that still failed the Harness phase with `harness planner dossier unavailable: Immutable dossier contains sensitive material` while Memory applied normally. Credential-shaped frozen evidence and snapshot/dossier text are ordinary learning input: selector, Harness and Memory planners all receive the unchanged digest-bound dossier and the model handles it. There is no startup hold, no screening reason in new receipts and no hold constants or summary/tone branches. Storage-side guards remain: the history WAL, expandable result display, Jev preflight and semantic review still refuse to persist or transmit a credential-shaped Memory body, and an explicit `/memory` request containing a secret is still refused rather than stored. The `screened` outcome stays only as a historical receipt value so frozen cohorts are not reclassified. The above-editor live activity identity now names its agent `learner`: `PiLiveActivity.identity` is a worker name, while the bounded run topic stays in `activity` and the spinner conveys progress.
- a3ee3e3: Report preflight failures accurately and keep legacy backlog rows from blocking replay.
  
  A sensitive-material guard on existing Memory bodies no longer stages the whole corpus into the history WAL; a no-change run writes no history record. Zero-worker receipts name the `preflight` phase and say `no model calls` only when no worker was started, while failed workers with unknown usage still report unavailable amounts. Old `auto-memory-off` backlog rows are quarantined and malformed-row counting is scoped, so unrelated historical rows no longer disable replay binding. The shared credential guard now distinguishes `Auth:` mode labels and bracketed placeholders from real secrets, refuses `*_WEB_KEY` assignments, and keeps parsed object members strict in both the TypeScript and Python detectors. Started learning rows name the real current-task topic from the last user entry instead of a generic placeholder.
- b3f7be3: 默认开启私有调试记录，按项目和会话关联插件入口、上下文、成功失败、后台流水线和学习回执。通过 `/learning debug` 查看状态、目录和分段容量，使用 `on` / `off` 合并更新统一配置。上下文以快照和摘要引用去重，内部阶段受控观测，流水线终态明确区分筛查、应用、取消和失败。敏感值在截断前脱敏，日志分段保留，记录失败不影响原执行。
- e86a44f: Add natural-language `/memory <request>` learning with parent-validated Memory-only
  changes, simplify Memory and Harness management menus, and offer only `full` as a
  common consolidation argument. Preserve advanced commands and scope aliases for
  compatibility, scripting and recovery.
- a3ee3e3: Converge the user-facing learning surface on a single `/learning` command and
  one zero-argument `learn` tool. The `/learning` Harness menu option now opens
  the guarded authoring procedure directly through the same parent-owned bridge
  as the tool, instead of looking up another command. Model guidance, six
  runtime diagnostics (write guards, headless menu, status and error notices)
  and both READMEs no longer offer or name `/memory`, `/consolidate`, or
  `/harness` as user input.
  
  Retire the planner worker loadout: `WORKER_LOADOUTS`, `workerCliArgs`,
  `workerToolNames`, `createWorkerToolSurface` and the planner case tool. The
  parent active-tool transitions and the dynamic current-source collector's
  scoped one-read budget survive in `createParentToolSurface` and
  `createCollectorToolSurface`; the `learning_read` name remains the collector
  tool and the frozen-evidence marker.
  
  Three internal slash-command bindings (`/memory`, `/consolidate`, `/harness`)
  remain registered solely for frozen provenance proofs and offline end-to-end
  runners. They are not documented, offered in menus, or named in guidance.
  Frozen research evidence and completion gates are unchanged.
- e86a44f: Add opt-in TypeSafe Jev judgments for incremental learning directions, Memory metadata relevance and parent-validated candidate semantics. Keep existing commands, empty-index routing, evidence and privacy checks, phase policies and Harness enforcement. Uncertain or unavailable judgments use the legacy selector or preserve candidates as proposals; receipts record controlled reasons and actual model usage without evidence text.
  
  Keep initial Memory learning and bounded correction faithful to ordered source changes: removed patch lines describe the predecessor, and incomplete final observations must remain qualified. Complete evidence and semantic acceptance gates stay unchanged.
  
  Add explicit verified-gateway JSON Object output for no-tool Qwen3.8-Flash learning
  workers, preventing text tool-call output from substituting for a plan when the
  provider honors the constraint. Preserve all parent validation and unknown-gateway
  behavior.
  
  Preserve validated repository observation metadata during field-specific Memory correction. Missing observations now report unknown repository grounding for every filename, rather than falsely declaring non-prefixed source knowledge inapplicable. Semantic and mutation gates remain unchanged.
  
  Keep original source observations when bounds prevent a field checklist, and allow structural correction of an unambiguous missing `.md` suffix on new Memory proposals while preserving intent, privacy and exact existing targets.
  
  Scope local Memory completeness criteria to each record while retaining the whole-plan gate. Bind the parent-selected question contract and keep historical rejected questions exact. Refuse coverage requests without the complete cited review path before transport.
  
  Keep independent Memory coherence and source failures visible to the existing
  correction worker. Include controlled observed scores and retain an explicit
  omission notice within the final diagnostic budget. Preserve repair permissions,
  semantic thresholds and finite historical and Harness review behavior.
  
  Keep source-supported applicability conditions during semantic Memory correction.
  Distinguish missing citations from false or obsolete conditions, and check the
  complete corrected scope before returning the existing amendment. Preserve all
  semantic gates, correction limits and mutation permissions.
  
  Remove conflicting unsupported-only and uncited-deletion instructions from the
  parent semantic repair diagnostics. Permit source-supported missing conditions
  only in admitted fields. Keep original-source checks and all mutation gates.
  
  Make the existing coverage-account output contract explicit about the required
  conditions array on every claim, including its empty case. Preserve rejection of
  missing arrays and every independent review; a valid shape is not approval.
  
  Keep cited source-version bounds in initial Memory bodies when discarding routine
  metadata inventories. An unavailable revision identifier does not erase a separate
  observed identifier. Preserve semantic gates and unknown revision limits.
  Remove the broad behavior-record declaration exemption so mixed runtime/type
  records keep the existing conditional complete-declaration requirements.
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

### Patch Changes

- 8662e95: Use additive run-start prompt contributions instead of complete prompt overrides. Do not use custom messages for context injection. Handle custom startup without a user prompt. Keep unrelated workflow records and authorization checkpoints.
- 2116b41: Report the real applied Memory count in the `learn()` tool-result row. A real `~/Documents/Home Lab` run showed `[learning] settled · learned 0 Memory changes` next to a transcript row saying `Learning 2 memories applied`: `learningOutcomeSpec` renders `details.operations`, but `learn()` never put that field in its result details, so every applied run rendered zero. The tool result now carries the receipt's accumulated Memory operation count; proposals, failures and disabled results carry zero and keep their existing wording. No receipt, write or gate changes.
- e86a44f: Block invalid learning model configuration before selection or normalization and
  freeze the selected session model when no separate learning model is configured.
  Align Memory privacy, plan, menu, validator, and undo parsing. Reject repository
  observations that escape through symlinks or claim an existing path is missing.
  Preserve real Harness guidance provenance, and treat unreadable
  session context as incomplete. Improve configuration diagnostics and terminal
  label sanitization without expanding the compact command surface. Recover once
  from missing Harness planner output while preserving frozen evidence, model,
  validation boundaries, and complete per-attempt receipt accounting.
  Clarify that durable personal response preferences remain private Memory when a
  mixed task also updates existing knowledge or supplies scoped instructions.
  Make the optional Harness report object shape explicit without relaxing parent
  validation or increasing the bounded repair budget.
  
  Skip empty full runs before any model calls. For an empty current session,
  freeze one bounded recent same-project active context with source provenance;
  extract new grounded Memory even when the corpus is empty. Reject malformed
  session graphs and preserve v1 context edits. Distinguish missing learning input
  from a reviewed no-op, and supply an identity-bound Harness no-op protocol.
- 7cccf2f: Enforce planner read scopes, literal prompt binding, optimistic transaction ownership and conflict-preserving recovery. Keep Memory metadata in untrusted reference context, downgrade incomplete-evidence learning to proposals, and expose meaningful automatic receipts and paged management details.
  
  Populated legacy private/scoped Harness paths remain unchanged but bind automatically to the first accessing canonical project for compatibility. Canonical-path collisions are refused. Add the TypeBox peer required by the scoped worker extension.
- a3ee3e3: Fix two real-project learning failures. The incremental Memory validator now derives the same parent-owned classifications as the learning dossier: a selected file with no public mirror is private even when the private MEMORY.md row lacks a `(harness only)` marker. This removes the "Operation classification disagrees with parent-derived inventory" rejection in non-Git projects, along with the follow-on structural-repair rejection. Dotted version-style Memory filenames such as `88.1-dual-wan-loadbalance-research.md` are now accepted by both the TypeScript filename guard and the Python artifact validator; leading dots, consecutive dots, path components and repeated `.md` segments stay rejected.
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
- a3ee3e3: Make the final `[learning]` outcome row expandable to show exactly what was applied. Expanding names each applied Memory by its filename and renders its description and body as Markdown; when AGENTS.md also changed, it names that file and shows each validated edit's operation and applied unit text. A normally settled zero-write run (no-change, screened, organized in-process) expands to state what was checked and that no Memory or AGENTS.md changes were written, so it no longer looks like an unfinished run; failed, rejected, cancelled or proposed runs never claim a completed check. Frontmatter, byte digests and receipt metadata (usage, cost, source, calls, attempts, diagnostics) are not displayed. The user owns every Memory file, so harness-only private entries are shown exactly like safe ones; credential-shaped and forged entries are never shown. Previously a private-only applied run reported `N memories applied` with an empty expansion; now the applied filenames and bodies are always readable. This relaxes only the display privacy classification, never the credential screen, the safe/private storage split (private still stays only in the private root with no public mirror), or the write-side privacy gates.
  
  The generated bodies and edit units travel inside the custom message's `content` after the one-line summary, because Pi persists only a fixed set of custom-message fields. The stored receipt and the model-facing `details` are unchanged.
- a3ee3e3: Show one live activity row above the editor while a learning run is active,
  using the same shared pi-kit spinner widget language as subagents. The row
  names the run without receipt metadata and is cleared on completion, failure,
  cancellation and session reload. Headless (`--print`/RPC) runs stay silent.
  Transcript rows (started and final result) are unchanged.
- a3ee3e3: Scope the built-in no-bulk-memory-deletion Bash rule to one shell segment. A
  later `.memory` grep filter or search pattern in a compound command no longer
  inherits an earlier unrelated `rm`, while deletions that name a Memory root in
  their own segment stay blocked. Script one-liners with quoted semicolons and
  `find`/`rsync` deletion forms keep their existing protection.
- b3f7be3: Bound how many new Memory files one automatic task may create. The private debug logs confirm this is a general pattern, not one project: across all scopes, 17 automatic batches wrote three or more Memory files (six, six, five, five fours, nine threes) and 19 stored plans contain three or more `newMemories`, mostly with `no-durable-memory-evidence` but routed to Memory by an agent `learn` request or an observed indexed-Memory read. The `hud-playground` case (`batch_67abf737...`, four files, `mode=automatic`, `input.source=current-session`) is one of them; an earlier plan there held six. The existing 16-candidate plan limit and same-batch Jev novelty only compared the current batch, so small batches accumulated indefinitely. `maxNewMemoriesPerRun` in the unified `continual-learning.json` (default `2`, valid `1..16`, invalid values fail closed) caps newly created files after full structural and semantic review: an over-limit automatic plan is saved as a reviewable proposal and reports the exact count and limit, with no Memory file or applied mutation receipt. Only `plan.newMemories` counts — verifying against all 128 stored plans, counting total operations instead would flip the decision on eight batches that also rewrite or delete existing records. Rewrites, deletes, propose policies and explicit `/memory` requests are exempt, and later Harness/AGENTS.md planners do not run from a held Memory plan.
  
  A held plan is now reported honestly in the terminal. The first cap implementation reused the `semanticProposal` hold path, so the memory attempt settled as `proposed` with `operations: 0` and the result row fell through to the quiet zero-write branch — reporting `no changes written` plus `N frozen entries were checked; mirrors, indexes and consistency were verified` even though the parent had actively held a grounded plan. A real `git-agent-cli` run (`batch_a0ef7c...`, 11-11) showed the `ui:notify` hold and that result line 25 ms apart from the same receipt. The parent now records a `new-memory-cap-hold` routing marker on the receipt; `learningSummarySubject` reports `new Memory plan held by per-run limit; proposal saved for review` and the zero-write "no changes / verified" expansion is suppressed for it. Normal zero-write runs are unchanged.
- 2116b41: Pair every `[learning] started` transcript row with exactly one terminal outcome row. Two real gaps were found in `~/Developer/FradSer/open-deskos`: (1) an agent-triggered run that found no durable changes, organized in process, or produced a screened/skipped receipt emitted the started row and an honest tool result (`Learning no durable changes`, `Memory organized in-process`) but no terminal row, because `shouldReportLearningReceipt` filtered those outcomes when `reportResult` was false; (2) a cancelled run wrote its receipt to disk but the `finally` branch never reported it, so a session shutdown stranded the started row. `startConsolidationPipeline` now derives one `reportedStarted` flag from its own `reportStarted` callback, routes all terminal paths (normal, error, cancelled) through one `reportTerminal` latch so an error-handler await overlapping a shutdown cannot double-report, and always reports cancellation. Background settled/replay pipelines that never emit a started row keep their quiet no-change behavior; no receipt, gate or write path changes.
- b3f7be3: Quiet the zero-write learning result. The terminal `[learning]` row and the `learn()` settled row previously said `no durable changes` / `no durable Memory in this task` — engineering jargon that framed an empty result like an outcome and covered three different states (no model run, a pre-start screening hold, and a review that found nothing worth saving). Both now read `no changes written` / `no Memory changes written`: short, factual, jargon-free. This is display-only; the receipt, the `; N pending review` suffix, the paired started/result rows, and the expandable checked-scope note are unchanged. Frozen historical fixtures keep their original wording.
- 2116b41: Give an otherwise complete Memory selector decision one bounded correction when its only defect is an out-of-range or duplicate frozen index. A real run in `~/Developer/FradSer/open-deskos` returned `[44,50,20,26,27,52]` against a 52-entry frozen index (valid `0..51`); the bare `selectedIndices contains an invalid or duplicate frozen position` diagnostic rejected the whole run with no retry. The parent now names the exact bad position and range in the rejection, passes that reason to the existing one-attempt structural correction, and fully revalidates the fresh decision before writing a dossier. All other structural, identity, privacy and range gates stay fail-closed, and a second invalid position still fails the run.
- 2116b41: Use the shared Memory filename guard for the consolidation selected scope. A real `~/Documents/Home Lab` plan selected `openwrt-upboard-1010101-25.12.md` (and other dotted version-style names such as `88.1-dual-wan-loadbalance-research.md`) and failed with `Consolidation plan selected[1] is not a canonical memory filename`, even though the corpus enumerator, `isMemoryFilename` and the structured validator all accept those names. `inject-memory.ts` kept a private stricter regex in two places: `normalizeSelectedScope` rejected the plan, and `parentSelectedScope` silently dropped dotted names from the parent-derived scope. Both now call `isMemoryFilename`, so the three surfaces agree; leading/consecutive/trailing dots, repeated `.md` segments, path components, `MEMORY.md` and duplicate names stay rejected. No gate or write path changes.
- 5108254: Judge a credential-named key that assigns a structured configuration literal by the literal's own members, so ordinary configuration snippets such as `apiKey:{source:"file"}` no longer refuse a whole learning record or Harness mutation. A secret assigned inside the literal is still refused, including a snippet under a wrapping document line, and the dependency-free validator mirror reports the same classification for the shared corpus.
- a3ee3e3: Centralize the tool surface without changing behavior.
  
  `extensions/tool-surface.ts` now owns the four canonical tool names, worker loadouts, parent active-tool transitions, read/case budgets and the worker CLI allowlist. Existing tool definitions, commands, prompts and validation gates remain unchanged.
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
- b3daa7f: Preserve a validated HTTP error status in Jev service-failure receipts, including split and full-evidence requests. Keep original fallback/proposal behavior, partial-usage limits and privacy protections.
- b3daa7f: Guide Memory generation and the existing semantic repair to cite relevant original evidence for body and description claims, distinguish future intent from verified current state, and preserve later corrections without attaching unrelated evidence. Keep all original privacy, quote, identity and Jev acceptance checks.
- b3daa7f: Give the existing Jev-enabled incremental Memory structural repair its hash-bound source evidence and selected Memory without increasing repair quota or write authority. Reject privacy reclassification and preserve completed repair usage when frozen input changes.
- b3daa7f: Add a programmatic evaluation gate for independently supported original new Memory records. Preserve the complete original proposal before applying a separately validated subset through the existing parent writer, retain uncertain records for review, and distinguish applied records from pending records in receipts. Ordinary user configuration keeps whole-plan behavior; this does not claim real-project quality improvement.
- ceb8e23: Judge documentation-style text placeholders identically in the Memory guard and
  the Jev preflight, so a tracked source sample no longer refuses a whole review.
  Both detectors now match plain, quoted and delimited credential assignments
  through one pattern set and one placeholder rule, and a credential-named
  structured member or object key is strict in both. A credential-named assignment
  has no URL exemption: a webhook, a token-bearing link or a connection string
  under such a key is refused, and so is a delimited value containing `,`, `;`,
  `?`, `'` or an escape. The documented placeholder rule, which covers code, env
  and expression references, is the only exemption. The plain pattern's
  credential-key class accepts optional surrounding quotes, which widens detection
  only, and the preflight no longer reads `?` or `&&` inside a password as a code
  expression. No placeholder entry was added and no secret value class was
  loosened. The packed validator mirrors both patterns and the shared corpus pins
  them.
- ceb8e23: Wait a bounded 500 ms backoff before the existing single connection-only Jev
  retry, and yield immediately to an abort during that wait. The retry count,
  request bounds and per-request deadline are unchanged. A failed request group
  already stops later request groups of the same review; a regression test now pins
  that spending rule.
- 84b0db7: Accept a selector verdict that carries unknown extra fields instead of discarding the run. The selector's eight required fields must all be present and every authoritative field is still type- and value-checked, so an extra key grants nothing; but a model that echoed an input field such as `omittedEntries` used to fail the exact-key check and end the learning run with zero operations and only a formatting complaint. A rejection for a missing required field now names the missing field, and the selector prompt states that slice fields are input, never response fields.
- b3daa7f: Locate complete Jev counterevidence holds by original evidence window and entry range in receipts and bounded repair hints. Keep raw evidence private, retain whole-plan holds, and never infer locations from incomplete reviews.
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
- b3daa7f: Expose read-only, digest-bound observations of complete new Memory candidate checks. Incomplete or changed inputs produce no observation. Whole-plan holds and existing write permissions remain unchanged; observations do not prove same-batch independence or authorize partial writes.
- b3daa7f: Add a bounded read-only Memory relationship review API using the existing Jev client. Bind complete original candidate reviews, check all data and requests before transport, retain actual model and known usage, and strip provider text from structured observations. Partial Memory application remains disabled.
- b3daa7f: Use frozen parent identity to recognize the canonical project git-push matcher before Jev semantic validation. Keep independent authorization, argument scope and complete counterevidence gates, without weakening thresholds or existing Harness protections.
- b3daa7f: Give Harness semantic repair the exact parent-owned rule identities and complete evidence bindings. Preserve existing write and semantic gates, and report controlled identity or citation mismatch categories when repair is rejected.
- b3daa7f: Recognize literal tabs and escaped tabs in the exact parent-bound project push template as equivalent spelling. Preserve the original rule and all user authority, argument scope, explanation, privacy and full counterevidence checks.
- b3daa7f: Reject failed and aborted assistant output even when the worker CLI exits successfully. Preserve cancellation until a successful reply, stop learning before repair or application, and report unavailable usage and cost without exposing provider error text.
- b3daa7f: Restore newly created empty Memory roots after a cancelled write with a non-recursive directory removal. Keep the original cancellation error instead of adding an EISDIR rollback failure, and preserve concurrent files.
- 8662e95: Contribute Goal context once per run through Pi 1.2 before_agent_start prompt sections. Remove runtime-message replay. Deliver Memory discovery at run start only; context filtering no longer inserts missing references.
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
- b3daa7f: Validate Memory index descriptions with independent Jev support, relationship,
  and full-evidence judgments alongside the original body checks. Keep duplicate
  bodies and conflicting descriptions as proposals, preflight all extra questions
  against existing limits, and identify description failures in controlled repair
  hints without recording their contents.
- b3daa7f: Keep parent final Memory receipt, privacy and frozen-evidence verification inside the writer's rollback boundary. Final verification failure or cancellation restores provisional files and indexes before history or receipts count an applied mutation. Existing three-argument writer calls remain compatible.
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

## 0.4.0

### Minor Changes

- a61a89e: Add opt-in per-phase automatic learning policies, private change history with conflict-aware undo, independent rule evaluation and paired Memory task evaluation. Existing automatic apply defaults and explicit consolidation behavior remain intact.
  
  Release locks on failed selection and preflight, preserve evidence across explicit continuations, bound complete task slices, run manual selection without automatic-screen keywords, review verified troubleshooting recoveries, and accurately summarize AGENTS.md changes.
  
  Accept canonical project-root aliases in learning history without following surface symlinks, and extract unambiguous Harness and AGENTS.md plans surrounded by prose while retaining identity validation.
  
  Separate worker assignments from quoted evidence with a package-owned system instruction, bind selector examples to the current digest, and report bounded structural selection errors without echoing rejected content.

### Patch Changes

- 01a46d3: Stop spending learning calls on evidence that is not evidence, and make the results inspectable.
  
  Harness activity is now decided by Harness-owned transcript evidence (guardrail event entries, Harness guidance delivery, and the notes Harness attaches to tool results) instead of matching words such as `policy`, `harness`, or `blocked` in repository text, so reading a harness file no longer starts a harness planner. A manual consolidation honors the selector's reviewed verdict unless user-stated evidence or real Harness activity floors it: a verified tool recovery alone no longer starts a Memory planner the selector declined after reading the same slice. Completed Memory runs keep their run directory (task, plan, receipts, manifest, snapshot) for inspection, and a sensitive snapshot refusal now names the learned surface to clean without echoing the matched bytes. Planner dossiers record Harness events from that same Harness-owned evidence instead of transcript fragments that merely mention the harness.
- ad80757: Stop learning history from refusing ordinary learned text. Credential detection now requires an assigned value long enough to be a credential or a concrete provider key format, so wiki links and names such as `skills-host-agnostic`, workflow permission names such as `id-token: write`, and prose such as `Auth is delegated` no longer fail the whole pipeline with `Learning history refuses sensitive material`. Real assignments, provider keys, private keys and bearer tokens are still refused.

## 0.3.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.3.0

### Minor Changes

- d3efa47: Harden continual learning across every runtime surface. Restore two synchronized Memory roots with one flat readable canonical-path identity for private directories, locks, and runs (rejecting names over 240 bytes and intentionally sharing sanitizer collisions) while ignoring obsolete private-root layouts without compatibility discovery or migration. Store locks separately at `memory/locks/<scopeKey>.lock` so private directories for projects such as `foo` and `foo.lock` coexist. Make AGENTS.md learning require indexed user/tool evidence and apply extraction artifacts, instructions, and recovery receipts in one rollback boundary. Keep exactly three canonical Harness layers, validate complete writes, reject path escapes, deduplicate unchanged artifact repairs, and skip corrective turns for interrupted output. Automatic learning now recognizes durable prohibition wording, runs later-only evidence without Memory mutation, bounds and cancels background workers, and reports every attempt and applied operation accurately.
- db62119: Learn from settled user tasks through parent-validated plans, including new memory creation from an empty corpus. Separate Harness guidance from enforcement, ground learned policies in snapshot evidence and executable examples, and check assistant output and file artifacts with bounded repair feedback.
- 36375b3: Unify new Harness authoring, automatic learning, and AGENTS extraction on flat skill/Bash/text rules. Preserve installed policy/skill-prompt and output/artifact protections through read-only compatibility rather than treating valid old configurations as global execution failures. Additions preserve existing declarations; removals require explicit authorization, with no automatic file migration. Preserve evidence, revision-bound ownership, narrow evaluator cases, privacy, and transactional receipts.
  
  Replace rigid authoring scripts with a bounded outcome contract, retain conditional AGENTS pointers during extraction, make guidance scope visible in retained messages, and keep omitted Memory entries discoverable without silently cutting relevance cues. Simplify planner instructions while retaining their machine protocols. Live smoke now requires actual learned rules rather than masking failed learning with fixtures. Scoped delivery revisions refresh resumed conversations once. Failed Harness readback rolls back identifiable parent writes without overwriting external changes; explicitly approved repairs can proceed one configuration layer at a time. Preserve exact repair-approval byte snapshots through later policy confirmations so concurrent edits cannot be overwritten merely because their resolved diagnostics match. Resolve execution policy after asynchronous preflight so newly installed protections cannot be bypassed by an earlier cached configuration.
- 34c5b62: Implement the flat Harness rules redesign: a single `rules` list with three selectors (`skill`, `bash`, `text`), stable rule `id`, and whole-rule nearest-layer override. Bash rules deliver a model-visible message on execution (omitted `action`), or gate the call with `confirm`/`block`; every matched message is collected and the call decision is order-independent. Invalid bash-scoped or ambiguous rules make Bash evaluation incomplete (fail closed) instead of silently executing, while clearly skill/text-scoped errors stay isolated.
  
  Skill and text guidance is delivered as a durable `before_agent_start` message (retained on the branch, deduplicated against retained guidance, prefix-stable for caching), replacing the ephemeral `context`-hook approach. Text rules scan the model-visible retained conversation (history and tool results) at agent start; same-run mid-run tool-result triggering is a documented follow-up pending a verified Pi delivery seam. `/harness` authoring, status, and target initialization now use the `rules` format; existing user files and the automatic-consolidation subsystem keep working through the legacy read path during migration.

### Patch Changes

- 37ffb70: Cut the per-turn cost of the injected memory index and of reading it. The prompt block now declares each body root once instead of repeating an absolute read path per entry, marks a shortened cue with a single `…` instead of a per-row notice, water-fills the remaining budget so short descriptions release characters to longer ones, and never drops a listed entry while its filename fits; the default budget is 6,000 characters. On a 45-entry corpus this lists every entry with a routing cue in a quarter fewer characters where the previous budget listed 21 entries and omitted 24. Loading no longer re-reads and re-parses every entry each turn: the read buffer is sized from the file, unchanged metadata is reused in-process while its device, inode, size, mtime, and ctime still match a regular non-symlink file, root identity is re-verified for every real read and for the batch, and the `git` root probe is memoized per canonical project path within a bounded window. Measured: a warm load drops from 18.8 ms to 1.75 ms with zero entry opens, and memory path resolution from 6.34 ms to 0.04 ms. Harness guidance now rebuilds and scans the retained conversation only when an enabled text rule can match it, reading delivered guidance state straight from session entries otherwise; `enabledTextRules` is the single predicate behind both that decision and the scanner itself.
- 9cabb0d: Bump every package by one patch version.
- 36375b3: Remove repeated title fields from expanded policy, check and guidance rows while retaining policy evidence, provenance and full guidance prompts, including prompts longer than 50 lines. Enforcement, guidance delivery and stored event data are unchanged.
- bcb0054: Move continual-learning planner protocols into package-owned prompt resources, add typed local builders with fail-closed placeholder validation, migrate every one-shot planner caller, and launch children with the shared minimal read-only Pi environment.
- 919504f: Teach direct harness generation and consolidation to translate incident evidence into reusable error classes before choosing narrow supported mechanisms. Avoid incidental resource identifiers and blanket write gates, transfer-test lessons across documents and rephrasings, and state the invocation-only limits of semantic skill guidance.
- 919504f: Require harness skill prompts to use exact registered skill keys and object-shaped prompt entries, with trigger verification guidance instead of treating JSON readback as effective enforcement.
- 1efd675: Identify skill and text rule guidance as the Harness rows they are: the transcript tag reads `[harness]`, the delivery module and its entry type are named for Harness, and entries persisted under the previous `context-guidance-event` type keep rendering unchanged. Enforcement, guidance delivery and stored event data are unaffected.
- 34c5b62: Keep harness write/edit gates working with asset-only Pi package directories without loading private runtime modules. Verify target aliases against the public native write tool and reject malformed consolidation targets before creating transaction receipts or changing ownership metadata.
- 34c5b62: Default harness authoring, consolidation, and skill extraction to project `.pi/harness.json`; reserve project personal configuration for explicit requests. Reject unchanged invalid skill guidance during authoring, validate runtime skill names against the available registry, and clarify inactive diagnostics and semantic limits without silently rewriting existing data.
- 919504f: Validate newly authored skill guidance against actual registered skills, reject bare-string entries, and distinguish inactive configuration from verified triggers. Gate direct harness writes and automated additions, normalize native tool path aliases before gating, and reject malformed predecessor containers without discarding data. Planner summaries filter unknown skills using the session registry.
- 3a6cdda: Classify consolidation planner model errors (quota 429, model cooldown) as labeled model failures instead of generic "missing schema-valid consolidation plan" rejections, and skip the fresh-planner retry that inherits the same failing model. Label dreaming-budget terminations as timeouts instead of raw exit codes, carry the previous rejection reason into the fresh planner's task header, emit validator errors once per category without duplicated prefixes, clip rejection notifications from the head, and document that grounding observations must cite existing files (skill directories via their SKILL.md).
- 2033c26: Remove unreachable legacy Agent control, unused internal helpers and constants,
  and the unused keyboard HID encoder (hardware commands already use via-rgb).
  Retain active entry points, shared public APIs, configuration compatibility,
  and behavioral regression coverage. Remove superseded planning documents and
  checks that only assert documentation wording or recreate implementation in tests.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.
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

## 0.2.2

### Patch Changes

- 548363d: Reject unsupported guardrail policy fields with actionable diagnostics, and apply the same runtime schema validation to consolidation plans.
- 548363d: Allow `/harness <prompt>` to route a natural-language rule request to the agent, with an explicit protocol for creating a narrow global rule in the personal `harness.local.json` while preserving and verifying existing configuration.
- 548363d: Render applied skill-prompt harness guidance as a visible, expandable transcript event with the actual prompt in the collapsed row and structured source details on expansion.
- 25b3787: Scope harness skill-prompt guidance to an expanded skill invocation's user message, enabling the Impeccable Live startup contract without affecting other Impeccable commands.
- 3e50fcf: Guide models to ask ordinary questions directly in the conversation when the Matt Pocock interview tool is unavailable, rather than starting an unrelated workflow.
- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- 92944c1: Apply progressive tool disclosure across runtime packages. State-dependent capabilities are now hidden until their workflow state is active, and continual-learning no longer couples its guardrails to Matt Pocock workflow state.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.2.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.2.0

### Minor Changes

- 616dad7: Rename the `/guardrails` command to `/harness`, and extend `/consolidate`
  into a two-phase pipeline: after a verified memory consolidation, a second
  read-only planner mines the same immutable session snapshot for tool-call
  guardrail evidence (blocked calls, confirm outcomes, corrections) and applies
  bounded policy/skillPrompt changes atomically to the personal project-local
  layer only.
- 42cd385: Add AGENTS.md consolidation as the third /consolidate phase. A read-only
  planner proposes at most five evidence-cited edits to the repository-root
  AGENTS.md against the same immutable snapshot as memory and harness
  consolidation. The parent verifies every cited quote verbatim in code,
  requires batched evidence for new units, gates document growth behind a byte
  budget with zero-sum updates at cap, routes narrow instructions to skill
  prompts or memory files via extraction, and autonomously applies only
  operations that pass all mechanical gates. User-level instruction files are
  never touched; the planner remains read-only. Validated plans are applied
  without a user confirmation step.
- 6dea952: Initial release under the new identity: absorbs @fradser/pi-memory 0.2.7 (memory retrieval, injection, /memory menu, consolidation) and adds the harness surface of continual learning — layered JSON tool-call guardrails evaluated on every tool call, blocking futile or dangerous calls with corrective guidance fed back to the model. Includes require-gate AND scoping, built-in defaults for interactive-auth/OTP automation, and the /guardrails command.
- 6d5b310: Add layered skill-specific corrective guidance for expanded `/skill:<name>` invocations, with idempotent system injection and user-target custom context messages.

### Patch Changes

- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

Continues the release history of `@fradser/pi-memory` under a broader identity:
the same memory surface plus declarative tool-call guardrails. Entries below the
heritage marker belong to the previous identity.

<!-- heritage: @fradser/pi-memory -->

## 0.1.0 (first release as pi-continual-learning)

- Absorbs @fradser/pi-memory 0.2.7 functionality unchanged.
- Adds layered JSON tool-call guardrails: corrective block reasons, require-gate
  AND scoping, built-in defaults, and the /guardrails command (renamed to /harness in 0.2.0).

## 0.2.7

### Patch Changes

- 152e880: Make `/consolidate` runnable end to end and diagnosable when it fails. The child planner now receives the parent-derived authoritative selected scope in the task header (the snapshot never contained it, so plans came back empty or partial and the scope-equality gate rejected every run), the procedure states the exact-name contract, and any pre-mutation failure retries once with a fresh planner through the same validation gates. Before planning, the parent deterministically normalizes mirror drift between the harness and public roots — newer mtime wins per file, private-marked or orphaned public files are removed, a missing harness root imports the mirror, and both indexes are rebuilt — so pre-existing drift no longer fails post-apply validation. Failed runs persist bounded stdout/stderr captures into their run directory and keep its artifacts while releasing the lock; retention is decided from ownership captured before state teardown. Locks left by dead same-host processes are reclaimed via atomic quarantine with one bounded retry instead of wedging the project forever. The dreaming timeout rises to 30 minutes for full-scope runs, and the validator's memory bounds align with the runtime (`--max-memory-files` / `--max-total-bytes` remain available as overrides).
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.2.6

### Patch Changes

- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.2.5

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.2.4

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.2.3

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.2.2

### Patch Changes

- a664c67: Add selectable and persisted model configuration for background memory consolidation, scope consolidation to related memories, and keep the active session responsive.

## 0.2.1

### Patch Changes

- 79c705f: Initial publish to npm via Changesets.
