# Continual-learning architecture and memory ownership
## Current architecture
`pi-continual-learning` improves Pi without changing model weights. It learns across three runtime surfaces:
1. **Memory** stores durable knowledge and exposes filename/description discovery. Models read entry bodies as untrusted reference data.
2. **Harness** resolves identified flat rules for new authoring: skill/text guidance and Bash messages or execution gates. A read-only compatibility boundary preserves installed tool-call, output/artifact, and skill-prompt declarations without weakening their semantics or rewriting configuration.
3. **AGENTS.md consolidation** maintains the small, always-loaded project instruction document and extracts narrower material into Memory or Harness.
These surfaces are deliberately different: Memory is untrusted reference
knowledge; Harness is parent-evaluated executable validation and execution
conditions; AGENTS.md and `skill`/`text` rules are scoped guidance. Guidance
delivery is not compliance evidence, and Memory never becomes an enforcement
rule. Automatic learning may identify more than one candidate surface, but it
must preserve manual, built-in, personal, disabled, invalid, and legacy Harness
ownership and must not duplicate one statement simply to increase coverage.

Automatic learning and default `/consolidate` operate on one completed **Task Slice**. A metadata-only **Memory Selector** chooses the minimum sufficient related existing Memory, and the parent builds one authoritative **Learning Dossier** containing that Task Slice plus selected bodies. Memory, Harness, and AGENTS.md planners consume the dossier and return only deltas. `/consolidate full` explicitly maintains the whole Memory corpus with bounded discovery from the current session.

Every phase follows the same trust boundary: the parent freezes the task context before asynchronous work, a stateless one-shot planner runs from a package-owned Markdown prompt with discovery disabled and the minimum tools for its mode (none for selection, `read` for incremental Memory, and bounded read-only discovery only for explicit full maintenance), and only the parent validates and applies a bounded structured plan. Typed package-local builders perform literal nonrecursive binding and reject missing, unknown, or unresolved prompt placeholders before launch. Memory attempts capture their bound inputs; Harness and AGENTS.md planners share one later-phase immutable capture of the same frozen context. Completion requires parent-owned validation and pre/post receipts; planner prose is never proof of success. Locks, path containment, symlink checks, atomic writes, rollback, output bounds, and shutdown generation checks remain mandatory.

Later-phase failure does not roll back an earlier verified phase. When Memory is selected, it must complete and verify before Harness starts; grounded Harness/AGENTS-only automatic evidence may instead use a verified no-mutation Memory gate. Harness failure leaves Memory intact; AGENTS.md failure leaves both earlier phases intact.
## Harness vocabulary

The flat Harness contract is described in
@packages/continual-learning/HARNESS-DESIGN.md. Authoring, automatic learning,
and AGENTS extraction use the same rule format and evaluator.

- **Rule identity** names one agreement independently of the content it matches.
- **Match entry** identifies a skill invocation, command invocation, or retained
  conversation text in which an agreement is relevant.
- **Effective rule** is the definition selected for an identity in the current
  configuration, together with its source and state.
- **Delivery record** is evidence that a particular revision of guidance reached
  an identifiable position in the current conversation branch.
- **Retained context** is the conversation currently available to the model after
  branch selection and compaction.
## Harness ownership

Harness configuration has four user-owned layers, plus package defaults, nearest first:

1. Project personal: `<project>/.pi/harness.local.json`
2. Project shared: `<project>/.pi/harness.json`
3. User scoped to this project: `~/.pi/agent/harness/<scopeKey>.json`
4. User shared: `~/.pi/agent/harness.json`

The scoped user layer reuses Memory's scope key — the canonical project path with separators replaced — so rules authored for one project cannot silently govern another. It lives in a directory parallel to `memory/` and never inside a Memory root: a Memory root admits only regular `.md` children, so a JSON configuration beside them fails consolidation's privacy validation and aborts the run. The all-projects user layer is kept as the lowest user layer, so a genuinely cross-project rule still applies everywhere.

Flat rule IDs are the addressable override keys across new selectors; nearer declarations replace a whole rule. Installed legacy policy/skill-prompt containers retain their original name-based override and disablement semantics through compatibility execution, including the historical effect of cumulative disabled names on same-ID flat rules. Compatible data is a notice, not an error; loading never migrates files. The obsolete user-personal `~/.pi/agent/harness.local.json` and project `.pi/agent/harness*.json` paths are not loaded, displayed, or targeted.

Direct authoring and automatic Harness consolidation default to `<project>/.pi/harness.json`. Other layers are read-only inputs to consolidation. Project personal `.pi/harness.local.json` is selected only by an explicit personal-configuration request; a global local variant is unsupported.

## Memory ownership: two synchronized roots

Memory deliberately uses two physical roots rather than copying the four Harness configuration layers:

1. **Harness/private Memory**: `~/.pi/agent/memory/<escaped-canonical-cwd>/`
2. **Project shared Memory**: `<project>/.memory/`

For `/Users/FradSer/Developer/FradSer/cerberus`, the private directory uses the official Pi flat escaped identity:

```text
~/.pi/agent/memory/--Users-FradSer-Developer-FradSer-cerberus--/
```

The name matches Pi's official session directory escaping: the canonical project path with leading slash stripped, slashes and colons replaced with single dashes, wrapped in double dashes (`--<escaped-path>--`). Names longer than 240 bytes are rejected, never truncated. The same name is the `scopeKey` for private Memory, `memory/locks/<scopeKey>.lock`, and `memory/runs/<scopeKey>/`; there are no hash-based project paths. Content-integrity digests remain unchanged.

The two roots have different privacy roles. No project-local private memory directory is recognized: private memory exists only in the agent-owned root.

- The Harness/private root is canonical and complete. It may contain both safe and private Memory.
- The project `.memory/` root is a sanitized, Git-trackable mirror. It contains only Memory classified as safe to share with the project.
- `MEMORY.md` in the private root marks private entries as `(harness only)`.
- A private-marked entry must never exist in project `.memory/`, and the project-shared index must never contain private markers.

## Memory synchronization contract

The previous two-root synchronization semantics are retained:

- Safe Memory exists byte-identically in both roots.
- Private Memory exists only in the Harness/private root.
- Before planning, drift is normalized in both directions. For a safe file present on both sides with different bytes, the newer mtime wins; ties prefer the Harness/private copy.
- A safe private-root file missing from project `.memory/` is copied outward.
- If the private root is absent on first adoption but project `.memory/` exists, project-shared files are imported into the private root rather than deleted.
- Public orphans are removed once a canonical private root exists.
- Private-marked files leaked into project `.memory/` are removed before the planner snapshot.
- Both indexes are rebuilt after normalization and after application.

Memory consolidation reads the related two-root scope, but the parent applies every selected operation transactionally across the privacy split:

- A safe create or rewrite updates both roots.
- A private create or rewrite updates only the Harness/private root and removes any project-shared copy.
- A delete removes the entry from both roots.
- Any later operation or mirror write failure restores both predecessors byte-for-byte.

The validator verifies plan identity, selected scope, source hashes, final hashes, mirror equality for safe files, absence of private entries from project `.memory/`, exact indexes, and receipt binding.

## Memory loading and injection

The private root is the complete runtime source. Project `.memory/` is also inspected so externally committed project updates can participate in drift normalization and first adoption, but deduplicated injection prefers the private copy for the same filename.

Only strict Memory basenames are accepted:

```text
[A-Za-z0-9][A-Za-z0-9_-]*.md
```

`MEMORY.md` is metadata and is never injected as an entry. Reads must reject symlinks, path escapes, non-regular files, oversized content, and root replacement during traversal. Injected Memory remains explicitly labelled untrusted reference data, not instructions.

## Obsolete private roots

The flat escaped canonical-path directory is the sole agent-private runtime root. Other layouts, including hash-only and hash-suffixed roots, remain untouched. Memory loading and consolidation do not discover, read, import, rename, or delete them, and there is no compatibility fallback or migration interface. Existing flat roots are retained byte-for-byte. On first access, populated legacy roots and new empty scopes bind automatically to the accessing canonical cwd for compatibility; a binding owned by another canonical project cannot be replaced. This prevents subsequent cross-project use but cannot retrospectively prove the owner of pre-binding legacy data. `memory/scopes/<scopeKey>.json` holds the binding outside the Markdown-only entry roots.

## Commands and settings

- `/memory` opens three actions: browse Memory, learning settings, and recent learning. Model search and the automatic-learning toggle live in settings, with per-phase policies under its advanced entry; history inspection and validated undo live under recent learning.
- `/memory <request>` learns only the explicitly requested Memory. The command arguments become the first entry of immutable evidence, with prior task entries as supporting context. The parent forces Memory review and disables Harness and AGENTS.md phases. Automatic learning may be off; the usual evidence, privacy, lock, validation, and receipt checks still apply.
- `/consolidate` has two learning modes; only `full` is offered as a common argument.
  - `/consolidate` learns from **the current context only**: the metadata-only Memory Selector picks the minimum sufficient related existing Memory for the one completed Task Slice, and the planners consume that dossier.
  - `/consolidate full` maintains **the whole Memory corpus using the current session**: the Memory scope is the entire corpus rather than a selected subset, the Memory planner is given bounded parent-scoped `learning_read` access to regular files and directory inventories instead of dossier-only access, and the frozen evidence is the current session rather than one Task Slice. Discovery remains bounded; this is not an exhaustive audit of the codebase or a replay of prior sessions. This maintenance path is never reached implicitly.
- The normal incremental and full commands use the current conversation and Memory corpus. Explicit backfill and bounded automatic recovery separately verify original session references before learning from past tasks. Settled tasks are retained before asynchronous settings checks, including disabled learning, settings failures and interrupted attempts. `learning-history.ts` remains the mutation audit trail for undo; replay inputs come from the verified original session, not history summaries.
- `backfill` processes retained references through the incremental pipeline; it does not enable full-corpus maintenance. Every run freezes a snapshot before any planner starts, and an unrecognised argument is refused rather than silently downgraded.
- The **learning backlog** retains settled tasks until learning completes, including disabled learning, screened tasks, failed attempts and proposals awaiting successful application. It stores references — session file and entry indices — never conversation text, and an entry whose session file is gone is reported as unlearnable rather than dropped or reconstructed. `/consolidate backfill` retries up to three source-verified learning references. With auto-learning enabled, completion of a normal attempt also retries at most one eligible failed task. Replay never repeats task tools. Failed, proposed, cancelled or unverifiable work stays pending; successful receipts acknowledge individual references without skipping siblings. Project leases serialize normal learning and replay. Attempts retain known costs; interrupted requests without a returned usage report have unknown cost. Automatic retries stop after three recorded attempts and back off between attempts.
- Backlog storage is a private regular JSONL file capped at 4 MiB; each reference is capped at 4 KiB and writes fail closed when the cap is reached (records are never silently rotated away). New records carry the project `scopeKey`, and cursors are scoped below that key. Legacy records are accepted only after their bounded session header proves the same scope; the historical global cursor applies only to those legacy records and cannot consume a scoped record. Unscoped records are reported separately. Symlinks, oversized files, malformed references, and changed files are diagnostics, not evidence to replay. Full state checks cover settings, backlog, scope, and cursor integrity before status is reported.
- `memory/settings.json` is strictly bounded and schema-validated. A missing file means automatic learning is enabled; malformed, unknown, unsafe, or unreadable settings disable automatic learning and expose a repair diagnostic. The package never silently treats invalid settings as defaults. Memory retrieval remains independent of this learning switch.
- `/harness` opens a rule list with details and a create/update entry. Its scope picker offers project shared (default), project personal, and user shared. `/harness <request>` directly prepares project-shared authoring; existing explicit scope aliases remain compatible. Unsupported or ambiguous requests do not create empty files or authorize edits elsewhere.

Auto-memory enables learning after `agent_settled` for real user input. It coalesces pending completed tasks, ignores extension-generated continuations as independent triggers, and waits for the full pipeline in headless mode. Existing Memory remains available regardless of the toggle. The main model is not asked to write memories directly; the parent validates new-memory proposals even when the existing corpus is empty.

New memories live in a separate `newMemories` proposal array while `selected` remains the exact parent-owned existing-file list. Snapshot message indices and quotes ground the proposals; preferences stay private and credentials are rejected. AGENTS.md extraction uses the same explicit safe/private classification, persists exact predecessor state in a pre-apply recovery receipt, and applies Memory, Harness, instruction, and post-receipt changes in one rollback boundary. On the next session start, an orphan pre receipt without a matching post receipt is validated against the canonical project scope and restored before new learning starts only when current bytes match the durable transaction ownership journal. Unjournaled legacy changes or newer human edits remain untouched and block recovery with a conflict diagnostic. Harness learning verifies user/tool evidence and executes positive and negative evaluator cases for each selector. Revision-bound `learnedRules` provenance protects manual edits; shared, built-in, personal, invalid, disabled, and manually authored identities cannot be overwritten by automatic learning.

Skill guidance names its invocation task in the model-visible message. Text guidance retains its selector and subject scope even when triggered by historical conversation. Flat and legacy skill guidance use additive structured run-start sections with explicit task scope, never custom context messages or complete system-prompt replacement. Saved legacy targets remain audit metadata; execution protections remain unchanged. A delivery revision includes its message format, so a restored unscoped delivery receives one scoped replacement without rewriting history. Matching and delivery do not prove semantic compliance. Output/artifact checks remain available for installed declarations, without becoming a fourth flat-rule selector or replacing project verification.

Memory injection contains only deduplicated filenames and bounded descriptions, with a compact root precedence list. It supplies the current structured discovery section at each run start. Old custom references are filtered without replacement context messages. Entry bodies require explicit relevant reads; index exposure does not establish Memory use. Automatic correction revisits actual successful reads paired by unique call identities and indexed paths, including validated same-name mirrors; it rechecks the current preferred body and preserves the old observation. Failed or ambiguous reads nominate nothing, and explicit Memory requests keep their scope. Nomination grants no factual or mutation authority. Per-entry source suffixes are omitted; omission counts and discovery pointers appear only when needed. Complete indexes are parent-rebuilt, stale-capable discovery metadata; loading never writes them. Cues give way before entries when the budget is tight. The per-turn loader sizes its read buffer from each file, reuses unchanged entry metadata in-process against a device/inode/size/mtime/ctime identity check on a regular non-symlink file, re-verifies root identity for every real read, and memoizes the `git` root probe per canonical project path; a rewritten or replaced entry is never served from reuse. AGENTS extraction can retain a bounded conditional `replacementText` pointer in the same evidence-checked, budgeted transaction instead of losing discoverability.
## Design assessment

The strongest architectural property is the separation between reasoning and mutation: children plan; the parent validates and writes. The main ongoing complexity is `extensions/inject-memory.ts`, which still owns command registration, settings, model selection, injection, child orchestration, UI status, pipeline sequencing, and shutdown cleanup. Future behavior should prefer smaller modules rather than expanding that composition root further.

A completed task that actually read indexed Memory can require correction even when its user request has no learning keywords. Automatic screening and later selection use the same parent-observed, uniquely paired successful read names. This nomination remains active when semantic phase selection is disabled, but never overrides disabled Memory learning or explicit command scope. A nomination starts review of the current preferred record, not a write or a claim of adoption. Current-source collection still precedes planning after successful source edits.

Continual improvement has four separate acceptance conditions: a validated record is stored; a later relevant task reads its exact revision; independently verified new evidence corrects or retires obsolete claims; and later paired tasks improve after including all failures, latency and known or unknown costs. Index delivery, a successful read, an applied correction and a green test suite each establish only their own condition. A held review must retain its original failure and must not be sampled repeatedly until approval. New acceptance and continuous studies use the user-requested Pi 1.2.0 baseline; historical Pi 1.0 evidence remains separate. The retained V47 cohort (2026-10-16) did not complete these conditions: both arms passed their first two tasks, but the learning arm's correction remained held after its independent body worker timed out. This is incomplete coverage, not demonstrated improvement.

Harness needs a separate authority loop: bind the latest actual user correction, revise or retire only the exact auto-owned rule, and verify both the newly allowed action and the restrictions that must remain. A failed semantic judgment cannot silently disable the old rule. Failed-task backfill needs the complete observed failure and current source, then an independently checked change and a later task that exercises the lesson. Merely acknowledging the backlog is not that outcome.

## Current recovery checkpoint (2026-10-17)
Evidence root: `/Users/FradSer/.codex/visualizations/2026/10/08/01a11d01-ec97-7620-923c-0ce430ba8fb3/continuous-learning-recovery-20261011`. Keep historical cohorts and costs there; `empirical-memory-correction-progress.json` records current handoff state. Earlier checkpoints remain in the frozen source manifests.
Goal remains incomplete: prove stored useful Memory, later voluntary use, accepted correction, Harness correction/retirement and failed-task backfill, then paired task improvement with all failures and known/unknown costs. A green source check or saved record is insufficient.
V73 settled failed: owner PID93667/tool session33640 ended exit1;121requests(75model/46Jev),1629.411s. Owner reports transport quiescent/reservation released, source unchanged and no retained owned containers. Use V73 settled-outcome.json; only exclusive owners access global cumulative ledger/reservation files.
Frozen source: `deepseek-pi12-memory-purpose-v73-20261017`; source manifest ec7874ec9620e13eda0c6d9950ce89ed602e68aa614222370a39286109d58e8f; native c83e95654c9784dbdc7deac098ac086a0dd5dda4e1f441cd20af959f45e7f2bf. Wrapper `/private/tmp/cl-continuous-frozen-deepseek-pi12-memory-purpose-v73.py` SHA629b4d96e9487554b171d98e8d9e9a64f036f09b74a109caccc7cd89faab8eaf. Host handoff edits postdate this immutable freeze.
Current output: `continuous-reviewed-deepseek-pi12-memory-purpose-v73/cohort/20261017T124144Z-efc8c9075d19`. Actual learner ccf48749b308 and control3a46851e4e93 match immutable imageb797eec4dc50b49108ade65c68bcca12a0f72f386b1ff1b9cb75e0494cebf99d and CLI1.2.0. Paid containers use the existing Docker bridge for proxy transport; the separate image-only proof used networknone. See `continuous-reviewed-deepseek-pi12-memory-purpose-v73/parent-running-image-proof.json`.
V73 admission: independentcfb32b9f/runtime1bb68f0e verified1365source+9SDK, actual7Pi1.2,87runtime+9SDK image hashes and kit closure. Offline preflight49.362s/0requests passed. Final source gate1985passed/1skip across1986nodes/244disjointmodules; typecheck/pack passed. Named paid synthetic live_smoke remains unrun; install check retains6unrelated missing packages.
Only V73 generation change: NEW Memory with evidenced maintenance purpose/applicability uses existing complete content, exact declaration and supported Why/How. Source-only/legacy interfaces and all runtime TS are unchanged. This fixes a demonstrated format gap, not a demonstrated semantic cause/cure. Preserve DeepSeek4.1Flash/Jev1.14, .9/.8/joint.9, complete evidence, no seeds/forced reads, six tasks and900/230/30/35/7200-second bounds.
Orientation raw checks passed both arms: control40.77s, learner256.26s including learning; ordinary main37.317s/25.287s. Independent native8aba518c found no observed boundary violation. Each piped pnpm test once and showed30AVA passes; pipe0 alone does not establish internal chain exit. All original prefixes and parent chains retained in orientation-native-evidence.
First Memory: `limitFunction_type_contract.md`, revision4a6e5ebd1283ebe79bb692f874768107d1efb1c3aabc294d17871af299c2a218,943bytes, public/private identical. Original draft had Why/How; actual semantic repair removed them. Structural long-citation repair52.689s and semantic repair67.888s completed, both original failures retained. Initial Harness no-npm-use-pnpm revision1f44b553ae9ee9e84377665f529a87edacd44f7c19ef9283b5dfaa060b609da1 persisted. See V73 parent-first-memory-and-harness.json and first-memory-evidence.
Idle learner ordinary main completed161302ms/62original rows/30tools. It voluntarily read the exact943byte Memory before edits: call_17b3785af02347cfa41a6a4c, entries13->14, prefix04980f04e94396ad83387e96b24673cfa461fa781768448ba28d730659883ea7. Exposure is not adoption or benefit. Independent e8382a4f found no prohibited read/write or unchanged failed-check rerun; final pnpm explicitly EXIT0/43AVA. Reporting failure: final claimed17newtests, actual13. New type-file assertions lack explicit execution proof. Do not label complete compliance passed.
Follow the actual idle learning run `run_mvceant0_d8993e2da9a78563`. Last observed proposal rewrites the type contract to add onIdle and creates onIdle_contract.md; not yet a successful correction. Independent body review184004ms/22549output tokens/$0.027213444 reported, both bodies consistent; this does not clear Jev. Sole semantic repair dd01946c-bbe6-4a2b-b127-4cc7ed98d4ee timed out230115ms/exit143, no amendment and no correction write. Learner rawsourcepassed766.21s including learning; baseline idle failed322.94s. This one paired win does not prove learning; invalid correction stopped four later tasks. Known model-reported$0.171104712 plus Jev-estimated$0.027785184 and unknown costs retained; aggregate capture reports incomplete.
Preserve historical outcomes under continuous-reviewed-deepseek-pi12-current-authority-v68, support-purpose-v69, credential-isolation-v70, preservation-generation-v71 and history-field-bindings-v72 (same continuous-reviewed-deepseek-pi12 prefix): each settled-outcome.json retains failures/costs. V71 already had explanatory declared-type knowledge and still held. V72 corrected missing field/history references but correction0 after230176ms timeout; four later tasks unrun. Prior wire/local verification remains in pi12-history-field-bindings-local-repair-20261017 and previousV72PaidStudy in empirical-memory-correction-progress.json.
Version diagnostic `v72-semantic-version-readonly-diagnostic-20261017` failed:4Jev/6.582s/$0.00410046estimated+unknown, last settled cumulative9723fromowner. Missing model parent directories lost typed answer captures; all4usage rows retained. No version conclusion, approval or repeat cells. Original failed owner/admission unchanged; separate future-reference real capture RED/GREEN fix independentlyc310e1d3 passed0external. Current derived cumulative9844=prior owner9723+121; no global ledger read. Independent106c677a demonstrated that onIdle waits for work added inside a job but can resolve before caller-facing Promise.then adds work: an applicability ambiguity, not a proved instantaneous-idle runtime bug or cause of Jev holds. Current local repair: shared initial/repair guidance preserves queued-at-completion versus future caller Promise continuation scope; no project fact is seeded. RED1failed/GREEN10passed; tsc/pack passed; independent6b8dfd3d and actual Pi1.2 initial+repair native490bfc1a passed0external. User requested quick closeout: unfinished full package check session19569 stopped; no full-suite pass claimed. Retain3disjoint module shard logs /private/tmp/cl-queue-phase-final-shard-{0,1,2}.log and1986node/244module partition. Verification pi12-queue-timing-scope-repair-20261017/verification.json. Actual V73 hold observation parent-semantic-hold-observation.json retains20complete counter responses, new source-support coherence.83/.74 and grounding.73/.66; overall46capture remains incomplete. No historical semantic/timeout cause or useful correction is inferred. No paid owner is active; no old plan is rejudged for approval.

The two Memory roots are intentionally asymmetric rather than ordinary override layers. The private root is the complete learned state; project `.memory/` is a synchronized, sanitized collaboration surface. Harness configuration remains a four-layer user-owned override system because its personal and shared JSON policies have different configuration semantics from Memory privacy mirroring.
## Locked acceptance decisions

- Memory has exactly two roots: readable Harness/private agent Memory and project-shared `.memory/`.
- The private directory, lock, and runs scope use the same flat sanitized canonical path without hashes; sanitizer collisions are refused by a canonical-cwd ownership binding outside entry roots.
- Overlong names fail explicitly instead of truncating or falling back to hashes.
- Project `.memory/` contains only sanitized safe Memory.
- Safe Memory synchronizes both ways and remains byte-identical after normalization/application.
- Private Memory never appears in project `.memory/`.
- The parent owns all mutation, validation, rollback, index rebuilding, and receipts. Automatic and manual consolidation may permanently delete Memory only with a stale verdict that permits removal plus a mechanically verifiable preservation target; receipt change counts are bound back to the validated plan. Generated shell commands cannot bulk-delete either project Memory directory or the private Pi Memory root.
- Harness retains its four-layer flat-rule model plus read-only compatibility execution of installed declarations. Legacy files remain unchanged; additions preserve their protections. @docs/adr/0005-preserve-installed-harness-protections.md records why compatibility, not global lockout or silent retirement, is required.
## Full maintenance input

Full maintenance first extracts grounded new knowledge even with an empty Memory corpus. Only when the current frozen context lacks real user/tool content can it use one recent same-project session through the parent-owned bounded reader. Receipts identify the session and source digest. Pi projection governs retained evidence; malformed graphs and unsafe sources are refused. With no evidence or existing Memory, no workers run. Automatic and default manual learning retain the current Task Slice scope. Backlog status inspection is read-only; the explicit backfill command and bounded automatic recovery are separately authorized replay paths.
## Audit safety boundaries

Incomplete Harness configuration or scanning preserves complete prior text guidance only after the parent validates its exact scoped header. Historical unscoped guidance remains untouched in history but is not delivered; a non-context notice reports that limitation.

Variable Memory names, descriptions and paths use an escaped untrusted data block in a structured run-start section. The context hook removes all old injection messages and adds nothing; the fixed retrieval protocol controls discovery. Fixed protocol, discovery data and automatic-learning guidance each own a named section, including under `customPrompt`. Disabled learning clears its section. Missing structured run-start sections fail explicitly; guidelines are not a fallback. This is an authority boundary, not evidence of resistance to every model-level injection.

Workers have no native filesystem, shell or network tools. An explicit package-owned extension registers only `learning_read`; failure to load it grants no fallback tool. Incremental Memory may read only its dossier. Full Memory may inspect its frozen snapshot, Memory roots and project root; Harness/AGENTS may inspect their supplied snapshot/dossier and project root. Every read rejects outside paths, sensitive material, symbolic links, non-regular files and changed file identities. Tool output is bounded and paged. Separate immutable extension files prevent concurrently planned phases from overwriting each other's read policy.

When a bounded Task Slice omits evidence, every apply policy is downgraded to propose (off stays off), including explicit incremental learning. Receipts report the omission. Normalization and all durable learning surfaces therefore remain read-only. Meaningful automatic outcomes produce one compact expandable receipt without triggering a turn; routine noop/screened outcomes remain quiet.

Management uses an independent 4,096-entry inventory, 32-row pages and on-demand body reads. Memory, history and Harness details page their full supported text in bounded 4,000-character pages and retain exact paths. Saved proposals explain how to obtain a fresh plan; they are never blindly applied.

Run snapshots, planner output, receipts and history remain private audit artifacts and have no automatic expiry. This change does not delete existing artifacts or claim an aggregate disk cap; owners decide retention separately from learning correctness.

Semantic correction of an already proposed Memory candidate uses a parent-bound
`incremental-memory-amendment`: the worker returns only a candidate ID, corrected
content and original-source citations. The ID binds its original array, position
and complete predecessor. The parent retains its name, operation kind, privacy
and other metadata; held-field preservation and full citation/semantic validation
still follow. Omission retains an unresolved candidate, and an empty amendment
cannot acknowledge correction. Previously valid incremental deltas remain readable
under their existing intent checks; moving a new candidate into rewrite operations
remains rejected.

Worker cost evidence uses parent-owned numeric ledgers. Completed requests are summed across the worker, rather than taking the last reply. A failed or incomplete worker keeps its known prefix separately and does not claim complete receipt usage. Each ledger has an opaque parent identity; the continuous study excludes it from additional costs only when an actual persistent receipt contains the same identity and identical usage. A completed worker without that receipt remains a cost-bearing orphan. Historical missing usage, interrupted calls and unverified billing remain unknown. These accounting records never authorize learning or prove downstream improvement.

A proposed or rewritten Memory body receives an independent internal-consistency judgment in addition to source support and complete counterevidence review. Correct main clauses cannot compensate for incompatible negated clauses or observable outcomes. Contradiction is unsupported candidate content, so the existing bounded semantic amendment can correct it without changing targets, privacy or intent. Uncertain or absent answers still hold the candidate. Candidate review checklists bind the additional judgment; older incomplete reviews cannot authorize independent application.

Incremental Memory planners receive the complete digest-checked Learning Dossier directly, using the same lossless indexed evidence projection as the scoped reader. They have no tools; the original snapshot, predecessor bodies, namespace, citations and all parent mutation gates remain authoritative. No entries are trimmed for this transport. Numeric worker usage is queued to private atomic ledgers as assistant events complete, and queue draining precedes cleanup. Full maintenance retains its existing scoped-reader path. This reduces redundant evidence retrieval, not a claim that the v33 timeout's exact read sequence is known.

Explicit private Memory review requires per-run native confirmation before maintenance audit/selection; newly generated private candidates ask before semantic review. Clone the original judge's frozen service/model/scopes and only change private review permission. Never re-read configuration after confirmation and accidentally disable validation. Headless/declined preflight has zero model calls and known zero usage, remains failed, and preserves backlog. Controlled consent/write tests prove routing only; actual learning quality is separate.
