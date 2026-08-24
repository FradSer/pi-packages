# @fradser/pi-utils

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
