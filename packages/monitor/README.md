# Monitor Pi Package

Background process monitoring for Pi — run a shell command in the background and
stream its stdout to the agent as notifications, so the agent reacts to logs,
deploys, CI runs, or file changes the moment something happens. No polling loops.

**Version**: 0.1.0

## What This Package Does

Like Claude Code's Monitor tool, `@fradser/monitor` turns the agent
event-driven: launch a watcher, go quiet, and wake up only when something
interesting appears in the output stream.

### Extension

The extension (`src/index.ts`) registers 3 tools and 1 command:

| Tool / Command | Description |
|---|---|
| `monitor_start` | Run a shell command in the background; stream its stdout to the agent |
| `monitor_list` | List active monitors (id, description, command, status, notifications, age) |
| `monitor_stop` | Stop a monitor by id, or all active monitors |
| `/monitor` | Full-screen console to inspect and stop active monitors |

### Semantics

- **stdout only** drives notifications. Each batch of stdout lines (arriving
  within 200ms) becomes one `[monitor ...]` message that wakes the agent via
  `pi.sendMessage(..., { deliverAs: "steer", triggerTurn: true })`.
- **Noise control via `match`**: pass a case-insensitive regex so only matching
  stdout lines wake the agent. Non-matching lines are suppressed and counted,
  then reported when the monitor ends — so a verbose build stays quiet until
  the one line you care about appears.
- **stderr** is captured but does not trigger notifications; it is reported in
  the final message when the monitor ends.
- **Timeout**: non-persistent monitors auto-stop after `timeout_ms` (default
  300000 / 5 min, max 3600000 / 1 hr). Set `persistent=true` to run for the
  whole session.
- **Event cap**: a monitor auto-stops after 40 notifications to protect context.
- **Session-scoped**: all monitors are killed on session shutdown.

### UI

- A widget below the input box shows `N monitor(s) running — /monitor to inspect`
  while monitors are active (display only — never intercepts keys).
- `/monitor` opens a full-screen console: `↑`/`↓` select, `x` stop the selected
  monitor, `a` stop all, `q`/`Esc` close.

## Installation

```bash
pi install npm:@fradser/monitor
# or from this repo:
pi install /path/to/pi-packages/packages/monitor
```

## Usage

```
monitor_start command="tail -f /var/log/app.log" description="errors in app.log"
monitor_start command="pnpm test 2>&1" description="test failures" match="fail|error|TypeError"
monitor_start command="gh run watch --exit-status" description="CI run status" timeout_ms=900000
monitor_list
monitor_stop monitor_id="monitor_1"
```

Consult `/skill:using-monitor` for the full usage guide.
