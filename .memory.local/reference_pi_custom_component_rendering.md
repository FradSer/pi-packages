---
name: pi-custom-component-rendering
description: ctx.ui.custom render(width) must word-wrap/truncate to the terminal width — raw lines overflow and are unreadable; non-overlay custom = full screen
type: reference
---

A `ctx.ui.custom` component's `render(width)` receives the terminal width and must fit its output: word-wrap long lines with `wrapTextWithAnsi(line, width - N)` and truncate with `truncateToWidth(line, width)`. Returning raw long lines overflows the terminal — the teammate detail page was "completely unreadable" until wrapped.

**Why:**
The teammate full-page view returned message bodies as raw lines; at 60 columns long bodies spilled past the right edge and rendered as garbage. `Text` from `@earendil-works/pi-tui` also does word-wrap; scroll can be implemented by windowing full lines then wrapping each.

**How to apply:**
1. `render: (width) => [...]` — never ignore `width`; wrap every line with `wrapTextWithAnsi` and/or truncate with `truncateToWidth`.
2. Full-screen page: `ctx.ui.custom(factory)` WITHOUT `{ overlay: true }` (overlay keeps the screen and renders on top).
3. Scrollable page: keep an offset into the unwrapped line list, slice a window, wrap each line, show a `(scroll a-b/N — ↑/↓)` hint.
4. Widgets (`setWidget`) render too — truncate lines to `width - 1`.

**Related:** [[pi-kitty-csi-u-keys]] [[no-global-input-interception]] [[teammate-autonomous-and-tui]]
