---
name: keyboard-orphaned-unread-cleanup
description: @fradser/pi-keyboard cleans up orphaned unread glow records left by unexpectedly-exited sessions at session start; it deliberately has NO time-based auto-return-to-idle — a live unread session keeps green
type: project
---

## Why

The "unread chat" green light comes from `onAgentSettled` writing a `settled`/`hasUnread:true` glow record. If a session exits **unexpectedly** (crash, SIGKILL, terminal closed without a clean `session_shutdown`), `onShutdown`/`removeSessionGlowState` never runs and that unread record is orphaned on disk. Left unchecked, these orphaned unread records pile up ("挤压") and keep the physical keyboard green even though no session is actually waiting on the user.

FradSer explicitly rejected a **time-based auto-return to white**: no "after 5 minutes unread decays back to idle" logic. The only acceptable behavior is cleaning up records of sessions that are actually no longer alive; a genuine live unread session must keep green.

## How to apply

- `packages/keyboard/src/global-sessions.ts` exports `pruneOrphanedGlowStates(): number` — sweeps the whole `~/.pi/agent/directory-sessions` registry and removes glow records whose owning PID is dead, returning how many it removed. It only deletes dead-process records; live unread records are untouched. No time-based expiry.
- `KeyboardStateMachine.onSessionStart` calls `pruneOrphanedGlowStates()` before the first `syncAndEvaluate`, so residue from crashed/killed sessions is cleared before computing the global state. During the session, `evaluateGlobalLightingState` still opportunistically prunes dead-PID records it encounters.
- The pre-existing `maxStaleAgeMs = 5 * 60 * 1000` in `evaluateGlobalLightingState` is the long-standing cross-session staleness skip for OTHER sessions' on-disk records (present since `3a77faf` "fix: sync keyboard unread state globally") — it is NOT a self-session auto-return and was left unchanged.
- Test seam: `getRegistryDir()` honors `PI_DIRECTORY_SESSIONS_DIR` so tests can point at a temp registry and never touch the real one (`test_orphaned_unread_records_from_dead_sessions_are_pruned` writes a dead-PID and a live-PID record, asserts only the dead one is removed).
- BDD: `packages/keyboard/features/keyboard.feature` has the "Orphaned unread record from an unexpectedly-exited session is cleaned up" scenario.
- Do NOT reintroduce a time-decay of unread state (e.g. clearing `hasUnreadChat` in-memory after N minutes) — that was tried and reverted as unwanted.

## Related

[[project_pi_package_conventions]]
