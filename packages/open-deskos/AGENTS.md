# Repository Guidelines

## Project Structure

`packages/open-deskos/` publishes `pi-open-deskos`. Package root `index.ts`
re-exports `src/index.ts`. Implementation is in `src/`:
- `discovery.ts`: machine-wide Pi session discovery (`~/.pi/agent/directory-sessions/`), PID liveness checks, UUID alias merging, and bounded refresh.
- `session-identity.ts`: process identity extraction, title detection, and exit status tracking.
- `reporter.ts`: Desk Link session/event telemetry reporting, offline queueing, exponential capped backoff, and state-resync on reconnect.
- `events.ts`: Pi transcript and tool event serialization, markdown preservation, and frame bounds.
- `control-transport.ts` & `transport.ts`: socket connection to Desk Link, NDJSON framing, and keepalive/teardown.
- `console-client.ts`: hosted Pi attach/detach protocol, operation tracking, catch-up replay, and history paging.
- `console-extension.ts`: `/open-deskos` command handler, Pi TUI input integration, headless fallback, and diagnostic notices.
- `types.ts`: protocol schemas for Desk Link v2.

BDD contracts live in `features/`; executable tests live in `tests/`.

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/open-deskos/tests/ -q
node --test packages/open-deskos/tests/*.test.mjs
pnpm --dir packages/open-deskos pack --dry-run
```

## Style and Architecture

- **Transport Safety & Reconnect**: Keep transport connections resilient to socket
  drops and server restarts. Outages buffer up to 300 offline events; reconnection
  replays retained tails before live events. Disconnect and stop must cleanly invalidate
  stale socket callbacks and timers.
- **Diagnostic Hygiene**: `/open-deskos` emits status and telemetry diagnostics exclusively
  through command notices. Never mutate terminal status or replacement footers on
  unsolicited background events or link state transitions.
- **Strict Bounds & Framing**:
  - Session discovery caps scanned entries at 64 sessions (prioritizing running, then recent).
  - Telemetry frames split at 1 MiB (`MAX_FRAME_BYTES`) NDJSON limits.
  - Assistant message bodies are capped at 16 KiB; tool outputs preserve code/tables within bounded limits.
- **Control Boundaries**: Without configured credentials (`ODK_DESK_LINK_TOKEN`), the machine
  operates report-only and registers no desk tools. Hosted Pi context injection must never trigger
  an autonomous model loop.
- **Headless Degradation**: The console surface uses Pi TUI `Input` for IME text when interactive;
  it falls back cleanly to non-interactive diagnostic text when TUI is unavailable.

## Testing Guidelines

`features/` defines BDD behaviors. Unit and integration tests in `tests/` are split:
- `test_*.py`: pytest integration checks covering configuration, manifest compliance, connection lifecycle, and background report safety.
- `*.test.mjs`: Node test runner suites covering session discovery limits, NDJSON frame boundary handling, multiline event serialization, and console client attach/replay logic.
The pack manifest must include `index.ts`, `src`, `fixtures`, and `README.md`.
