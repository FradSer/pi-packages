---
"@fradser/pi-utils": minor
---

A redirected `git worktree add` moves the Pi session into the worktree it
created.

The redirect already kept linked worktrees inside `.pi/worktrees/<name>`. It now
also switches the session there, so the next relative path, edit, or shell
command belongs to the new checkout instead of the parent.

- The move is reserved before the command runs, so the rest of that tool batch
  is blocked rather than editing the checkout the session is leaving.
- The replacement session is forked from the current one and records the parent,
  exactly like `/enter-worktree`, so `/exit-worktree` keeps its behavior. The
  worktree is entered as an existing one: no second worktree or branch appears.
- The replacement session records one `[worktree] entered` row with the managed path,
  so the move is confirmed in the session it happened in. An extension notice sent
  during the switch does not reliably paint; the row does, and Ctrl+O expands it to
  `Path: <absolute directory>`. This replaces the transient
  `Entered worktree:` notice of the explicit command path too.
- A failed creation releases the batch and tells the user the session stays in
  its current directory. A reserved command that produces no result at all — a
  truncated message, or a blocker that stops it before execution — never moves
  the session, because only a successful result confirms the directory exists.
- A creation cannot start while another switch is already in flight, and a
  worktree command invoked after a reservation is refused by name until the turn
  settles. Neither case leaves a stray worktree or a silent session move.
- A session without a session file cannot be replaced: the worktree stays on
  disk and the user is told that Pi cannot switch to it.
- An explicit `/enter-worktree` or `enter_worktree` in the same message wins
  over the automatic move.
- An aborted run drops the queued move and says so; the created worktree is
  kept. Pi 1.2.0 reports the abort on `agent_settled`; an older host that does
  not report it still applies the move.

Commands that are not rewritten, such as a chained shell form or an
already-managed path, never move the session.
