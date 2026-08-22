---
name: continue-stale-session-rebase
description: /continue compares the session leaf with the session file on disk and reloads the same file when the view lags, so continuation never forks a sibling branch
type: project

## Why

Session analysis across 153 real pi sessions showed 103 `continue-extension` markers persisted as siblings of the failed turn instead of extending it: the fork point was always the last entry before the failed turn's first error. `pi.sendMessage` appends at `sessionManager.leafId`, so whenever the live view lags the file on disk (a parallel writer appended, or the leaf was rewound), the hidden marker lands on a new branch and the conversation history splits instead of being fully inherited.

## How to apply

- In `packages/utils/extensions/continue.ts`, before any direct or visible continuation, read the session file's last non-header entry id (`readDiskTipEntryId`) and compare it with `ctx.sessionManager.getLeafId()`.
- On divergence, call `ctx.switchSession(sessionFile, { withSession })` to reopen the same file; the fresh `SessionManager` puts the leaf at the true tip, and the shared `performContinuation` runs from the recovered context.
- Only command contexts expose `switchSession`; route idle keyword input ("continue"/"继续") through the internal `__continue` command via `pi.sendUserMessage(..., { expandPromptTemplates: true })` (runtime honors the flag even though 0.84.x published types omit it). While streaming, keep steering the marker directly because a live streaming process owns a current leaf.
- Keep both entry points on the shared `runContinuation`/`performContinuation` path so recovery applies to `/continue`, keyword input, and custom follow-up prompts alike.

## Related

[[continue-recovery]]
[[project_directory_sessions_multi_writer]]
