---
name: agents-skills-pool-hygiene
description: ~/.agents/skills shared pool hosts only cross-host skills — Codex/Claude-Code-exclusive ones get deleted, and ceremony workflows in FradSer/skills use disable-model-invocation
type: feedback
---

The `~/.agents/skills/` directory is a cross-host skill pool that pi reads natively (alongside the curated symlinks in `~/.pi/agent/skills/`). Host-exclusive skills must not live there. On 2026-08-22 the pool was cleaned of host-exclusive skills: 20 Codex/Cursor-exclusive ones deleted (automate, canvas, create-hook, create-rule, create-skill, create-subagent, goal, migrate-to-skills, new-repo, onboard, origin, rename-chat, review, review-bugbot, review-security, sdk, share, statusline, update-cli-config, update-cursor-settings) plus 2 Claude-Code-exclusive ones (`claude-handoff` -> `claude --bg`, `git-guardrails-claude-code` -> CC hooks), removing their `.skill-lock.json` entries together with the directories (pool went 98 -> 76 entries; lock 51 -> 49 keys).

**Why:**
pi loads `~/.agents/skills/` as a default global location, so every entry taxes every session's system prompt (~75 discovered skills was ~5K tokens of name+description) and risks mis-triggering on machinery that does not exist in pi (Codex Automations, Canvas, hooks.json, `.cursor/rules`, Bugbot subagents). The Agent Skills frontmatter has no host-scoping field, so the only filter is pool composition itself.

**How to apply:**
1. When a host-exclusive skill appears in the pool, delete it from `~/.agents/skills/` rather than filtering downstream; check `.agents/.skill-lock.json` first — lock-managed entries (github installs) need dir + lock entry removed together or they return on next sync.
2. Mere mentions of other hosts inside a skill body (e.g. agent-browser listing `~/.claude/skills` as one install target) do NOT make it host-exclusive — exclusivity means the skill drives machinery only that host has (`claude --bg`, Codex Automations, Canvas, Bugbot subagents, `.cursor/cli-config.json`).
3. In `~/Developer/FradSer/skills`, git-flow ceremony skills (start-feature/hotfix/release, finish-feature/hotfix/release) carry `disable-model-invocation: true`: branch/merge/tag ceremonies are explicit-only via `/skill:name`; natural-language-routed skills (commit, commit-and-push, create-pr, resolve-issues, review-pr, create-issues) stay model-invocable because NL routing is their design.
4. Changes take effect in new pi sessions only; running sessions hold skill paths from startup.

**Related:** [[skills-host-agnostic]] [[pi-package-conventions]] [[git-github-menu-conversion]]
