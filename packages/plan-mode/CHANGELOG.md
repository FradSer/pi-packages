# @fradser/pi-plan-mode

## 0.2.0

### Minor Changes

- a61a89e: Keep planning read-only when execution is discussed or negated, and block extension tools, including overrides of built-in names, that bypass the plan-file guard. Fix direct model configuration, preserve the original model across repeated plan entry, and automatically review plans started through the interactive start flow. Preserve partial worker failures in writer context and avoid false failure diagnostics for successful research.
  
  Run `/plan <prompt>` in one minimal read-only pi-kit worker and await its completion in headless mode. Replace the custom timed overlay with Pi’s native selector and require an explicit current-session or new-session implementation choice.

## 0.1.7

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.1.6

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- ae01b20: Allow read-only bash pipelines and conditional chains while validating every stage. Reject malformed shell syntax and unsafe command options, and exercise the production validator in regression tests.
- ae01b20: Open plan review after the agent settles without blocking its lifecycle. Fresh-session implementation no longer waits on its own completion event, and dismissing review leaves new prompts ready to run.
- c9eb37d: Use bounded readable topic filenames for new plans, with numeric collision suffixes. Persist the exact plan path across session reloads, resumes, review, research, and fresh implementation without renaming existing files.
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

## 0.1.5

### Patch Changes

- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- dbca59c: Prevent infinite /plan review loop by showing plan overlay directly on completion and clearing active request state.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.1.4

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.1.3

### Patch Changes

- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

## 0.1.2

### Patch Changes

- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.1.1

### Patch Changes

- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
  - @fradser/pi-kit@0.2.0
