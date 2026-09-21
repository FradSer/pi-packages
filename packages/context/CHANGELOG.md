# @fradser/pi-context

## 0.6.3

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.6.2

### Patch Changes

- ac83f4e: Prevent pre-cancelled child workers from spawning, fail closed on bounded worker stream violations, and disable extension discovery for isolated side-question and research children.
- 9cabb0d: Bump every package by one patch version.
- 6d21149: Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
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

## 0.6.1

### Patch Changes

- Keep context research as a stateless one-shot worker with a package-local typed builder that builds a concrete prompt from the current request and working directory, and retries an empty successful answer exactly once. The transcript renders `[context] research started · <research query>` on start with live progress only in the researcher widget above the editor (no duplicate progress row), and a compact expandable `[context] researched` band on completion.
- Render live research activity with Pi's native Markdown styling while preserving the compact, sanitized, width-bounded widget and its spinner lifecycle.
- Prevent the research call renderer from crashing Pi when streamed arguments do not yet contain a string query.

## 0.6.0

### Minor Changes

- 61e7692: Replace provider-specific retrieval tools with `context_get`, which delegates context research to an isolated Pi child process.

### Patch Changes

- a3d72d7: Render `/context` workflow prompts as one expandable lifecycle message.
- 548363d: Make the injected context-retrieval guidance proactive: natural-language search requests (e.g. "帮我搜索") now route to `context_exa`, library/API questions to `context_context7`, and public-repo questions to `context_deepwiki`, with trigger phrasing in both the system-prompt guidance and the tool-level prompt guidelines.
  
  `context_exa` no longer requires `EXA_API_KEY`: without a key it queries Exa's public keyless endpoint (`mcp.exa.ai`, same JSON-RPC/SSE pattern as DeepWiki); with a key it upgrades to the full-text `api.exa.ai/search` REST API.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2

## 0.5.1

### Patch Changes

- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.

## 0.5.0

### Minor Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.
