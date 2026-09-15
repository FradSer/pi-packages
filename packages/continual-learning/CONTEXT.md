# Continual-learning architecture and memory ownership

## Current architecture

`pi-continual-learning` improves Pi without changing model weights. It learns across three runtime surfaces:

1. **Memory** stores durable knowledge that is injected into future sessions as untrusted reference data.
2. **Harness** evaluates declarative policies on tool calls, assistant output, and actual file artifacts. Skill-specific prompts are a separate pre-generation context-guidance module.
3. **AGENTS.md consolidation** maintains the small, always-loaded project instruction document and extracts narrower material into Memory or Harness.

Automatic learning and default `/consolidate` operate on one completed **Task Slice**. A metadata-only **Memory Selector** chooses the minimum sufficient related existing Memory, and the parent builds one authoritative **Learning Dossier** containing that Task Slice plus selected bodies. Memory, Harness, and AGENTS.md planners consume the dossier and return only deltas. `/consolidate full` is the explicit exhaustive maintenance path.

Every phase follows the same trust boundary: the parent freezes the task context before asynchronous work, a package-owned child agent runs with discovery disabled and the minimum tools for its mode (none for selection, `read` for incremental Memory, and bounded read-only discovery only for explicit full maintenance), and only the parent validates and applies a bounded structured plan. Memory attempts capture their bound inputs; Harness and AGENTS.md planners share one later-phase immutable capture of the same frozen context. Completion requires parent-owned validation and pre/post receipts; planner prose is never proof of success. Locks, path containment, symlink checks, atomic writes, rollback, output bounds, and shutdown generation checks remain mandatory.

Later-phase failure does not roll back an earlier verified phase. When Memory is selected, it must complete and verify before Harness starts; grounded Harness/AGENTS-only automatic evidence may instead use a verified no-mutation Memory gate. Harness failure leaves Memory intact; AGENTS.md failure leaves both earlier phases intact.

## Harness ownership

Harness configuration has exactly three user-owned layers, plus package defaults:

1. User shared: `~/.pi/agent/harness.json`
2. Project shared: `<project>/.pi/harness.json`
3. Project personal: `<project>/.pi/harness.local.json`

Precedence is project personal over project shared over user shared over built-in defaults. Policy names and skill-prompt names are the addressable override keys. The obsolete user-personal `~/.pi/agent/harness.local.json` and project `.pi/agent/harness*.json` paths are not loaded, displayed, or targeted.

Automatic Harness consolidation writes only `<project>/.pi/harness.local.json`. The shared Harness layers are read-only inputs.

## Memory ownership: two synchronized roots

Memory deliberately uses two physical roots rather than copying the three Harness configuration layers:

1. **Harness/private Memory**: `~/.pi/agent/memory/<escaped-readable-prefix>--<full-sha256-scope-key>/`
2. **Project shared Memory**: `<project>/.memory/`

For `/Users/FradSer/Developer/FradSer/cerberus`, the private directory remains readable while carrying a collision-resistant identity:

```text
~/.pi/agent/memory/-Users-FradSer-Developer-FradSer-cerberus--<64hex>/
```

The prefix is derived from the canonical project working directory, normalized to bounded ASCII, and capped at 174 bytes. The `--` suffix is the full 64-character lowercase SHA-256 scope key, keeping the complete component within 240 bytes and preventing different paths with the same readable prefix from sharing Memory.

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

## Legacy directory migration

The opaque SHA-256 project directory, the collision-prone readable directory, and the older readable directory that preserved whitespace must migrate to the readable-prefix-plus-scope-key directory. Migration is one-way and has no permanent compatibility read fallback:

- Valid Memory merges into the collision-resistant destination without overwriting conflicts.
- Private markers from legacy indexes transfer only for files whose bytes were created in or match the destination; a retained conflicting source cannot reclassify different canonical bytes.
- Source and destination roots, entries, and indexes reject symlinks.
- A failed application restores the destination predecessor and leaves every source intact.
- A migrated source is removed only after successful application and only when every source entry was recognized; unsupported or conflicting sources remain intact.

## Commands and settings

- `/memory` manages the consolidation model, auto-memory toggle, instructions, and opens the Harness/private Memory directory.
- `/consolidate` incrementally learns from the current completed Task Slice.
- `/consolidate full` explicitly runs exhaustive Memory, Harness, and AGENTS.md maintenance.
- `/consolidate no-context` performs the context-disabled full Memory path and skips Harness and AGENTS.md, which require task evidence.
- `/harness` displays active policies and creates rules in the selected Harness configuration layer.

Auto-memory enables learning after `agent_settled` for real user input. It coalesces pending completed tasks, ignores extension-generated continuations as independent triggers, and waits for the full pipeline in headless mode. Existing Memory remains available regardless of the toggle. The main model is not asked to write memories directly; the parent validates new-memory proposals even when the existing corpus is empty.

New memories live in a separate `newMemories` proposal array while `selected` remains the exact parent-owned existing-file list. Snapshot message indices and quotes ground the proposals; preferences stay private and credentials are rejected. AGENTS.md extraction uses the same explicit safe/private classification, persists exact predecessor state in a pre-apply recovery receipt, and applies Memory, Harness, instruction, and post-receipt changes in one rollback boundary. On the next session start, an orphan pre receipt without a matching post receipt is validated against the canonical project scope and restored before new learning starts. Harness learning verifies user/tool evidence and executes positive and negative evaluator cases. Shared, built-in, and manually authored policies remain protected from automatic replacement or disabling.

Post-generation policies explicitly choose `output` or `artifact`. Artifact checks read actual bounded workspace file contents, including explicit paths for command-produced files. Unreadable or unsafe artifacts are unsupported, not verified. Output checks run after streaming and can request bounded corrections but cannot hide the original response.

## Design assessment

The strongest architectural property is the separation between reasoning and mutation: children plan; the parent validates and writes. The main ongoing complexity is `extensions/inject-memory.ts`, which still owns command registration, settings, model selection, injection, child orchestration, UI status, pipeline sequencing, and shutdown cleanup. Future behavior should prefer smaller modules rather than expanding that composition root further.

The two Memory roots are intentionally asymmetric rather than ordinary override layers. The private root is the complete learned state; project `.memory/` is a synchronized, sanitized collaboration surface. Harness configuration remains a three-layer override system because its personal and shared JSON policies have different configuration semantics from Memory privacy mirroring.

## Locked acceptance decisions

- Memory has exactly two roots: readable Harness/private agent Memory and project-shared `.memory/`.
- The private directory name combines a bounded human-readable canonical-path prefix with the full scope hash, so recognizable prefixes cannot collide.
- A hash-only directory is not the steady-state format.
- Project `.memory/` contains only sanitized safe Memory.
- Safe Memory synchronizes both ways and remains byte-identical after normalization/application.
- Private Memory never appears in project `.memory/`.
- The parent owns all mutation, validation, rollback, index rebuilding, and receipts. Automatic and manual consolidation may permanently delete Memory only with a stale verdict that permits removal plus a mechanically verifiable preservation target; receipt change counts are bound back to the validated plan. Generated shell commands cannot bulk-delete either project Memory directory or the private Pi Memory root.
- Harness retains its separate three-layer policy model.
