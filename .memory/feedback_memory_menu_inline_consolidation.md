---
name: memory-menu-inline-consolidation
description: /memory menu design — consolidate first, single project-instructions entry (AGENTS.md/CLAUDE.md), consolidation runs in a background child worker process, auto-triggered at 40% context fill when auto-memory is on
type: feedback
---

The @fradser/pi-memory /memory menu follows three rules: "Consolidate memory now" is the first option; the project-instructions entry resolves from cwd (`AGENTS.md` preferred, `CLAUDE.md` fallback — pi treats them as equivalent); consolidation runs through pi's native mechanism.

**Why:**
User feedback during a menu review: the hardcoded `~/Developer/FradSer/CLAUDE.md` was wrong for subprojects (each project has its own workspace CLAUDE.md), consolidate deserved top billing, and pointing the agent at a skill-style doc file (`skills/consolidate/SKILL.md`) added a dynamic path dependency that could break depending on install layout.

**How to apply:**
1. Menu order: Consolidate first, then user instructions, then project instructions (single entry — `AGENTS.md` and `CLAUDE.md` are the same concept under two ecosystem names; pi loads either from cwd), then auto-memory folder, toggle.
2. Project instructions entry: `resolveProjectInstructionsFile(cwd)` prefers `./AGENTS.md` (pi-native), falls back to `./CLAUDE.md` (Claude Code convention), defaults to creating `./AGENTS.md`; the menu label shows the resolved `./` path dynamically.
3. Consolidation runs as a background child worker process: whether triggered manually via the /memory menu ("Consolidate memory now") or auto-triggered at context fill, the extension calls `spawnAsyncConsolidation` to spawn an independent non-interactive child Pi process (`--print --mode json --no-session`) with a "Memory: dreaming" widget, keeping the main session context unblocked and clean.
4. `resolvePackageDir()` probes `~/.pi/agent/settings.json` packages (relative dev checkouts included) for `procedures/consolidate.md`, then `<cwd>/packages/memory`.
5. **Auto-consolidation** (added later): while auto-memory is on, the extension reads `ctx.getContextUsage()` at `agent_settled` and, once the session context fill reaches `consolidateAtContextFraction` of the active model's context window (default 0.4 = 40%, from research that long-context quality degrades from ~40-50% fill; persisted in `~/.pi/agent/memory/settings.json`, 0 disables), spawns a **background child Pi process** (`--print --mode json --no-session`, task via a temp `@file`, cwd = project) to run the inline consolidate procedure — async, never blocks the session, single-flight, with a `setWidget` "Memory: dreaming" indicator above the input box until the child exits. The child gets the session file path (`ctx.sessionManager.getSessionFile()`) for Step 0 capture. Tier-based firing (one trigger per fraction boundary: 40%, 80%, …) plus the `input`-source-`interactive` + `ctx.mode === "tui"` gates mean the consolidation run itself never re-triggers and one-shot `--print` child sessions never consolidate. Concurrency caveat: content written while a dreaming run holds its file snapshot is folded in by the next consolidation.
6. **Exit 0 is not proof of work** (failure mode): the consolidation child runs on the same default provider as the main session; when that provider is unstable (opencode HTTP 500) the child's model calls exhaust auto-retries and produce **empty output and zero tool calls**, yet the process still exits 0 — so the parent's unconditional "memory consolidated" notification was false. Gate the completion message on evidence of real work (a tool call executed, the validator run, or a G1–G8 report produced); otherwise report "consolidation finished but may not have completed" with the empty-output/stderr reason.

**Related:** [[pi-package-conventions]]
