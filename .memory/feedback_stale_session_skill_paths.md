---
name: stale-session-skill-paths
description: pi caches package/skill paths at session startup — after restructuring a repo (e.g. top-level → packages/), old open sessions throw ENOENT on /skill:*
type: feedback
---

When a pi session is started, it resolves package paths from `~/.pi/agent/settings.json` once and holds skill file locations in memory for the whole session. If the repo layout changes afterwards (e.g. `pi-packages/git-agent/` moved to `pi-packages/packages/git-agent/`), any already-running session still points skills at the old paths and `/skill:commit` fails with `ENOENT ... open '.../pi-packages/git-agent/skills/commit/SKILL.md'`.

**Why:**
Observed Aug 12: after the pi-packages monorepo restructure into `packages/`, sessions started before the settings.json update produced exactly this ENOENT (missing `packages/` segment), even though the file existed at the new path and settings.json was already corrected. pi loads skills fresh per session — there is no persistent skill cache — so a restart fully fixes it.

**How to apply:**
1. When diagnosing a skill/extension ENOENT whose path is missing a directory segment, first diff the failing path against the actual file location; if the repo was recently restructured (or settings.json edited), the running session is stale.
2. Verify `settings.json` resolves: from `~/.pi/agent`, each local package entry is relative to `~/.pi/agent` and must point at a dir containing `package.json` (use `pi list`).
3. The fix is restarting pi / starting a new session — do not "repair" package files or add fallbacks; the on-disk config is the source of truth.
4. Quick proof a fresh session is fine: the session's own `<available_skills>` block lists `<location>` paths — if they show the new layout, resolution is correct.

**Related:** [[pi-package-conventions]]
