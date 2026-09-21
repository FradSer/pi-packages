# @fradser/pi-recap

## 0.1.11

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.1.10

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- b0231e3: Replace the recap line with a single identity-only `Recapping...` activity row while a recap is generating instead of stacking the marker above a stale `✦ Recap:` line, and let pi-kit live activity widgets omit the `· <activity>` suffix when no fallback activity is configured.
- b0231e3: Drop the repeated current-recap text from the `/recap` menu title and merge the model override into one `Select recap model` option: dismissing the picker without choosing a model clears the stored override so recap generation falls back to the session default.
- bcb0054: Retry recap generation once when the model returns empty or generic verb-plus-identifier output, and discard the result if the retry remains uninformative.
- ac83f4e: Use one canonical, hashed directory-session identity across keyboard, recap, and utils. Verify registry ownership before reading or removing records, preserve per-command keyboard failures through the serial queue, pair recaps with the latest complete answer, and ignore pre-cancelled, auth-cancelled, or late provider responses.
- efd5641: Make pi-kit own the whole live-activity status row, so no package can drift. The widget now formats the identity itself — bold in pi-kit's stable per-name accent palette, the same one `@name` segments use in report rows — and replaces the free-form `formatIdentity`/`formatActivity` hooks with one closed vocabulary: `activityFormat: "plain"` (muted, literal, unchanged default) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens; foreign ANSI is stripped, a streamed fence line is dropped, activity without visible width leaves an identity-only row, and the widget row truncates with `fit`). `renderLiveActivityIdentity`, `liveActivityMarkdownTheme`, and `renderLiveActivityMarkdown` are exported so console rows render identity and activity the same way instead of reimplementing either one.
  
  Context research and agent-teams teammate rows both request markdown activity: identified rows stop being colorless or warning-colored, well-formed markdown renders with the theme's tokens instead of literal markup, and status rows above the editor are now the same language in every package. agent-teams' console delegates to the shared renderer with a passthrough theme instead of keeping a second markdown implementation, and its roster, board, and report rows use the same per-agent accent for names and ids instead of a status-flavored palette. Every package that mounts a live widget is republished so it picks up the new pi-kit.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0

## 0.1.9

### Patch Changes

- 548363d: Keep pre-response recaps grounded in the user's request: describe work as starting or planned and do not claim unverified actions, files, connections, or results.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.1.8

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.1.7

### Patch Changes

- dcf3806: Start recap generation when the first user prompt arrives so the TUI immediately shows that the session is being recapped, then refresh the summary after the turn completes.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.1.6

### Patch Changes

- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.1.5

### Patch Changes

- 7ad11b4: Allow manual recap generation from the recap menu and `/recap now` to refresh an already-generated exchange instead of returning the cached recap.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0

## 0.1.4

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.1.3

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.1.2

### Patch Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.1.1

### Patch Changes

- 6eee038: Add a session recap widget: after each turn it summarizes what the session is doing (from the last user input and assistant output) and shows a concise one-liner above the TUI editor. Toggleable via `/recap`.
