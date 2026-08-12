# Memory Plugin

Active memory writing during conversation, plus manual `/skill:consolidate` for real consolidation (not cosmetic tidy). No auto-consolidation.

Two locations must stay **identical** (idempotent):

1. **`~/.claude/projects/<escaped-cwd>/memory/`** — harness, loaded by Claude Code, written first
2. **`.memory/`** — canonical, git-tracked, written second

**Privacy:** `.memory/` is part of a public GitHub repo. Technical content only; user preferences, credentials, and personal information stay in harness memory only.

**Version**: 0.1.5

## Installation

```bash
# published
pi install npm:@fradser/memory
# or from this repo: pi install /path/to/pi-packages/packages/memory
```

Invoke consolidate with `/skill:consolidate`.


## How it works

- **Active writing**: search existing theme files first; write harness, then mirror **safe** files to `.memory/`. Private content (preferences, credentials) is harness-only — never body or index line in `.memory/`.
- **Slash command** `/skill:consolidate` — user-invoked only. Fail-closed pipeline:
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
├── .claude-plugin/plugin.json
├── skills/consolidate/
│   ├── SKILL.md
│   └── references/staleness-examples.md
├── scripts/validate-consolidate.py
├── features/validate-consolidate.feature
├── tests/test_validate_consolidate.py
└── README.md
.memory/                         # per-project canonical git-tracked memory data
```
