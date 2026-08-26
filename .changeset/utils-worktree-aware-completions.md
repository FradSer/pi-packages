---
"@fradser/pi-utils": minor
---

Add git worktree-aware @ completions: editor file suggestions now hide paths
that resolve inside another git worktree. A session in main never sees linked
worktree contents, and a session inside a linked worktree never sees sibling
worktrees or the main checkout.
