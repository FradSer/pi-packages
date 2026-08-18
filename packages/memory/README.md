# Memory Plugin

Native pi `/memory` command — no skill surface. Provides an instructions editor
menu, memory folder access, auto-memory guidance toggle, manual consolidation,
and a dedicated `/consolidate` command.

Two locations must stay **identical** (idempotent):

1. **`~/.pi/agent/memory/<escaped-cwd>/`** — harness, loaded by pi, written first
2. **`.memory/`** — canonical, git-tracked, written second

**Privacy:** `.memory/` is part of a public GitHub repo. Technical content only; user preferences, credentials, and personal information stay in harness memory only.

**Version**: 0.2.1

## Installation

```bash
# published
pi install npm:pi-memory-fradser
# or from this repo: pi install /path/to/pi-packages/packages/memory
```

## Usage

Type `/memory` to open the management menu (native pi select dialog). Type
`/consolidate` to skip the menu and start consolidation immediately.

```
Auto-memory: on

❯ 1. Consolidate memory now
  2. Edit user instructions        (~/.pi/agent/AGENTS.md)
  3. Edit project instructions     (./AGENTS.md — or ./CLAUDE.md if that exists)
  4. Open memory folder
  5. Toggle auto-memory (currently on)
```

- **Auto-memory on** (default): `before_agent_start` injects prompt guidance that
  instructs the LLM to actively capture durable decisions, preferences, and lessons
  into memory during the session as needed. Off = no prompt guidance; existing
  memories are still injected into the system prompt.
- **Consolidate memory now**: runs the full fail-closed consolidation procedure
  (`procedures/consolidate.md`) in the background without blocking the active
  session. A "Memory: dreaming" widget shows progress above the input editor.
  The completion notice says memory was consolidated only after the required
  tool work, validator, and `G1 passed` through `G8 passed` evidence is present;
  an unverified run gets a diagnostic warning instead.
- **Memory model**: choose an available Pi model from the `/memory` menu, or
  enter `provider/model` manually. The selection is persisted in
  `~/.pi/agent/memory.json` and used for future consolidation runs. Environment
  variables `PI_MEMORY_PROVIDER` and `PI_MEMORY_MODEL` provide initial fallback
  configuration.
- **`/consolidate`**: a dedicated one-shot trigger for the same consolidation,
  sitting as a sibling of `/memory` — no menu, starts it immediately
  (single-flight: a running consolidation blocks a second one). It runs in the
  background, so the active session stays responsive while the "Memory:
  dreaming" widget shows progress.

## How it works

- **System prompt injection**: active project memories in `.memory/` and the
  harness directory are loaded and formatted into the system prompt before each turn.
  When auto-memory is enabled, guidance for active memory capture is also appended.
- **Consolidation** — menu item 3 or `/consolidate`. Fail-closed pipeline:
  1. Capture durable content from the current session, then select related memories
  2. Read the selected related files + inventory (mutation freeze until planning artifacts exist)
  3. Theme-cluster covering the selected non-index files (merge bias default)
  4. Staleness rubric (practical expiry, not calendar age alone)
  5. **Machine check** `scripts/validate-consolidate.py --check=cluster,staleness` (exit 0 lifts freeze)
  6. Ground-truth verify against the current tree with cited paths
  7. Merge / prune / rewrite
  8. Independent adversarial pass when any multi-file cluster, count ≥ 8, or uncertainty
  9. Rebuild **split** indexes (harness full; `.memory/` safe-only) + scrub stale private copies from `.memory/`
  10. Full `validate-consolidate.py` (cluster+staleness+report+privacy) exit 0 + G1–G8 report

Cosmetic-only runs (frontmatter + index rewrite while thematic duplicates remain) are invalid.

## Files

```
memory/
├── extensions/inject-memory.ts   # /memory + /consolidate commands, memory injection, auto-memory guidance
├── procedures/
│   └── consolidate.md            # inline background consolidation procedure, not a skill
├── scripts/validate-consolidate.py
├── features/validate-consolidate.feature
├── features/consolidate.feature
├── tests/test_validate_consolidate.py
├── tests/test_inject_memory_extension.py
├── tests/consolidation_evidence_harness.ts
└── README.md
.memory/                         # per-project canonical git-tracked memory data
```
