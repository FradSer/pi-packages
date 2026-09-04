# Continual-learning layer alignment

## Goal

Memory and harness use the same three-layer ownership and precedence model. The obsolete user-personal harness layer is removed rather than retained as a compatibility fallback.

## Locked decisions

### Shared layer model

Both surfaces resolve layers from broadest to narrowest:

1. User shared
2. Project shared
3. Project personal

The effective precedence is project personal over project shared over user shared. A definition at a narrower layer replaces the same addressable name from broader layers.

### Harness paths

- User shared: `~/.pi/agent/harness.json`
- Project shared: `<project>/.pi/harness.json`
- Project personal: `<project>/.pi/harness.local.json`

`~/.pi/agent/harness.local.json` is no longer discovered, displayed, or targeted. `/harness --global` and `/harness --user` target the remaining user shared file.

### Memory paths

- User shared: `~/.pi/agent/memory/`
- Project shared: `<project>/.memory/`
- Project personal: `<project>/.memory.local/`

Operational files such as settings, locks, run artifacts, and legacy project-scope directories remain below the agent memory root but are not memory entries. Only valid memory Markdown basenames are loaded as user-shared entries.

Memory files resolve by filename with the same precedence as harness policy names: project personal replaces project shared, which replaces user shared. `MEMORY.md` remains an index and is never injected as an entry.

### Consolidation ownership

Automatic consolidation writes only the project-personal layer for both surfaces:

- Memory: `<project>/.memory.local/`
- Harness: `<project>/.pi/harness.local.json`

The planners remain read-only. The parent validates plans, applies changes atomically, rebuilds indexes, and writes pre/post receipts. Shared user and project layers are inputs and are never mutated by automatic consolidation.

### Privacy and migration

Project-personal memory is not mirrored into project-shared memory. The old canonical-plus-public-mirror behavior is replaced by ordinary layered resolution.

Existing project-scoped harness memory under `~/.pi/agent/memory/<scope-key>/` is migrated into `<project>/.memory.local/` only when the new project-personal directory does not already contain the same filename. Existing new-layer content wins. No backward-compatible read fallback remains after migration.

### Commands

- `/memory` opens the project-personal memory directory.
- `/consolidate` processes the resolved three-layer memory surface, writes memory changes to project personal, then processes harness and `AGENTS.md` as before.
- `/consolidate no-context` keeps its existing restriction: harness and `AGENTS.md` phases are skipped.

## Acceptance summary

- No runtime reference to a user-personal harness layer remains.
- Memory and harness expose the same three ownership layers and precedence.
- Consolidation never mutates either shared layer.
- Existing project-local private memory is migrated without overwriting newer explicit project-personal files.
- Features, tests, README, and command diagnostics describe the three-layer model consistently.
