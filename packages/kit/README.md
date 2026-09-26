# @fradser/pi-kit

Shared runtime helpers for the FradSer pi-packages monorepo. This is an
internal workspace dependency, **not** a Pi package: it has no `pi` manifest,
no skills, and no extensions. Consumer packages declare it as
`"@fradser/pi-kit": "workspace:*"` under `dependencies`. It declares two `"*"`
peers — `@earendil-works/pi-tui`, the bundled core TUI library pi reifies for
every extension module it loads and kit imports for shared live-activity
markdown rendering, and `@earendil-works/pi-coding-agent`, which its worker CLI
probe resolves at runtime — per pi's package guide for core imports. It has no
`dependencies` at all.

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
- `createLiveActivityWidget(options)` — package-owned passive widget controller that renders one or more active rows as `<spinner> <identity> · <latest activity>` using Pi's native cadence. It owns the lifecycle (TUI-only mounting, refresh, disposal) **and the whole row language**: `renderLiveActivityIdentity` paints the identity bold in pi-kit's stable per-name accent palette, and `activityFormat` picks one of exactly two activity formats — `"plain"` (default: muted, literal) or `"markdown"` (one sanitized line through pi-tui's Markdown with the injected theme's native markdown tokens). Every activity is flattened to a single row, foreign ANSI is stripped, and the widget truncates with `fit`. Callers retain worker state, activity extraction, and domain labels; no caller supplies an identity, an activity formatter, or styled text. A caller that passes `fallbackActivity: ""` asks for an identity-only `<spinner> <identity>` row with no activity suffix.
- `renderLiveActivityIdentity(identity, theme, prefix?)` / `liveActivityMarkdownTheme(theme)` / `renderLiveActivityMarkdown(text, theme)` — the shared row pieces, exported so console and overlay rows use the same identity and markdown activity rendering instead of reimplementing them. The identity renderer hashes the bare `identity` and prepends `prefix` (for example `"@"`), so a caller that prints `@name` gets the same accent as report rows. Pass a passthrough theme (`{ fg: (_color, text) => text }`) when the row paints its own color around the activity. `renderLiveActivityMarkdown` returns one line and takes no width: the caller (or the widget row) owns truncation. Activity is a streamed fragment, so a fence line is dropped; everything else renders exactly like pi's own streaming assistant text — the same pi-tui `Markdown`, the same `md*` tokens — which means a fragment that is still arriving mid-inline-markup shows that fragment's marker until the next activity replaces it, exactly as the transcript does.
- `setPiStatus` / `clearPiStatus` — sanitized set/clear adapters for package-owned transient status entries.
- `startPiWorkingIndicator` / `clearPiWorkingIndicator` — start the shared native-cadence spinner or restore Pi's default indicator.

### Messages

- `extractTextContent(content, separator = "\n")` — plain text from a pi
  message content value (string or content-block array). Non-text blocks
  contribute nothing; callers own trim/empty semantics.
- `createToolLifecycleMessageRenderer(options)` — structural custom-message renderer factory using the lifecycle band.
- `createStaticToolLifecycleMessageRenderer(options)` — compact custom-message factory that keeps model-only text out of the TUI row.
- `createToolLifecycleResultRenderer(options)` — structural native-tool result renderer factory. Partial results render on the toolPendingBg band, settled results on toolSuccessBg, and errors on the shared toolErrorBg band (first error line as subject, remaining lines expandable); pi-kit owns every state so consumers cannot drift.
- `bindLifecycleRenderers` + `eventToolLifecycle` — shared expansion path used by context research and coordination messages. Context keeps its query title plus distinct answer details, and an expanded body is complete: omit `detailLimit` for a full readback, or pass a number and the row names the lines it left out. Titles and summaries wrap in full on expansion through the injected native wrapper; `expandedSubject` is only needed when the collapsed subject is an intentional preview. Width fitting, native wrapping, configured key hints, and theme bands remain in pi-kit.
- `createStaticToolLifecycleResultRenderer(options)` — compact native-tool factory that keeps model-only text out of the TUI row.
- `scrubHandles(text, resolve?)` — replaces runtime handles only. It preserves surrounding literal quotes, spacing, and line breaks; consumers that want prose cleanup apply that separately, never to exact message readbacks.
- `notifyPi(ui, message, level)` — sanitized forwarding to Pi's native notification surface.

### Meaningful expansion contract

All four normal/static result/message factories use the same display-driven rule: an expand hint appears only when a bounded, nonempty `ToolLifecycleSpec.details` body is hidden, a full subject differs from its preview, or the current width hides title/summary text that expansion can reveal. Resizing recomputes the hint. Model-facing `content` and opaque `result.details` are not expansion signals; only their explicit projection into the display spec is.

- Consumers put the outcome in `subject`/`label`, essential always-visible content in `summary`, and supplementary evidence in `details`. Do not repeat a title's action or identifier as a detail merely to make it expandable.
- A short row with no supplementary information has no hint. Long or multiline titles and summaries use the injected native wrapper on expansion; collapsed summaries stay compact. Supply `wrapDetail` to recover width-clipped text. Legacy hosts without a wrapper can still expand explicit line breaks and detail bodies; pi-kit does not reimplement Pi's Unicode/ANSI wrapping.
- All-whitespace or control-only bounded detail bodies are empty. Within a nonempty body, paragraph spacing and repeated values are preserved. Pi-kit does not guess business semantics or deduplicate original reports.
- Authored rows opt in with `verbatimSubject` and `bgToken`. A verbatim subject renders raw: no `@name` recoloring, one band row per authored line, wrapping instead of merging, and no hint for text that is already visible. `bgToken: "userMessageBg"` echoes user-authored text on Pi's native user-message band while hidden details keep their own hint row. `subjectBlock` keeps the head, one blank band row, and the authored lines apart instead of an inline `[tool] label · subject` row.
- Error bands use the first error line as the title and subsequent evidence as details. They follow the same width/expansion rule.
- `renderToolLifecycle` retains its explicit low-level `expandable` override for legacy hosts that own additional content outside the standard body. Standard factories never set it from machine metadata; new consumers should use the display spec instead.

Read @features/pi-kit.feature when changing this contract and run `python3 -m pytest packages/kit/tests/ -q`. Consumer tests must also verify that removed display fields remain available in machine results and persisted state. With Pi installed, `tests/test_live_expansion.py` exercises the real offline CLI in print mode and a PTY, native host mouse expansion where supported (explicitly reported unavailable on older Pi), Ctrl+O, and 48/90/240-column resizing using a temporary home and scripted provider; it does not use user credentials or an external model.

### One-shot workers

- `minimalPiWorkerArgs(tools)` — builds the common `--print --mode json --no-session -ne -ns -np -nc --no-themes --tools <allowlist>` arguments for packages that own a one-shot child-process lifecycle.
- `runPiWorker(options)` — runs a one-shot JSONL worker with pre-cancel checks. Set `minimal: true` to use those shared minimal arguments; combine it with `tools` for an explicit allowlist. It also provides close-observed cancellation and byte limits of 16 MiB for stdout, 8 MiB for
  stderr, and 8 MiB for each JSONL line. The line bound leaves room for normal
  inline image payloads plus their JSON envelope. Limit failures terminate the
  child and return no assistant text.
- `getDirectorySessionKey(cwd)` — SHA-256 of the canonical directory path;
  existing paths use realpath and missing paths use an absolute path.
- `isSameDirectory(left, right)` — compares those canonical directory paths.

## Rules

- Zero runtime dependencies beyond Node built-ins; no imports of pi core or
  consumer packages (the dependency graph stays one-way).
- Package-owned prompt resources and typed binding rules stay in their consumer
  packages; pi-kit owns the one-shot process runtime, not prompt semantics or
  generated Agent identities.
- The package root `index.ts` re-exports the shared runtime from `src/index.ts`.
  The implementation remains a zero-internal-import module that resolves
  identically under Node's native type stripping, tsx, and tsc.
- Do not wrap what `@earendil-works/pi-tui` already exports
  (`wrapTextWithAnsi`, `truncateToWidth`, `visibleWidth`, `Key`,
  `matchesKey`, `isKeyRelease`) — consumers import those directly.

## License

MIT
