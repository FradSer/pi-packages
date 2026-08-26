---
"@fradser/pi-utils": minor
---

Add Claude Code-style EnterWorktree and ExitWorktree session switching. Pi can
create or enter a git worktree through a replacement session, rebind built-in
tools and @ completions to that worktree cwd, return to the parent session, and
optionally clean up worktrees created by Pi.
