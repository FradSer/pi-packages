---
"@fradser/pi-utils": minor
---

Worktree paths now anchor to the repository root, the /effort menu mirrors pi's supported-level rule, and live-session control has a command to reach it.

**@fradser/pi-utils**

- **One worktree location.** `git worktree add` issued from a repository subdirectory was rewritten to a cwd-relative `.pi/worktrees/<name>`, so the worktree landed somewhere `/enter-worktree` and the isolation filters never looked. The redirect now resolves the repository root and emits the absolute managed path, and all three worktree layers share one porcelain parser, canonicalizer, and `.pi/worktrees` definition (`extensions/git/worktrees.ts`). A repository that does not git-ignore `.pi/` is told so; the extension never edits a `.gitignore`.
- **`/effort` matches pi.** The menu hid `xhigh`/`max` only when a `thinkingLevelMap` was present and treated an absent `reasoning` flag as full support, diverging from pi's own rule. It now applies the same predicate, pinned by a parity test against `getSupportedThinkingLevels` from `@earendil-works/pi-ai`.
- **`/live-sessions`.** Live-session discovery and delivery had no entry point in the shipped package. The new command lists instances (with id completions) and sends text, reporting `accepted` or `queued` without ever claiming completion, and bounds its arguments before touching a socket.
- **Transition honesty.** An aborted run drops the queued worktree transition and now says so instead of leaving the model believing one was coming; a worktree command invoked while a transition is queued is refused rather than racing the session switch; the batch barrier names the pending transition.
- **Registry and guard cleanups.** A session removes its record from every directory it registered under (session replacement changes cwd without reloading extensions), registry temp names no longer depend on a per-millisecond clock, and the publish guard's advice follows the repository's lockfile instead of asserting "this pnpm workspace" to every user.
- **Cross-package tool inputs.** The worktree isolation filters write `exclude` only into search tools whose declared schema has that parameter; undeclared tools keep their input untouched and are still filtered on the way back.
- **Verification.** Extension tests that asserted on source text are replaced by tests that drive registered command handlers, tool `execute`, and event handlers against a fake host: the same mutation that used to pass `/effort` tests silently now fails seven.