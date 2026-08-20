# Memory Plugin

Native pi `/memory` command for bounded project memory injection and parent-owned consolidation. It has no skill surface and honors Pi's configured agent directory.

Memory roots:

1. `<agent-dir>/memory/<sha256(canonical-project-cwd)>/` — private harness memory, written first
2. `<project>/.memory/` — safe, git-tracked mirror written only for explicitly safe files

`<agent-dir>` is resolved through Pi's `getAgentDir()` and may be overridden with `PI_CODING_AGENT_DIR`. The hashed project scope prevents punctuation-based path collisions. Private memories, credentials, and personal information never enter the public mirror.

**Version**: 0.2.5

## Installation

```bash
pi install npm:@fradser/pi-memory
# or from this repository
pi install /path/to/pi-packages/packages/memory
```

## Usage

Type `/memory` to open the management menu. Type `/consolidate` to start a background run without opening the menu.

```text
Auto-memory: on

1. Select memory model
2. Enter provider/model manually
3. Consolidate memory now
4. Edit user instructions
5. Edit project instructions
6. Open memory folder
7. Toggle auto-memory
```

- **Auto-memory** is on by default. It adds bounded capture guidance; existing memory is injected independently of the toggle.
- **Memory model** accepts one complete `provider/model` reference. Menu selection and manual input use the same allowlist. Invalid persisted configuration is preserved and surfaced instead of being overwritten.
- **Consolidate memory now** starts a single-flight parent-owned transaction. `/consolidate no-context` intentionally disables session-context capture.
- **Instructions** use Pi's resolved context resource when available, including overrides and ancestor files.
- **Open memory folder** opens the configured harness directory, not a hard-coded home path.

## Consolidation transaction

The parent extension owns the run from start to finish:

1. Acquire a cross-process project lock and create a private `0700` run directory.
2. Capture an immutable branch/context snapshot before launching the worker. `no-context` writes an explicit disabled-context manifest.
3. Launch a no-extension, read-only worker with only `read`, `grep`, `find`, and `ls` tools. The worker receives run paths and metadata, never provider credentials or a live session file.
4. Accept exactly one bounded structured JSON plan. Progress, prose, `PASSED` text, and validator-like output are not evidence.
5. Run `validate-consolidate.py` before mutation. The parent applies only selected, validated operations with atomic writes; unrelated files are untouched.
6. Rebuild the scoped indexes, run full post-apply validation, and write a receipt bound to the run, scope, exact plan artifact bytes, selected files, and final hashes.
7. Report success only after the parent-owned receipt and privacy/mirror checks verify the resulting state. Timeout, shutdown, spawn failure, stale identity, lock contention, and validation failure release the run without success notification.

An empty selected scope is a verified no-op. Global public-mirror repair is not part of scoped consolidation and requires a separate explicit confirmation.

## Memory loading limits

Only direct regular Markdown files with a strict lower-case `.md` basename are loaded. Symlinked roots/files and non-regular entries are rejected. Loading is deterministic, harness memory shadows a public duplicate, and injection is bounded by file count, per-file size, and total size. Injected content is labeled untrusted reference data and must not be treated as instructions.

## Files

```text
memory/
├── index.ts
├── extensions/inject-memory.ts
├── extensions/consolidation-run.ts
├── extensions/memory-files.ts
├── extensions/memory-paths.ts
├── extensions/config.ts
├── procedures/consolidate.md
├── scripts/validate-consolidate.py
├── features/consolidate.feature
├── features/validate-consolidate.feature
└── tests/
```
