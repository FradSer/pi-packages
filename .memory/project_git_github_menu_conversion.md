---
name: git-github-menu-conversion
description: Settled workflow-UX decision — pi menu commands with inline procedures, not skills; manual selection, no per-workflow commands or autocomplete; git/github menus later removed, git-agent menu lives in git-agent/pi-git-agent
type: project
---

Settled UX decision for FradSer workflow packages: expose workflows as native pi **menu commands** (one `registerCommand` per package, `ctx.ui.select` menu, full procedure embedded via `pi.sendUserMessage(..., { deliverAs: "followUp" })` with `{{PKG_DIR}}` substituted at send time), **not skills**. Do not split into per-workflow commands, package-prefixed names (`/git-commit`), or `getArgumentCompletions` keyword autocomplete — "不走这个方向吧，就让用户手动去选择" (user manually selects from the menu; revisit only with explicit user consent).

**Why:**
The user directed that package commands should be pi menus, not skills ("命令应该不是 skill 而是 pi 的菜单"), referencing `/memory` as the pattern. Skills collided in pi's global skill namespace (`commit` / `commit-and-push`) and broke after the repo restructure into `packages/`. When the naming/UX question resurfaced (why no `/create-pr`, whether "multiple independent commands" were possible), package-prefixed naming and a uniform-prefix scheme were all declined.

**Current state (verified 2026-08-14):**
1. `/git` and `/github` menu packages were **removed from this monorepo**; their workflows (GitFlow start/finish, commit, commit-and-push, create-issues, create-pr, resolve-issues, review-pr) became **pure skills in `~/Developer/FradSer/skills`** — verified present there. create-pr remains the only PR-creating path.
2. The `/git-agent` menu package moved to **`~/Developer/FradSer/git-agent/pi-git-agent`** (npm name `pi-git-agent`, extension-only): commit, commit-and-push, init, related; `extensions/menu.ts` + `procedures/*.md` + a `before_agent_start` guidance block for "commit this" routing.
3. `/memory` and `/btw` menus in this monorepo follow the same pattern (`packages/memory`, `packages/btw`).

**How to apply:**
1. New workflow surfaces default to a menu command with inline procedures; only revisit with explicit user consent.
2. package.json: `pi` = `{ "extensions": [...] }` only; `files` includes `procedures` (+ `references`, `scripts` where used). No `skills/` for workflow packages.
3. Procedures must not reference `/skill:`; reference paths resolve through the `{{PKG_DIR}}` placeholder at send time.
4. Natural-language routing ("commit this", "create a PR") is preserved with small `before_agent_start` GUIDANCE blocks, not skills.

**Related:** [[pi-package-conventions]] [[no-custom-interaction-tools]] [[stale-session-skill-paths]]
