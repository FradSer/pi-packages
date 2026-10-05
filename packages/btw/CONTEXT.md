# btw Working Context

## Current state

- Context budgets include the truncation marker. Zero limits return empty context.
- Overlay focus delegates to native Input. Completed turns do not override host focus.
- Home and End edit the visible composer. While loading, they navigate the transcript.
- Native wheel events scroll the answer. Cache invalidation preserves active animation.
- Layout measures controls before assigning answer space. Compact mode supports 20 columns and 8 rows.
- Smaller sizes display the size requirement and a close action.
- Shared scroll windows clamp negative offsets. Optional horizontal-rule callbacks style native separator text and preserve existing kit defaults.
- Injected host keybindings handle configured cancellation in loading and idle states. Literal Escape remains available.
- btw no longer interprets authored separator-marker text as layout metadata.
- Package guidance and mouse claims are corrected. Package memory matches its canonical local copy.
- No generic chat framework or shared cancellation state machine is added.

## Verification

- Before fixes, new focus and animation regressions fail. Earlier probes reproduce negative scrolling and 16-row overflow.
- Latest broad run: 228 tests pass across btw, kit, goal, and recap.
- Minimum-size regressions cover a long loading model label and keyboard reachability of the final answer line.
- Latest PTY rerun passes actual normalized wheel routing, page scrolling, follow-up cancellation, resize to 20 by 8, and close.
- Root and btw TypeScript checks pass. btw and kit pack dry-runs pass.
- Installation checks pass: 17 workspace Pi packages, 18 settings entries.
- Final screen pixels, manual IME placement, and production child-provider interaction are not established by the model-free PTY fixture.

## Review

- Prior simplification and height-reserve reviews pass.
- Design review accepts ownership recommendations. Its raw-wheel fallback, native separator, memory evidence, and acceptance corrections are incorporated.
- Implementation review finds two blockers: loading controls exceed the minimum budget and keyboard scrolling uses the old budget.
- Both are fixed and regression-tested. Loading controls fit the height limit; all navigation uses the measured viewport.
- Independent turn3 review closes both blockers and finds no new scoped runtime blockers.
- Reviewer verifies cancellation in initial, idle, error, and follow-up states, including configured keys and literal Escape.
- Independent turn4 review confirms all blockers and public compatibility concerns are closed on the current candidate.
- Zero-argument hr calls retain the legacy marker. Custom callbacks receive native rule text.
- Reviewer reruns the original probes, three focused tests, and both btw and kit TypeScript checks; all pass.
- Final broad rerun: 228 tests pass after the public type correction.
- Design report: @../../docs/research/btw-tui-design-20261002.md. Its findings describe the pre-fix candidate.

## Boundaries

- User authorization covers all reported TUI findings, changed composer keys, and compact layout.
- Preserve unrelated working-tree changes, including concurrent kit edits.
- Do not publish or commit without authorization.
