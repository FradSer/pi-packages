---
name: agents-skills-symlinks
description: ~/.agents/skills/ user skills are symlinks to local dev repos (e.g. using-git-agent → git-agent/git-agent-cli) — never delete them when cleaning "skill installations"
type: feedback
---

`~/.agents/skills/` is the user's hand-managed skill dir: entries are **symlinks to local development repos**, not installs to clean. Examples: `using-git-agent -> ~/Developer/FradSer/git-agent/git-agent-cli/skills/using-git-agent`, `apple-events -> ~/Developer/FradSer/event/skills/apple-events`, `apple-notes -> ~/Developer/FradSer/note/skills/apple-notes`. The git-agent CLI repo ships its own `using-git-agent` skill (discovery stub that loads `git-agent skills get core`).

**Why:**
During the git/git-agent/github skills→menu conversion cleanup, `~/.agents/skills/using-git-agent/` was mistaken for a stale skill install and deleted with `rm -rf`. The user corrected: it is a symlink target that should stay (the CLI's own skill, kept in sync with the CLI version). Only package-owned skills under the pi packages (or lock-managed github installs in `.skill-lock.json`) are fair game; anything the user symlinked from a local repo is intentional.

**How to apply:**
1. Before deleting anything under `~/.agents/skills/` (or `~/.pi/agent/skills/`), check `ls -la`: symlink entries pointing at `~/Developer/FradSer/...` repos are user-managed — keep them.
2. `~/.agents/.skill-lock.json` only tracks github-source installs (impeccable, shadcn, cloudflare, etc.) — absence from the lock does NOT mean the skill is stale.
3. To restore a deleted symlink: `ln -s <repo>/skills/<name> ~/.agents/skills/<name>`.
4. The `pi-git-agent` package (`~/Developer/FradSer/git-agent/pi-git-agent`) is extension-only (no skills) — its menu guidance coexists with the CLI's own `using-git-agent` skill, which covers the raw CLI.

**Related:** [[pi-package-conventions]] [[stale-session-skill-paths]]
