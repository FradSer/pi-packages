# pi-continual-learning

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
