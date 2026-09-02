# @fradser/pi-kit

Shared runtime helpers for the FradSer pi-packages monorepo. This is an
internal workspace dependency, **not** a Pi package: it has no `pi` manifest,
no skills, and no extensions. Consumer packages declare it as
`"@fradser/pi-kit": "workspace:*"` under `dependencies`.

## API

### TUI

- `PI_SPINNER_FRAMES` — braille spinner frames identical to pi's native
  ` ⠋ Working...` loader row.
- `PI_SPINNER_INTERVAL_MS` — `120`, the native loader cadence.
- `createPiThemeStyle(theme)` — adapts any pi theme (`{ fg(color, text) }`)
  to the shared overlay/console style language:
  `accent` / `muted` / `dim` / `border` / `success` / `error` / `fg`.
  See `packages/btw` for the canonical layout that consumes it.
- `renderPiPanel({ width, style, fit, title, body, footer })` — standard bordered panel geometry for overlays and full-screen consoles. Consumers keep interaction, scrolling, and Markdown rendering; pi-kit supplies the shared frame.
- `computeScrollWindow(lines, scroll, maxBody)` — compute scroll window slice indices and clamped scroll offset for scrollable panels.
- `renderPiWidgetRow(content, width, fit)` — one leading-space, width-bounded passive status-widget row aligned with Pi's native rows.
- `setPiStatus` / `clearPiStatus` — sanitized set/clear adapters for package-owned transient status entries.
- `startPiWorkingIndicator` / `clearPiWorkingIndicator` — start the shared native-cadence spinner or restore Pi's default indicator.

### Messages

- `extractTextContent(content, separator = "\n")` — plain text from a pi
  message content value (string or content-block array). Non-text blocks
  contribute nothing; callers own trim/empty semantics.
- `createToolLifecycleMessageRenderer(options)` — structural custom-message renderer factory using the lifecycle band.
- `createStaticToolLifecycleMessageRenderer(options)` — compact custom-message factory that keeps model-only text out of the TUI row.
- `createToolLifecycleResultRenderer(options)` — structural native-tool result renderer factory; callers provide the host-native error component.
- `createStaticToolLifecycleResultRenderer(options)` — compact native-tool factory that keeps model-only text out of the TUI row.
- `notifyPi(ui, message, level)` — sanitized forwarding to Pi's native notification surface.

## Rules

- Zero runtime dependencies beyond Node built-ins; no imports of pi core or
  consumer packages (the dependency graph stays one-way).
- The package root `index.ts` re-exports the shared runtime from `src/index.ts`.
  The implementation remains a zero-internal-import module that resolves
  identically under Node's native type stripping, tsx, and tsc.
- Do not wrap what `@earendil-works/pi-tui` already exports
  (`wrapTextWithAnsi`, `truncateToWidth`, `visibleWidth`, `Key`,
  `matchesKey`, `isKeyRelease`) — consumers import those directly.
