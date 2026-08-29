# @fradser/pi-monitor

## 2.1.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 2.1.0

### Minor Changes

- 02ec642: Add bounded monitor timeouts. `monitor_start` accepts `timeout_ms` and emits a terminal `timeout` result after the deadline, stopping the process group instead of waiting indefinitely when an external CLI or API is unavailable.

### Patch Changes

- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- 6664765: Collapse repeated source-labelled diagnostic lines in terminal monitor results and include their occurrence counts to keep timeout and failure reports concise.
- dcf3806: Clarify monitor guidance so quick, low-output information commands run directly while noisy, long-running, or asynchronous work uses `monitor_start`.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 2.0.5

### Patch Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · delivered|queued` row carries the outcome (plus a dim stalled-duration suffix), replacing the duplicated call-plus-sentence transcript rows. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 2.0.4

### Patch Changes

- 50c45ff: Share compact tool lifecycle labels through pi-kit and standardize monitor startup and terminal event rendering.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 2.0.3

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.

## 2.0.2

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 2.0.1

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 2.0.0

### Major Changes

- e55e25e: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result with a bounded diagnostic tail. Remove the model-facing `monitor_read` output reader so agents wait for the contracted terminal notification instead of polling.

## 1.0.0

### Major Changes

- e09c395: Replace raw progress-log streaming with result-contract monitoring. `monitor_start` now requires `result_pattern`, supports an optional `failure_pattern`, scans stdout and stderr without injecting progress into model context, and emits one structured terminal result. Add `monitor_read` for bounded, on-demand diagnostics and retain recent completed monitor output for inspection.

## 0.1.1

### Patch Changes

- 1c5e807: Rename to @fradser/pi-monitor and publish for the first time.
