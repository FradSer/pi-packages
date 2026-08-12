# Lark Pi Package

Feishu/Lark CLI skills, mirrored from [larksuite/cli](https://github.com/larksuite/cli) with local customizations and self-contained sync tools.

**Version**: 0.1.0  
**Display Name**: Lark

## What This Package Does

Lark/Feishu CLI operations — docs, sheets, IM, calendar, approval, attendance, drive, wiki, contacts, minutes, mail, tasks, events, video conferences, whiteboards, and more.

## Structure

- **`package.json`** — Pi package manifest declaring `./skills`.
- **`skills/SKILL.md` (lark router)** — local router that indexes all sub-skills; the index table is automatically regenerated from sub-skill frontmatter by `tools/skill-sync/gen-index.py`.
- **`skills/`** — mirrored sub-skills, stored as `<name>/<name>.md` (denested after sync so only the router is auto-discovered).
- **`scripts/sync-lark.sh`** — syncs from upstream `larksuite/cli`, then denests sub-skills and refreshes the router index.
- **`tools/skill-sync/`** — bundled Python tools (`denest.py`, `gen-index.py`) for denesting and index generation.
- **`SYNC.md`** — sync metadata and strategy.

## Installation

```bash
# published
pi install npm:@fradser/lark
# or from this repo: pi install /path/to/pi-packages/packages/lark
```

## Syncing from Upstream & Local Modifications

You can sync the latest skills from upstream `larksuite/cli` while keeping local additions:

```bash
# Dry-run: check for upstream updates
bash scripts/sync-lark.sh --check

# Sync with backup and refresh index table
bash scripts/sync-lark.sh

# Re-run denest or index generator manually if needed
python3 tools/skill-sync/denest.py --tree skills
python3 tools/skill-sync/gen-index.py --skills skills --router skills/SKILL.md
```

## License

MIT. Mirrored content sourced from `larksuite/cli`.
