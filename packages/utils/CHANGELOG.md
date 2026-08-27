# @fradser/pi-utils

## 0.4.0

### Minor Changes

- 8905dbd: Add Claude Code-style EnterWorktree and ExitWorktree session switching. Pi can
  create or enter a git worktree through a replacement session, rebind built-in
  tools and @ completions to that worktree cwd, return to the parent session, and
  optionally clean up worktrees created by Pi.
- edccd2f: Block package publish and npm credential commands (`publish`, `login`/`adduser`/`logout`, `token create/revoke/delete`) from the agent's non-interactive bash tool. These flows cannot complete there — 2FA web-auth exits immediately with EOTP and dead tokens surface as masked 404 PUT failures — so the guard blocks the call and returns corrective steering that routes the interactive step to the user's own terminal and the `npm-package-first-release` skill procedure.
- 8905dbd: Add git worktree-aware @ completions: editor file suggestions now hide paths
  that resolve inside another git worktree. A session in main never sees linked
  worktree contents, and a session inside a linked worktree never sees sibling
  worktrees or the main checkout.

### Patch Changes

- dcf3806: Preserve paragraph and bullet line breaks in `/init` instructions while letting Pi's TUI wrap long lines to the available width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.3.7

### Patch Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.3.6

### Patch Changes

- 7ad11b4: Make /continue always retry with the current model and configuration: remove error classification gating that turned stale persisted failures into permanent refusals even after switching models or fixing config, drop the redundant auth preflight, strip consecutive failed assistant messages from retried context while keeping tool-call/result pairs intact, route the continuation keyword through the registered /continue command, and remove the internal __continue command from the command menu.
- 9edc0a6: Preserve the selected session-tree node when continuing: /continue reloads the same session only when the disk tip is unknown to the active session, while entries written by another process are still inherited before retrying.
- 7ad11b4: Render `list_directory_sessions` with the shared compact tool display pattern: self-rendered shell, empty call slot, and one `[sessions] listed · N other sessions in <dir>` result row styled like monitor terminal events (custom-message label color on the custom-message background). Expanding reveals a bounded block per session with status, pid, relative age, goal, recap, and recent files; every display field is sanitized with the new shared `safeDisplayText` and truncated to bounded lengths.
  
  Registry reads now normalize untrusted records on read (numeric pid/timestamps, known status union), merge records from multiple writers (extension state and keyboard glow state use different id conventions) into one logical session per owning process, and exclude records owned by the current process regardless of id, so counts and listings are no longer doubled.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.3.5

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.3.4

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.3.3

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.3.2

### Patch Changes

- 40d0127: Expand `/continue` recovery to handle provider/model API errors and truncated responses, preserving useful error details while avoiding repeated completed work.

## 0.3.1

### Patch Changes

- 89337a2: Rename to @fradser/pi-utils and publish for the first time.
