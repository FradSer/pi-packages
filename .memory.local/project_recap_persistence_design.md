---
name: recap-persistence-design
description: @fradser/pi-recap persists recap across restarts using pi.appendEntry custom session entries, restoring on session_start without redundant LLM generation
type: project
---

## Why

Prior to session entry persistence, `@fradser/pi-recap` only synced recaps to the ephemeral `~/.pi/agent/directory-sessions/` registry (which is pruned on session shutdown or dead PID cleanup). When Pi was restarted or a session resumed, `readDirectorySessionRecap` failed to find a saved recap and triggered a redundant LLM recap generation from scratch every time.

## How to apply

- When generating or updating a recap in `packages/recap/extensions/index.ts`, append a custom entry to the session file via `pi.appendEntry("recap", { recap: text, language: config.language, timestamp: Date.now() })`.
- Also update `syncDirectorySessionRecap(...)` for multi-session awareness across parallel sessions.
- In `packages/recap/extensions/recap.ts`, `extractLatestSavedRecap(entries: RecapSessionEntry[])` scans backwards through the session branch entries (`ctx.sessionManager.getBranch()`) to find the latest custom entry where `entry.type === "custom" && entry.customType === "recap"`, supporting both `{ recap: string }` and `{ text: string }` data formats.
- On `session_start`, check `extractLatestSavedRecap(branch)` before checking directory sessions. If a saved recap is found:
  1. Set `currentRecap = savedRecap;`.
  2. Populate `completedRequestKey` matching the last exchange so subsequent checks know it has already been recapped.
  3. Update the `aboveEditor` widget with the restored recap.
  4. Skip triggering `performRecap(ctx)`.
- If no saved recap exists and the session has history, `performRecap(ctx)` is triggered only once to bootstrap the initial recap, which is then persisted.
- Unchanged recaps (`text === currentRecap`) skip appending duplicate entries to keep the session log compact.

## Related

[[pi-package-conventions]]
