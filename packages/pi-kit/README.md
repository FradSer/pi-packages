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

### Messages

- `extractTextContent(content, separator = "\n")` — plain text from a pi
  message content value (string or content-block array). Non-text blocks
  contribute nothing; callers own trim/empty semantics.

## Rules

- Zero runtime dependencies beyond Node built-ins; no imports of pi core or
  consumer packages (the dependency graph stays one-way).
- All code lives in `src/index.ts`: a zero-internal-import module resolves
  identically under Node's native type stripping, tsx, pi's extension loader,
  and tsc with any moduleResolution.
- Do not wrap what `@earendil-works/pi-tui` already exports
  (`wrapTextWithAnsi`, `truncateToWidth`, `visibleWidth`, `Key`,
  `matchesKey`, `isKeyRelease`) — consumers import those directly.
