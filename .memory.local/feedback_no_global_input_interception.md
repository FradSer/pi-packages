---
name: no-global-input-interception
description: extensions must not drive widgets with onTerminalInput — it breaks pi's model selector/history/dialogs; own input via ctx.ui.custom instead
type: feedback
---

Never intercept keys globally (`ctx.ui.onTerminalInput`) to drive a passive widget in a pi extension. The listener runs BEFORE pi's keybinding dispatch, so consuming Enter/Esc/arrows hijacks pi's own UI — the teammate panel consumed Enter and broke the model selector (`ctrl+l`), and plain ↑/↓ fought prompt-history navigation.

**Why:**
The teammate TUI originally used `onTerminalInput` to catch Shift+↑/↓ + Enter + Esc + x against a `setWidget` panel. Each fix (Kitty CSI-u sequences, engagement windows, try/catch) treated a symptom; the model selector still broke because the global listener consumed Enter while pi's overlay was open. The correct model: a component that OWNS input (`ctx.ui.custom`) — inside it ↑/↓/Enter are safe; outside it pi owns everything.

**How to apply:**
1. Interactive extension UI = `ctx.ui.custom(factory)` (owns input) or `ctx.ui.select/confirm/input` dialogs — not `onTerminalInput`.
2. A `setWidget` is display-only: render state, never consume keys.
3. If you must listen to raw input, only consume keys that are uniquely yours, never generic Enter/Esc unconditionally — but prefer not listening at all.
4. Wrap any listener body in try/catch so a handler error can never break pi's input dispatch.
5. Full-screen views use `ctx.ui.custom` WITHOUT `{ overlay: true }` (overlay = popup rendered on top).

**Related:** [[pi-kitty-csi-u-keys]] [[pi-custom-component-rendering]] [[teammate-autonomous-and-tui]]
