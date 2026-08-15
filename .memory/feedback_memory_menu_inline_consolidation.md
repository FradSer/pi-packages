---
name: memory-menu-inline-consolidation
description: /memory menu design — consolidate first, instructions entry (AGENTS.md/CLAUDE.md), memory folder access, auto-memory guidance toggle; consolidation runs in a background child worker process on manual trigger (via /memory menu or /consolidate), no automatic consolidation triggers
type: feedback
---

The @fradser/pi-memory /memory menu follows clean principles: "Consolidate memory now" is the first option; the project-instructions entry resolves from cwd (`AGENTS.md` preferred, `CLAUDE.md` fallback — pi treats them as equivalent); memory folder is accessible; auto-memory toggle controls prompt guidance; consolidation runs through pi's native mechanism on demand.

**Why:**
Auto-memory guidance helps the LLM actively capture durable decisions, preferences, and lessons directly during conversation without needing a command. However, automatic background consolidation triggered by context thresholds (e.g. at 40% fill) is unnecessary and intrusive — consolidation should only run when manually requested via `/memory` or `/consolidate`.

**How to apply:**
1. Menu order: Consolidate first, then user instructions, then project instructions (single entry — `AGENTS.md` and `CLAUDE.md` are the same concept under two ecosystem names; pi loads either from cwd), then open memory folder, then toggle auto-memory.
2. Auto-memory guidance: When `autoMemory` is on (default true, persisted in `~/.pi/agent/memory/settings.json`), `before_agent_start` injects prompt guidance (`AUTO_MEMORY_GUIDANCE`) telling the LLM to actively record durable facts directly into memory files. When off, only existing project memories are injected.
3. Project instructions entry: `resolveProjectInstructionsFile(cwd)` prefers `./AGENTS.md` (pi-native), falls back to `./CLAUDE.md` (Claude Code convention), defaults to creating `./AGENTS.md`; the menu label shows the resolved `./` path dynamically.
4. Consolidation runs as a background child worker process on manual trigger only: triggered manually via the /memory menu ("Consolidate memory now") or the `/consolidate` command, the extension calls `spawnAsyncConsolidation` to spawn an independent non-interactive child Pi process (`--print --mode json --no-session`) with a "Memory: dreaming" widget, keeping the main session context unblocked and clean.
5. **No auto-consolidation**: No context-threshold watchers, no `agent_settled` triggers, and no automatic spawning of consolidation background runs.
6. **Exit 0 is not proof of work** (failure mode): the consolidation child runs on the same default provider as the main session; when that provider is unstable (opencode HTTP 500) the child's model calls exhaust auto-retries and produce **empty output and zero tool calls**, yet the process still exits 0 — so the parent's unconditional "memory consolidated" notification was false. Gate the completion message on evidence of real work (a tool call executed, the validator run, or a G1–G8 report produced); otherwise report "consolidation finished but may not have completed" with the empty-output/stderr reason.

**Related:** [[pi-package-conventions]]
