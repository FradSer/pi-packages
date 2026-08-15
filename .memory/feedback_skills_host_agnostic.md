---
name: skills-host-agnostic
description: ~/Developer/FradSer/skills serves multiple agent hosts — skill files must stay host-agnostic; no pi/Claude-specific tool names, diagnostics, or package concepts
type: feedback
---

The skills repo (`~/Developer/FradSer/skills`) is consumed by multiple agent hosts (Claude Code, pi, others). Skill content — SKILL.md, references, scripts — must stay host-agnostic ("更通用"). Host-specific integration details belong in the host's own packages/docs, never in skill files.

**Why:**
User reminder ("记得 skills 需要更通用") after the review-pr watch-buffering fix: the first draft leaked host-specific framing into the skill ("the monitor sees nothing", an anecdote phrased around one host's monitor UI), and the warning was inaccurate outside streaming consumers — under the re-entrant `--once` mode the grep buffer flushes at exit and nothing stalls. The review-pr skill is explicitly designed tool-agnostic ("The workflow is tool-agnostic"; "Run it under the host's generic background monitor when available... otherwise --once once per turn").

**How to apply:**
1. Never write host-specific tool names (`monitor_start`, `ctx.ui.*`), package names (`@fradser/pi-monitor`), or host UI diagnostics (`0 retained, 0 dropped`) into skill files.
2. Use the skill's established generic vocabulary: "the host's generic background monitor", "a streaming background watch", "the re-entrant `--once` mode", "background task".
3. Scope behavioral claims to the consumers they actually apply to (e.g. pipe buffering affects streaming consumers only; `--once` readers are unaffected).
4. Host-side guidance for the same lesson lives in the host's own docs (e.g. `pi-packages/packages/monitor` using-monitor skill + README gotcha section).
5. Incident anecdotes are fine in skill references when phrased host-neutrally ("a watch piped through `grep -v node=...` delivered no events for 20+ minutes").

**Related:** [[pi-package-conventions]] [[git-github-menu-conversion]] [[agents-skills-symlinks]]
