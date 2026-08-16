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

The answer is a **full-width popup directly over the main session input area**, with
adaptive height and interactive keyboard input. The widget approach (setWidget) was
tried and dropped: widgets are non-interactive displays — no keyboard, no mouse, no esc.

The overlay (`ctx.ui.custom(..., { overlay: true })`) is the right primitive:
- `anchor: "bottom-center"`, `width: "100%"`, `margin: { bottom: 0 }` → full-width
  panel covering the main session input area.
- Adaptive height: `render()` returns content-sized lines (short answers shrink the
  panel, long answers cap at ~40% of terminal rows via `maxAnswerBody` and remain scrollable without a hidden-line count).
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

## Multi-turn side conversation

- The overlay supports multi-turn replies without leaving the popup.
- When an answer is ready, an embedded `Input` component renders below the Markdown viewport.
- Submitting a follow-up question starts a new child turn with the accumulated side history passed in `buildBtwPrompt`.
- Token usage and cost aggregate across turns in the footer.
- Cancelling an in-flight follow-up with `esc` drops the pending turn and restores the previous completed conversation without closing the overlay.

## Spawner

`resolvePiCli` (verified against the pi package manifest, same approach as teammate's
spawner) + JSONL `message_end` parsing for the final text and usage
(`message.usage.cost.total`). Long prompts (>8k chars) go to a temp `@file` arg.
