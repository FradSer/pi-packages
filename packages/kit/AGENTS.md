# Repository Guidelines

## Structure

`index.ts` re-exports the shared runtime from `src/index.ts`; the implementation intentionally remains a single module. `src/index.ts` contains spinner constants, theme/style and layout helpers, compact labels, Pi child-process spawning/progress/termination, message text extraction, and model-reference/menu helpers. BDD scenarios are in `features/pi-kit.feature`, and executable Python checks are in `tests/`.

## Commands

From the repository root:

```bash
python3 -m pytest packages/kit/tests/ -q
pnpm exec tsc --noEmit -p packages/kit/tsconfig.json
pnpm --dir packages/kit pack --dry-run
```

## Style and architecture

Use explicit public types, small pure helpers, and structural callback
interfaces rather than Pi core imports. Keep `src/index.ts` free of internal
imports so Node type stripping, tsx, and tsc resolve it identically. Consumers
supply `wrapTextWithAnsi`, `truncateToWidth`, `visibleWidth`, and key helpers
from Pi TUI; do not duplicate them here. Preserve the native 120 ms spinner
cadence, `PiThemeStyle`, child close/termination semantics, and `provider/model`
validation.

## Testing Guidelines

`features/pi-kit.feature` and `tests/test_pi_kit.py` exercise runtime helpers
and consumer dependency hygiene. Test lifecycle width/expansion, sanitization,
model selection, abort escalation, and CLI resolution. Keep the manifest free
of `pi`, `pi-package`, dependencies, and peer dependencies; retain the root
TypeScript export.

## Shared Tool Lifecycle & UI Primitives

- Result/message factories have normal and `createStaticToolLifecycle*`
  variants; keep host components, width callbacks, and configured expansion
  hints injected, not imported.
- `formatToolLifecycleTitle` returns sanitized plain text, not colored output.
  Omitted labels omit the middle segment; `kind` is layout metadata, not a
  visible generic verb.
- `startedToolLifecycle` accepts a label; `eventToolLifecycle` also accepts
  summary/details and `detailLimit`. Expanded details default to 50 lines;
  reserve `"all"` for explicit full readbacks.
- `verbatimSubject` renders an authored subject raw: no `@name` recoloring, one
  band row per authored line, wrapping instead of merging, and no expand hint for
  text that is already visible. `subjectBlock` moves the subject under the head
  (`[tool] label`, one blank band row, then the authored lines) and drops the
  inline ` ·` separator. `bgToken` picks the band tint; `userMessageBg` marks
  user-authored content.
- Keep `safeDisplayText`, `formatToolErrorLine`, and `detailField` safe for
  untrusted values. Native dialogs remain consumer-layer APIs, outside this
  dependency-free runtime.