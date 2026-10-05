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
- Escape closes or cancels. Arrows and page keys scroll. Home and End scroll only while loading.

## Mouse and compact layout

Pi 1.0.0 routes normalized wheel events to overlays. btw handles these events without parsing terminal mouse protocols.
Regular mode retains terminal-owned scrollback. Keyboard navigation remains available.

The overlay delegates focus to its native Input. Home and End edit the visible composer.
Small terminals remove decorative spacing. The minimum size is 20 columns and 8 rows.
The answer viewport uses the space remaining after measured controls and panel rows.

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
