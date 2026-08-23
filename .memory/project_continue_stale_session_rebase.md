---
name: continue-stale-session-rebase
description: /continue reloads only genuinely unseen persisted entries while preserving a user-selected session-tree leaf
type: project

## Why

The original disk-tip rebase fixed stale views that missed entries written by another process, but it also treated deliberate tree navigation as stale. After the user selected an earlier node, the append-only session file still contained the abandoned failed branch; reopening the file reset the leaf to its physical last entry and made `/continue` resume the abandoned failure instead of the selected node.

## How to apply

- In `packages/utils/extensions/continue.ts`, read the last valid persisted entry id with `readDiskTipEntryId`.
- Call `needsSessionReload(ctx.sessionManager, diskTipEntryId)`, which reloads only when `getEntry(diskTipEntryId) === undefined`. An unknown tip means another process appended history that the active session has never loaded.
- If the disk tip is already known, do not compare it to `getLeafId()` and do not reload. A known tip with a different leaf is a deliberate tree selection; the selected leaf is authoritative and the next append creates the continuation branch there.
- Keep idle keyword input routed through the public `/continue` command via `pi.sendUserMessage("/continue", { expandPromptTemplates: true })`. While streaming, send the direct marker against the live session.
- The continuation classifier uses only the active `getBranch()` path, so abandoned branches cannot determine what gets resumed.

## Related

[[continue-recovery]]
[[project_directory_sessions_multi_writer]]
