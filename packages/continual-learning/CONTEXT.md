# Continual-learning architecture and memory ownership

## Current architecture

`pi-continual-learning` improves Pi without changing model weights. It learns across three runtime surfaces:

1. **Memory** stores durable knowledge that is injected into future sessions as untrusted reference data.
2. **Harness** resolves identified flat rules for new authoring: skill/text guidance and Bash messages or execution gates. A read-only compatibility boundary preserves installed tool-call, output/artifact, and skill-prompt declarations without weakening their semantics or rewriting configuration.
3. **AGENTS.md consolidation** maintains the small, always-loaded project instruction document and extracts narrower material into Memory or Harness.

Automatic learning and default `/consolidate` operate on one completed **Task Slice**. A metadata-only **Memory Selector** chooses the minimum sufficient related existing Memory, and the parent builds one authoritative **Learning Dossier** containing that Task Slice plus selected bodies. Memory, Harness, and AGENTS.md planners consume the dossier and return only deltas. `/consolidate full` is the explicit exhaustive maintenance path.

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

Harness configuration has exactly three user-owned layers, plus package defaults:

1. User shared: `~/.pi/agent/harness.json`
2. Project shared: `<project>/.pi/harness.json`
3. Project personal: `<project>/.pi/harness.local.json`

Precedence is project personal over project shared over user shared over built-in defaults. Flat rule IDs are the addressable override keys across new selectors; nearer declarations replace a whole rule. Installed legacy policy/skill-prompt containers retain their original name-based override and disablement semantics through compatibility execution, including the historical effect of cumulative disabled names on same-ID flat rules. Compatible data is a notice, not an error; loading never migrates files. The obsolete user-personal `~/.pi/agent/harness.local.json` and project `.pi/agent/harness*.json` paths are not loaded, displayed, or targeted.

Direct authoring and automatic Harness consolidation default to `<project>/.pi/harness.json`. Other layers are read-only inputs to consolidation. Project personal `.pi/harness.local.json` is selected only by an explicit personal-configuration request; a global local variant is unsupported.

## Memory ownership: two synchronized roots

Memory deliberately uses two physical roots rather than copying the three Harness configuration layers:

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

The flat escaped canonical-path directory is the sole agent-private runtime root. Other layouts, including hash-only and hash-suffixed roots, remain untouched. Memory loading and consolidation do not discover, read, import, rename, or delete them, and there is no compatibility fallback or migration interface. Existing flat roots matching the current sanitizer are used directly.

## Commands and settings

- `/memory` manages the consolidation model, auto-memory toggle, instructions, and opens the Harness/private Memory directory.
- `/consolidate` incrementally learns from the current completed Task Slice.
- `/consolidate full` explicitly runs exhaustive Memory, Harness, and AGENTS.md maintenance.
- `/consolidate no-context` performs the context-disabled full Memory path and skips Harness and AGENTS.md, which require task evidence.
- `/harness` displays resolved rules and creates rules in the selected Harness configuration layer. Unsupported or ambiguous requests do not create empty files or authorize edits elsewhere.

Auto-memory enables learning after `agent_settled` for real user input. It coalesces pending completed tasks, ignores extension-generated continuations as independent triggers, and waits for the full pipeline in headless mode. Existing Memory remains available regardless of the toggle. The main model is not asked to write memories directly; the parent validates new-memory proposals even when the existing corpus is empty.

New memories live in a separate `newMemories` proposal array while `selected` remains the exact parent-owned existing-file list. Snapshot message indices and quotes ground the proposals; preferences stay private and credentials are rejected. AGENTS.md extraction uses the same explicit safe/private classification, persists exact predecessor state in a pre-apply recovery receipt, and applies Memory, Harness, instruction, and post-receipt changes in one rollback boundary. On the next session start, an orphan pre receipt without a matching post receipt is validated against the canonical project scope and restored before new learning starts. Harness learning verifies user/tool evidence and executes positive and negative evaluator cases for each selector. Revision-bound `learnedRules` provenance protects manual edits; shared, built-in, personal, invalid, disabled, and manually authored identities cannot be overwritten by automatic learning.

Skill guidance names its invocation task in the model-visible message. Text guidance retains its selector and subject scope even when triggered by historical conversation. New flat guidance uses persistent tail messages, never per-turn system-prompt changes; installed legacy skill targets preserve their configured delivery semantics. A delivery revision includes its message format, so a restored unscoped delivery receives one scoped replacement without rewriting history. Matching and delivery do not prove semantic compliance. Output/artifact checks remain available for installed declarations, without becoming a fourth flat-rule selector or replacing project verification.

Memory injection carries bounded relevance descriptions, one declared body root per source, omission counts, and discovery pointers. Complete indexes are parent-rebuilt, stale-capable discovery metadata; loading never writes them. Descriptions front-load when the memory is relevant, and cues give way before entries when the budget is tight. The per-turn loader sizes its read buffer from each file, reuses unchanged entry metadata in-process against a device/inode/size/mtime/ctime identity check on a regular non-symlink file, re-verifies root identity for every real read, and memoizes the `git` root probe per canonical project path; a rewritten or replaced entry is never served from reuse. AGENTS extraction can retain a bounded conditional `replacementText` pointer in the same evidence-checked, budgeted transaction instead of losing discoverability.

## Design assessment

The strongest architectural property is the separation between reasoning and mutation: children plan; the parent validates and writes. The main ongoing complexity is `extensions/inject-memory.ts`, which still owns command registration, settings, model selection, injection, child orchestration, UI status, pipeline sequencing, and shutdown cleanup. Future behavior should prefer smaller modules rather than expanding that composition root further.

The two Memory roots are intentionally asymmetric rather than ordinary override layers. The private root is the complete learned state; project `.memory/` is a synchronized, sanitized collaboration surface. Harness configuration remains a three-layer override system because its personal and shared JSON policies have different configuration semantics from Memory privacy mirroring.

## Locked acceptance decisions

- Memory has exactly two roots: readable Harness/private agent Memory and project-shared `.memory/`.
- The private directory, lock, and runs scope use the same flat sanitized canonical path without hashes; sanitizer collisions intentionally share scope.
- Overlong names fail explicitly instead of truncating or falling back to hashes.
- Project `.memory/` contains only sanitized safe Memory.
- Safe Memory synchronizes both ways and remains byte-identical after normalization/application.
- Private Memory never appears in project `.memory/`.
- The parent owns all mutation, validation, rollback, index rebuilding, and receipts. Automatic and manual consolidation may permanently delete Memory only with a stale verdict that permits removal plus a mechanically verifiable preservation target; receipt change counts are bound back to the validated plan. Generated shell commands cannot bulk-delete either project Memory directory or the private Pi Memory root.
- Harness retains its three-layer flat-rule model plus read-only compatibility execution of installed declarations. Legacy files remain unchanged; additions preserve their protections. @docs/adr/0005-preserve-installed-harness-protections.md records why compatibility, not global lockout or silent retirement, is required.
