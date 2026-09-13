# Continual-learning architecture and memory ownership

## Current architecture

`pi-continual-learning` improves Pi without changing model weights. It learns across three runtime surfaces:

1. **Memory** stores durable knowledge that is injected into future sessions as untrusted reference data.
2. **Harness** evaluates declarative policies on tool calls, assistant output, and actual file artifacts. Skill-specific prompts are a separate pre-generation context-guidance module.
3. **AGENTS.md consolidation** maintains the small, always-loaded project instruction document and extracts narrower material into Memory or Harness.

Automatic learning after settled user tasks and explicit `/consolidate` runs use these phases in order:

1. Memory consolidation
2. Harness consolidation
3. Project `AGENTS.md` consolidation

Every phase follows the same trust boundary: the parent freezes the task context before asynchronous work, a `--no-extensions` child performs read-only planning, and only the parent validates and applies a bounded structured plan. Each phase snapshots that same frozen context, including retries. Completion requires parent-owned validation and pre/post receipts; planner prose is never proof of success. Locks, path containment, symlink checks, atomic writes, rollback, output bounds, and shutdown generation checks remain mandatory.

Later-phase failure does not roll back an earlier verified phase. Memory must complete and verify before Harness starts. Harness failure leaves Memory intact; AGENTS.md failure leaves both earlier phases intact.

## Harness ownership

Harness configuration has exactly three user-owned layers, plus package defaults:

1. User shared: `~/.pi/agent/harness.json`
2. Project shared: `<project>/.pi/harness.json`
3. Project personal: `<project>/.pi/harness.local.json`

Precedence is project personal over project shared over user shared over built-in defaults. Policy names and skill-prompt names are the addressable override keys. The obsolete user-personal `~/.pi/agent/harness.local.json` is not loaded, displayed, or targeted.

Automatic Harness consolidation writes only `<project>/.pi/harness.local.json`. The shared Harness layers are read-only inputs.

## Memory ownership: two synchronized roots

Memory deliberately uses two physical roots rather than copying the three Harness configuration layers:

1. **Harness/private Memory**: `~/.pi/agent/memory/<escaped-project-path>/`
2. **Project shared Memory**: `<project>/.memory/`

For `/Users/FradSer/Developer/FradSer/cerberus`, the private directory is readable and path-derived:

```text
~/.pi/agent/memory/-Users-FradSer-Developer-FradSer-cerberus/
```

The escaped project path is derived from the canonical project working directory by replacing path separators and whitespace runs with `-`. For example, `/Users/FradSer/Documents/Home Lab` becomes `-Users-FradSer-Documents-Home-Lab`. It replaces the temporary SHA-256 directory naming: the on-disk scope must be recognizable to a human, contain no whitespace, and not be an opaque digest.

The two roots have different privacy roles:

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

The opaque SHA-256 project directory introduced during the abandoned three-layer experiment, and an older readable directory that preserved whitespace, must migrate to the normalized escaped-project-path directory. The migration is one-way and has no permanent compatibility read fallback:

- If only the old opaque directory exists, move its valid Memory into the readable private directory.
- Existing files in the readable destination win conflicts.
- Preserve private markers from the old index.
- Rebuild the readable private index after migration.
- Remove the migrated opaque source only after successful application.

Older dash-encoded directories already matching the readable escaped project path are the desired destination, not legacy input.

## Commands and settings

- `/memory` manages the consolidation model, auto-memory toggle, instructions, and opens the Harness/private Memory directory.
- `/consolidate` manually runs Memory, Harness, and AGENTS.md consolidation in sequence.
- `/consolidate no-context` performs the context-disabled Memory path and skips Harness and AGENTS.md, which require session evidence.
- `/harness` displays active policies and creates rules in the selected Harness configuration layer.

Auto-memory enables learning after `agent_settled` for real user input. It coalesces pending completed tasks, ignores extension-generated continuations as independent triggers, and waits for the full pipeline in headless mode. Existing Memory remains available regardless of the toggle. The main model is not asked to write memories directly; the parent validates new-memory proposals even when the existing corpus is empty.

New memories live in a separate `newMemories` proposal array while `selected` remains the exact parent-owned existing-file list. Snapshot message indices and quotes ground the proposals; preferences stay private and credentials are rejected. Harness learning verifies user/tool evidence and executes positive and negative evaluator cases. Shared, built-in, and manually authored policies remain protected from automatic replacement or disabling.

Post-generation policies explicitly choose `output` or `artifact`. Artifact checks read actual bounded workspace file contents, including explicit paths for command-produced files. Unreadable or unsafe artifacts are unsupported, not verified. Output checks run after streaming and can request bounded corrections but cannot hide the original response.

## Design assessment

The strongest architectural property is the separation between reasoning and mutation: children plan; the parent validates and writes. The main ongoing complexity is `extensions/inject-memory.ts`, which still owns command registration, settings, model selection, injection, child orchestration, UI status, pipeline sequencing, and shutdown cleanup. Future behavior should prefer smaller modules rather than expanding that composition root further.

The two Memory roots are intentionally asymmetric rather than ordinary override layers. The private root is the complete learned state; project `.memory/` is a synchronized, sanitized collaboration surface. Harness configuration remains a three-layer override system because its personal and shared JSON policies have different configuration semantics from Memory privacy mirroring.

## Locked acceptance decisions

- Memory has exactly two roots: readable Harness/private agent Memory and project-shared `.memory/`.
- The private directory name is derived from the canonical project path and remains human-readable.
- Opaque hash directory names are not the steady-state format.
- Project `.memory/` contains only sanitized safe Memory.
- Safe Memory synchronizes both ways and remains byte-identical after normalization/application.
- Private Memory never appears in project `.memory/`.
- The parent owns all mutation, validation, rollback, index rebuilding, and receipts.
- Harness retains its separate three-layer policy model.
