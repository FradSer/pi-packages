# @fradser/pi-context

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
