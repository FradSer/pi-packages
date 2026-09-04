---
name: pi-package-conventions
description: Native Pi package standards for package.json, skills, extensions, worktrees, and runtime deps — no Claude plugin artifacts
type: project
---

Pi packages under `pi-packages/` follow native Pi Agent Harness conventions for manifests, skills, extensions, and package management — not Claude Code plugin layout.

**Why:**
Mixing legacy Claude Code plugin artifacts (`.claude-plugin`, `${CLAUDE_PLUGIN_ROOT}`, Claude-only skill frontmatter/tools) with Pi package architecture causes resolution failures, dirty environment assumptions, and skills that do not run under Pi.

**How to apply:**
1. **Manifests:** Use `package.json` with `"keywords": ["pi-package"]` and `"pi": { "skills": [...], "extensions": [...] }`. Never place `.claude-plugin` directories inside `pi-packages`.
2. **Paths:** Use standard relative Markdown paths (`../../references/...`, `scripts/...`) — never `${CLAUDE_PLUGIN_ROOT}`.
3. **Worktrees:** Create Git worktrees under `.pi/worktrees/<name>` (the agent-teams package uses `.pi/worktrees/teammate-<taskId>/`; a former `git` package extension also rewrote bare `git worktree add` targets there).
4. **Decoupling:** Keep GitFlow tooling (now pure skills in `~/Developer/FradSer/skills`) strictly decoupled from `git-agent` (AI commit + co-change, `~/Developer/FradSer/git-agent/pi-git-agent`). Do not reintroduce cross-references outside tests.
5. **Skill invocation:** Load skills with `/skill:<name>`. Arguments are appended after the skill body. Do not rely on `$ARGUMENTS` expansion or `` !`cmd` `` shell injections inside skill Markdown (Pi does not process them).
6. **Skill frontmatter:** Only Pi fields — `name`, `description`, optional `disable-model-invocation`. Strip Claude-only keys (`allowed-tools`, `user-invocable`, `argument-hint`, `model`).
7. **Tools in skills:** Prefer Pi built-ins (`bash`, `read`, `edit`, `write`). Do not assume Claude-only tools (`Task`, `Skill()`, `Monitor`, `AskUserQuestion`, `EnterWorktree`, `WebSearch`, `WebFetch`).
8. **Extensions:** Packages that ship extensions declare `peerDependencies: { "@earendil-works/pi-coding-agent": "*" }`.
9. **Runtime deps:** Document required CLIs (e.g. `gh`) and optional MCP servers (e.g. code-context DeepWiki/Context7/Exa) in package description and README; provide fallbacks when optional runtimes are missing.
10. **Skill name collisions:** Skill names are global in the agent; first installed package wins. Avoid duplicate skill names across packages — the historical `commit` / `commit-and-push` clash between the `git` and `git-agent` packages was resolved by moving to menu commands and the external skills repo.

**Related:** [[git-github-menu-conversion]] [[stale-session-skill-paths]] [[agents-skills-symlinks]]
