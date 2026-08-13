---
name: git-github-menu-conversion
description: git/git-agent/github expose workflows as pi menu commands (/git, /git-agent, /github) with inline procedures — no skill surface; manual selection is settled, no independent commands or autocomplete
type: project
---

The git, git-agent, and github packages expose their workflows as native pi menu commands (`/git`, `/git-agent`, `/github`) with **no skill surface** (pattern: `@fradser/memory`'s `/memory`). Each package: `extensions/menu.ts` registers one command; `ctx.ui.select` shows the menu; the chosen item's full procedure (`procedures/<name>.md`) is embedded via `pi.sendUserMessage(..., { deliverAs: "followUp" })` with `{{PKG_DIR}}` substituted at send time. Keyword shorthand (`/github review-pr 123`) runs the workflow directly, skipping the menu. This single-menu-command-per-package shape is settled: do not split into per-workflow commands, package-prefixed names (`/git-commit`, `/git-agent-commit`), or `getArgumentCompletions` keyword autocomplete.

**Why:**
The user directed that the packages' commands should be pi menus, not skills ("命令应该不是 skill 而是 pi 的菜单"), referencing the `/memory` package as the pattern. Skills also collided in pi's global skill namespace (`commit` / `commit-and-push`) and broke after the repo restructure into `packages/`. When the naming/UX question resurfaced (why no `/create-pr`, whether "multiple independent commands" were possible), package-prefixed naming and a uniform-prefix scheme were all declined — final call: "不走这个方向吧，就让用户手动去选择" (keep manual menu selection, no independent commands, no autocomplete).

**How to apply:**
1. `/git` — GitFlow start/finish for feature/hotfix/release + commit/commit-and-push (standard git); `procedures/start.md` & `finish.md` substitute `{{WORKFLOW_TYPE}}`; the package must never contain the literal `git-agent` (test-enforced decoupling).
2. `/git-agent` — commit, commit-and-push, init, related; procedures point at `{{PKG_DIR}}/references/cli.md`; a small `before_agent_start` guidance block keeps "commit this" routing without a skill.
3. `git`/`github` moved to pure skills in ~/Developer/FradSer/skills (see the skills repo) — their pi menu packages were removed from this monorepo.
4. package.json: `pi` = `{ "extensions": [...] }` only; `files` includes `procedures` (+ `references`, `scripts` for github). Delete `skills/` entirely.
5. Procedures must not reference `/skill:`; reference paths resolve through the `{{PKG_DIR}}` placeholder at send time.
6. Natural-language routing still exists via `before_agent_start` GUIDANCE injection ("create a PR", "commit this") — the shortcut for users who skip both the menu and slash-command knowledge.
7. If a naming/UX question around these commands comes up again, default to "user manually selects from the menu" and only revisit with explicit user consent.

**Related:** [[pi-package-conventions]] [[no-custom-interaction-tools]] [[stale-session-skill-paths]]
