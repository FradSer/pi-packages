# Repository Guidelines

## Project Structure

`packages/utils/` publishes `@fradser/pi-utils`, a native Pi extension. `index.ts`
only wires the focused modules in `extensions/`: `/continue`, `/effort`, `/init`,
`/sessions`, private live-session socket control, npm publish/credential guarding,
git worktree path redirect, worktree-aware `@`
completions, and EnterWorktree/ExitWorktree session switching. BDD contracts live in
`features/`; executable Python tests and runtime harnesses live in `tests/`.
The published package is limited by `package.json`'s `files` list (`index.ts`,
`extensions/`, and `README.md`).

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/utils/tests/ -q
pnpm --dir packages/utils pack --dry-run
```

## Style and Architecture

Keep command behavior in its corresponding extension and `index.ts` as
composition-only wiring. Preserve explicit `.ts` relative imports in this
package; its entry point is exercised through native Node and tsx.

- **Worktree Session Switching (`enter_worktree`, `exit_worktree`)**:
  - *Session Forking*: Uses `SessionManager.forkFrom` to replace the session with a worktree-rooted one instead of mutating `process.cwd`. Tools terminate their batch and dispatch `/enter-worktree` or `/exit-worktree` only at `agent_settled` (`expandPromptTemplates: true`, Pi ≥0.85.1). Block sibling tools and keep the barrier active until dispatch; resume work only through the replacement context.
  - *Foreign Worktree Protection*: Non-session worktrees are foreign checkouts; `read`, `edit`, and `write` block access until entered via `enter_worktree`.
  - *Progressive Tool Disclosure*: `exit_worktree` is activated via `pi.setActiveTools()` only when currently inside a worktree-created session.
- **Directory Sessions (`list_directory_sessions`)**:
  - Reads `~/.pi/agent/directory-sessions/`, filters dead PIDs, and collapses multi-writer records by PID.
  - Dynamically exposed via `pi.setActiveTools()` only when active/recent peer sessions exist in cwd.
  - Sanitizes untrusted registry fields with `safeDisplayText` before prompt injection or transcript rendering.
- **Live Session Control**:
  - Uses private user-owned Unix sockets; never inject terminal input or edit session files.
  - Routes by opaque live-instance ID, preserves request-ID replay protection, and never treats accepted/queued as completion.
  - Keep this capability internal to `@fradser/pi-utils`; do not add a separate package or executable.
- **Publish Guard**: `extensions/npm-publish-guard.ts` checks command positions
  and exact dry-run flags. Preserve coverage for filtered/recursive publish
  forms; never route OTP codes through chat.

## Testing Guidelines

Match each extension with its contract under `features/` and tests under
`tests/`. Cover continuation recovery without breaking tool-call/result pairs,
known tree-leaf selection versus unseen disk appends, model-supported thinking
levels, safe worktree rewriting, queued versus applied session replacement,
registry deduplication, and npm guard parsing.
