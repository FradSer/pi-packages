---
name: directory-sessions-multi-writer
description: ~/.pi/agent/directory-sessions/ has two writers per session (utils state + keyboard glow) with different id conventions — reads must merge by pid and exclude own pid
type: project
---

The shared directory-session registry `~/.pi/agent/directory-sessions/<cwd-key>/` receives records from at least two writers with different sessionId conventions for the same physical session:

- `@fradser/pi-utils` (`extensions/sessions.ts`): writes `<sessionFileBasename>.json`, where the basename is pi's native session file name `<timestamp>_<uuid>` — full SessionInfo (status, latestGoal from the user prompt, recap synced by @fradser/pi-recap, modifiedFiles).
- `@fradser/pi-keyboard` (`src/global-sessions.ts`): merges a bare glow record into `<uuid>.json` (pid, cwd, status, hasUnread, updatedAt).

**Why:**
Before 2026-08-22, `cleanAndListDirectorySessions` treated every file as one session, so each live session appeared twice (doubling the `[sessions] listed · N` count and duplicating expanded rows), and the current process leaked in as an "other session" whenever only its glow record matched the id filter.

**How to apply:**
1. Any reader of this registry must dedupe by `pid` (one logical session per owning process): newest record wins mutable scalars; optional detail fields (sessionName/latestGoal/recap/modifiedFiles) are filled from sibling records when missing; `startedAt` prefers the primary's own value — glow records have no startedAt (coerces to 0) so min-across-records would show 1970.
2. Self-exclusion must check `info.pid === process.pid` in addition to the session id — id conventions differ across writers.
3. Registry JSON is not type-checked at rest: normalize on read (`normalizeSessionRecord` — numeric pid/timestamps, status coerced to the known union). Display of free-text fields must sanitize via pi-kit `safeDisplayText` and truncate; status/pid are safe only after normalization.
4. New registry writers should reuse the utils SessionInfo shape instead of inventing a parallel schema.
5. Reference implementation: `mergeSessionsByPid`/`normalizeSessionRecord` in `packages/utils/extensions/sessions.ts`; BDD in `packages/utils/features/sessions.feature`.

## Related

[[monitor-display-pattern]] [[pi-package-conventions]] [[keyboard-orphaned-unread-cleanup]]
