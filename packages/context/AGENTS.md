# Repository Guidelines

## Package Scope

`packages/context/` publishes `@fradser/pi-context`, a Pi skill and extension
that exposes native DeepWiki, Context7, and Exa retrieval tools, plus clone and
web-fetch fallbacks. Keep its README, `skills/context/SKILL.md`, extension
behavior, and BDD scenarios aligned when the public workflow changes. Reuse
`@fradser/pi-kit` for shared runtime helpers whenever that workspace package is
available; follow the parent guide for its dependency and release rules.

## Research before modifying this package

Before editing `packages/context/`, classify the change and use the applicable native context tool first. These are Pi extension tools, not MCP servers:

| Change type | First lookup | Fallback |
| --- | --- | --- |
| Pi API, package manifest, or TypeBox schema | `context_context7` | Local source inspection or official docs |
| Public repository architecture or DeepWiki API behavior | `context_deepwiki` | Git clone |
| Provider usage, integration patterns, or community examples | `context_exa` | Targeted web fetch |
| A change spanning multiple categories | All applicable tools | Use each method's fallback |

- `context_deepwiki`: use for changes involving a public repository's architecture, integration behavior, or DeepWiki API assumptions.
- `context_context7`: use for changes involving Pi APIs, package manifests, TypeBox schemas, or external library/API contracts.
- `context_exa`: use for changes involving real-world provider usage, current integration patterns, comparisons, or community examples. It requires `EXA_API_KEY`.

Do not call unrelated tools for documentation-only or local-test-only changes. For every applicable call, record the result in the implementation notes or change summary. If a tool is unavailable or fails, state why and use the documented fallback in the relevant skill: local source inspection, git clone, or targeted web fetch.

## Expected workflow

1. Add or update a BDD scenario under `features/`.
2. Run the applicable native context lookup(s) before implementation.
3. Add a regression/unit test and confirm it fails before the fix when behavior changes.
4. Implement the smallest change.
5. Run `pnpm test` and package/type checks relevant to the change.
6. Review the diff for stale MCP claims and verify package contents with `pnpm pack --dry-run` when packaging changes.

## TUI Interaction & Styling Standards

All interactive terminal UI components in Pi extensions (popups, overlays, status widgets, interactive dialogs) MUST strictly adhere to the `@packages/btw` TUI interaction pattern:

### 1. Style Language & Theme Helpers
Never hardcode ANSI escape codes or assume direct Theme object access. Always map colors through theme styling callbacks/helpers:
- `accent`: theme-accent color (e.g. `theme.fg("accent", s)`) for primary highlights, spinners, titles (`Dreaming...`, `Answering...`), headings, and selected items.
- `muted`: theme-muted color (`theme.fg("muted", s)`) for secondary metadata, parameters, or subtle hints.
- `dim`: theme-dim color (`theme.fg("dim", s)`) for borders, separators, secondary info (` · tool_name`), and unselected/idle states.
- `border`: theme-border color (`theme.fg("border", s)`) for dividing rules and panel frames.
- `error` / `warning` / `success`: semantic theme colors (`theme.fg("error", s)`, etc.) for status indicators.

### 2. Component Structure: Title + Detail Layout
For status displays and widgets (such as `setWidget`), follow the compact single-line title + detail structure:
- **Format**: `${icon} ${title}${detail}`
- **Icon**: Braille spinner frame (`SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]`) styled with `accent`.
- **Title**: Short, prominent title styled with `accent` (e.g. `Dreaming...` or `Answering...`). Do NOT pad with verbose explanatory sentences.
- **Detail**: Optional, dynamic activity text prefixed with ` · ` and styled with `muted` or `dim` (e.g. ` · read package.json`).

### 3. Modal Overlays (`ctx.ui.custom`)
When rendering interactive overlays or modal consoles:
- **Input Ownership**: Use `ctx.ui.custom` so the component exclusively owns keyboard input without polluting pi's global input dispatch (`onTerminalInput`).
- **Standard Controls**: 
  - `Esc` / `q`: Close or cancel.
  - `↑` / `↓`: Line-by-line selection/scroll.
  - `Enter`: Confirm selection or submit.
- **Render Boundaries**: Constrain height (e.g. max ~40% terminal height) and calculate responsive text wrapping with `truncateToWidth` / `wrapTextWithAnsi` using the provided render `width`.
- **Clean Lifecycle**: Always register a `dispose()` handler to clear timers (e.g. `clearInterval`), unref timeouts, and release TUI resources when closed.
