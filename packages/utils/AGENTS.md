# Repository Guidelines

## Project Structure

`packages/utils/` publishes `@fradser/pi-utils`, a native Pi extension. `index.ts`
only wires the focused modules in `extensions/`: `/autoname`, `/continue`,
`/effort`, `/init`, `/sessions`, private live-session socket control and its
`/live-sessions` command, npm publish/credential guarding, git worktree path
redirect, worktree-aware `@` completions, and EnterWorktree/ExitWorktree
session switching. BDD contracts live in `features/`; executable Python tests
and runtime harnesses live in `tests/`. The published package is limited by
`package.json`'s `files` list (`index.ts`, `extensions/`, and `README.md`).

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/utils/tests/ -q
pnpm --dir packages/utils pack --dry-run
sh packages/utils/tests/utils_docker.sh
UTILS_DOCKER_BASE_IMAGE=node:24-trixie-slim sh packages/utils/tests/utils_docker.sh
```

`utils_docker.sh` packs `@fradser/pi-kit` and `@fradser/pi-utils`, installs
both in an isolated Pi 1.2.0 container, and runs two real layers. It prints the
receipt directory on success and keeps it on failure.

## Style and Architecture

Keep command behavior in its corresponding extension and `index.ts` as
composition-only wiring. Preserve explicit `.ts` relative imports in this
package; its entry point is exercised through native Node and tsx.

- **Shared git plumbing**: `extensions/git/worktrees.ts` owns the single
  `git worktree list --porcelain` parser, canonicalization helpers, and the
  `.pi/worktrees` definition. The redirect, the isolation filters, and the
  session switcher must import them instead of re-deriving roots; that
  duplication is what previously let a command run from a subdirectory create
  a worktree where no other layer looked for it.
- **Automatic entry after a redirected creation**: a rewritten `git worktree add`
  moves the session into the worktree it made. The redirect does not switch
  sessions itself: it reserves the transition in `message_end`, before any tool
  of that message runs, and settles it with the real bash result. Only a
  successful result confirms the move: a reserved call that produces no result
  never moves the session, because nothing proves the directory exists. The
  session switcher owns the barrier and the queued command, so an automatic
  entry cannot race an explicit transition, and the reserved call is the one
  call the barrier exempts. The barrier also covers a switch that is already in
  flight, and a worktree command invoked after a reservation is refused by name.
  A blocked call still produces tool execution events and an error tool result,
  so judge an outcome by the result, never by the presence of an execution
  event. `resetTransition()` is the only place that clears this state, and both
  `session_start` and `agent_settled` call it. Keep the registration order in
  `index.ts`: the switcher registers first, so its `message_end` handler sets the
  transition id before the redirect reserves. An unpersisted session cannot be
  replaced, so the redirect reports that instead of reserving. The move is confirmed by one
  displayed `pi-utils-worktree-applied` row of the replacement session, not by a
  notice: a notice sent while the switch rebinds the session does not reliably
  paint, while a transcript row is durable. Keep the row subject short (the
  repository-relative managed path) and the absolute directory in its expansion
  detail as `Path: <directory>`, or a narrow terminal truncates the path. Pi 1.2.0
  reports `agent_settled.aborted`, and the package's 1.0.x type dependency still
  omits that field: declare the event type with the optional field and treat an
  absent value as "not aborted".
- **Worktree Session Switching (`enter_worktree`, `exit_worktree`)**:
  - *Session Forking*: Uses `SessionManager.forkFrom` to replace the session with a worktree-rooted one instead of mutating `process.cwd`. Tools terminate their batch and dispatch `/enter-worktree` or `/exit-worktree` only at `agent_settled` (`expandPromptTemplates: true`, Pi ≥0.85.1). Block sibling tools and keep the barrier active until dispatch; resume work only through the replacement context.
  - *Foreign Worktree Protection*: Non-session worktrees are foreign checkouts; `read`, `edit`, and `write` block access until entered via `enter_worktree`.
  - *Progressive Tool Disclosure*: `exit_worktree` is activated via `pi.setActiveTools()` only when currently inside a worktree-created session.
  - *Abort and re-entry*: An aborted run drops the queued transition and notifies the user; a worktree command issued while a transition is queued is refused rather than racing the session switch. Both are deliberate: the model is told the transition is pending, so neither state may be left implied.
- **Directory Sessions (`list_directory_sessions`)**:
  - Reads `~/.pi/agent/directory-sessions/`, filters dead PIDs, and collapses multi-writer records by PID.
  - Dynamically exposed via `pi.setActiveTools()` only when active/recent peer sessions exist in cwd.
  - Sanitizes untrusted registry fields with `safeDisplayText` before prompt injection or transcript rendering.
- **Live Session Control**:
  - Uses private user-owned Unix sockets; never inject terminal input or edit session files.
  - Routes by opaque live-instance ID, preserves request-ID replay protection, and never treats accepted/queued as completion.
  - Keep this capability internal to `@fradser/pi-utils`; do not add a separate package or executable. The `/live-sessions` slash command is its only entry point, so the capability stays reachable without a CLI.
- **Foreign tool inputs**: `worktree-completion.ts` writes `exclude` into a search tool only when that tool's declared schema has the parameter (`pi.getAllTools()`), and always filters foreign paths out of returned text as the backstop. Never assume another package's input shape.
- **Managed worktree ignore state**: creating a worktree reports when `.pi/` is not git-ignored. Do not edit a repository's `.gitignore` to fix it; that is the user's file and the change needs their say-so.
- **Session Naming (`autoname`)**: `/name` is a built-in interactive command and
  an extension cannot replace it, so `/autoname` is the model-generated
  counterpart. Build the digest from user requests only, race the deadline
  against the request rather than only signalling it, forward the session id
  so routing gateways accept the nested call, and report each failure cause
  instead of one generic error. The request rules ask for the subject of the
  work as a noun phrase, forbid a leading verb, and show one good name against
  one bad name: without that pair the model restated the conversation as a
  command and named the directory. A provider rejection arrives as a message with
  `stopReason: "error"`, not as a thrown error. The name request must go through
  `streamSimple` with `reasoning: "off"`: the raw `complete` path cannot express
  a reasoning level, so a reasoning model runs at its default and shares one
  response budget with the answer, which leaves a thinking block and no name.
- **Publish Guard**: `extensions/npm-publish-guard.ts` checks command positions
  and exact dry-run flags. Preserve coverage for filtered/recursive publish
  forms; never route OTP codes through chat.

## Testing Guidelines

Match each extension with its contract under `features/` and tests under
`tests/`. Cover continuation recovery without breaking tool-call/result pairs,
known tree-leaf selection versus unseen disk appends, model-supported thinking
levels, safe worktree rewriting, queued versus applied session replacement,
registry deduplication, and npm guard parsing.

For real worktree creation, `tests/worktree_creation_cases.py` drives
`pi --print` so the real `bash` tool runs each rewritten command, then reads the
checkout, branch, lock state and worktree list back from disk.
`tests/worktree_notice_pty.py` drives the real interactive CLI through a PTY,
because print mode replaces `ui.notify` with a no-op. Run both only through
`tests/utils_docker.sh`, which isolates HOME, the agent directory and the
repository fixtures; `test_utils_docker_harness.py` guards the harness prologue,
which must start on a host that exports no TMPDIR. Read `creation/evidence.json`,
`notices/evidence.json` and
the per-case `pi.jsonl`, `pi.stderr`, `raw.bin` and `frames.txt` in the receipt.

- The harness pins the current Pi release (1.2.0). A native run keeps a
  persisted session, because a session move needs a session file; the ephemeral
  path is covered by the PTY cases, which pass `--no-session`.
- Never pass `-ne` to a native run that must load the installed package: it
  disables the `packages` entries in `settings.json`. Use `-ns -np -nc
  --no-themes` for isolation instead.
- Debian bookworm ships git 2.39, which has no `git worktree add --orphan`, so
  that case reports SKIP. The trixie image runs it on git 2.47.

Tests must exercise behavior, not source text. An assertion that a string or an
expression appears in an extension file passes while the behavior behind it is
broken; drive the registered command handler, tool `execute`, or event handler
against a fake Pi host instead. Where this package mirrors host behavior — the
supported thinking-level rule mirrors `getSupportedThinkingLevels` from
`@earendil-works/pi-ai` — add a parity test against the host function so the
copy cannot drift.
