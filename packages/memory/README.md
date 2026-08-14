# Memory Plugin

Native pi `/memory` command — no skill surface. Provides auto-memory guidance
(injected like @fradser/pi-agent-teams injects its guidance), an instructions editor
menu, manual consolidation, and a dedicated `/consolidate` command.

Two locations must stay **identical** (idempotent):

1. **`~/.pi/agent/memory/<escaped-cwd>/`** — harness, loaded by pi, written first
2. **`.memory/`** — canonical, git-tracked, written second

**Privacy:** `.memory/` is part of a public GitHub repo. Technical content only; user preferences, credentials, and personal information stay in harness memory only.

**Version**: 0.2.1

## Installation

```bash
# published
pi install npm:@fradser/pi-memory
# or from this repo: pi install /path/to/pi-packages/packages/memory
```

## Usage

Type `/memory` to open the management menu (native pi select dialog). Type
`/consolidate` to skip the menu and start the same consolidation immediately.

```
Auto-memory: on

❯ 1. Consolidate memory now
  2. Edit user instructions        (~/.pi/agent/AGENTS.md)
  3. Edit project instructions     (./AGENTS.md — or ./CLAUDE.md if that exists)
  4. Open auto-memory folder
  5. Toggle auto-memory (currently on)
```

- **Auto-memory on** (default): `before_agent_start` injects a guidance block that
  tells the agent to actively capture durable decisions/preferences/lessons into
  memory as they occur. Off = no auto-write guidance; existing memories are still
  injected into the system prompt.
- **Consolidate memory now**: spawns an **independent background child Pi
  process** (`spawnAsyncConsolidation`, `--print --mode json --no-session`) to
  run the full fail-closed consolidation procedure (`procedures/consolidate.md`)
  without blocking or cluttering the active session context. The extension writes
  the procedure to a temporary task file and launches the child with
  `--print --mode json --no-session @<task-file>`. A "Memory: dreaming" widget
  shows above the input editor until the worker exits. The completion notice says
  memory was consolidated only after JSONL shows completed tool work, a passing
  full validator, and an individually marked `G1 passed` through `G8 passed`
  gate report; a zero-exit worker without that evidence gets a diagnostic
  warning instead.
- **`/consolidate`**: a dedicated one-shot trigger for the same consolidation,
  sitting as a sibling of `/memory` — no menu, starts it immediately
  (single-flight: a running consolidation blocks a second one). It already runs
  entirely in the background, so the foreground user just sees the "Memory:
  dreaming" widget.
- **Auto-consolidate**: while auto-memory is on, the extension watches
  `ctx.getContextUsage()` and, once the session context fill reaches
  `consolidateAtContextFraction` of the active model's context window (default
  0.4 = 40% — research shows long-context quality degrades from ~40-50% fill),
  spawns a **background child Pi process** (`--print --mode json --no-session`)
  to run the same fail-closed consolidation — the session is never blocked, and
  a "Memory: dreaming" widget shows above the input editor until the child
  exits. Fires once per fraction boundary (40%, 80%, …) after a real user turn
  (`input` source `interactive`) in TUI mode, so the consolidation run itself
  never re-triggers; only one dreaming run at a time.
- Settings are persisted per-user at
  `~/.pi/agent/memory/settings.json` — `{ "autoMemory": bool,
  "consolidateAtContextFraction": 0.4 }` (set the fraction to 0 to disable).

## How it works

- **Auto-write**: the injected guidance tells the agent to search existing theme
  files first, write harness, then mirror **safe** files to `.memory/`. Private
  content (preferences, credentials) is harness-only — never body or index line in `.memory/`.
- **Consolidation** — menu item 1, `/consolidate`, or auto-trigger. Fail-closed pipeline:
  1. Read all files + inventory (mutation freeze until planning artifacts exist)
  2. Theme-cluster covering every non-index file (merge bias default)
  3. Staleness rubric (practical expiry, not calendar age alone)
  4. **Machine check** `scripts/validate-consolidate.py --check=cluster,staleness` (exit 0 lifts freeze)
  5. Ground-truth verify against the current tree with cited paths
  6. Merge / prune / rewrite
  7. Independent adversarial pass when any multi-file cluster, count ≥ 8, or uncertainty
  8. Rebuild **split** indexes (harness full; `.memory/` safe-only) + scrub stale private copies from `.memory/`
  9. Full `validate-consolidate.py` (cluster+staleness+report+privacy) exit 0 + G1–G8 report

Cosmetic-only runs (frontmatter + index rewrite while thematic duplicates remain) are invalid.

## Files

```
memory/
├── extensions/inject-memory.ts   # /memory + /consolidate commands, auto-memory injection, auto-consolidation
├── procedures/
│   └── consolidate.md            # inline procedure written to a child Pi task file, not a skill
├── scripts/validate-consolidate.py
├── features/validate-consolidate.feature
├── features/auto-consolidate.feature
├── tests/test_validate_consolidate.py
├── tests/test_inject_memory_extension.py
├── tests/consolidation_evidence_harness.ts
└── README.md
.memory/                         # per-project canonical git-tracked memory data
```
