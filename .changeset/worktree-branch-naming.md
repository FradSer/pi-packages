---
"@fradser/pi-utils": minor
---

A managed worktree is created on the name itself, with no tool namespace.

`/enter-worktree feature-auth` created `.pi/worktrees/feature-auth` on branch
`pi/worktree/feature-auth`: a namespace plus a `worktree` segment that repeated
what the managed path already says.

- The branch is now the name: `.pi/worktrees/feature-auth` on branch
  `feature-auth`, the spelling a plain
  `git worktree add .pi/worktrees/<name> <branch>` reads. The location stays
  `.pi/worktrees/<name>`; only the branch lost the prefix.
- Two names are refused before anything is created, so the user reads one reason
  instead of git's fatal and no empty `.pi/worktrees` directory is left behind:
  a name git rejects as a ref (a leading dot, a trailing `.lock`), and a name
  whose branch already exists — the common collision of a bare name, which
  `git worktree add -b` would refuse. That message names the way out: another
  name, or `path` for an existing worktree.
- `/exit-worktree` is unaffected: it removes the branch recorded in the session
  state, so a worktree created under the old name still cleans up.

A worktree created by a redirected `git worktree add` keeps the branch named in
that command; this changes only the branch this package creates.