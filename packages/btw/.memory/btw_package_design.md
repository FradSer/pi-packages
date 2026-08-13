# btw package design

`packages/btw` implements `/btw <question>` — side questions shown in a full-width
interactive popup above the input box that never enter the session history.

## Read-only enforcement

The side question runs as a child `pi --print --mode json --no-session` process with a
strict allowlist: `--tools read,grep,find,ls --exclude-tools bash,edit,write`. This is
stronger than Claude Code's /btw (which infers from context only) because the child CAN
verify facts by reading the codebase — but can never modify anything. `bash` is excluded
even though it is arguably "read-only capable" because a shell is an escape hatch.

## Zero history pollution

- `--no-session` on the child — its exchange is never persisted.
- The `/btw` command is consumed by the extension (extension commands skip the input
  event), so the invocation itself is not recorded as a session message.
- The overlay never touches `sessionManager`.

## Display: interactive bottom popup (overlay)

User feedback (Aug 12): the answer must be a **full-width popup above the input box
with adaptive height** — and it must be interactive (mouse scroll + esc close). The
widget approach (setWidget) was tried and dropped: widgets are non-interactive displays
— no keyboard, no mouse, no esc.

The overlay (`ctx.ui.custom(..., { overlay: true })`) is the right primitive:
- `anchor: "bottom-center"`, `width: "100%"`, `margin: { bottom: 4 }` → full-width
  panel right above the input box.
- Adaptive height: `render()` returns content-sized lines (short answers shrink the
  panel, long answers cap at ~40% of terminal rows via `maxAnswerBody`).
- `CancellableLoader` drives the spinner; its signal kills the child on escape.
- Escape closes (handleInput), arrows/pgup/pgdn/home/end scroll.

## Mouse wheel: impossible for extension UI (pi core limitation)

pi fullscreen mode uses TuiAltScreen, which registers its viewport input listener
FIRST in the input-listener chain (`addInputListener` in the constructor) and
unconditionally `{ consume: true }` for every wheel/mouse sequence
(`handleViewportInput` → `parseWheelEvent`/`parseSgrMouseEvent`). `TuiBase.handleTerminalInput`
returns on the first `consume`, so `ctx.ui.onTerminalInput` extensions never see mouse
events. Keyboard scrolling is the only option without a pi core change (forwarding mouse
to focused overlays/widgets).

## Widget approach (tried and dropped)

`createBtwOverlay` used `ctx.ui.custom(..., { overlay: true })` with a state machine
(loading -> answer/error) and hand-rolled scrolling. It was replaced by the widget
because a modal overlay captures focus and was the wrong shape. The scrolling/padding
lessons are preserved below.

## Spawner

`resolvePiCli` (verified against the pi package manifest, same approach as teammate's
spawner) + JSONL `message_end` parsing for the final text and usage
(`message.usage.cost.total`). Long prompts (>8k chars) go to a temp `@file` arg.
