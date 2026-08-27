# pi-continual-learning

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
