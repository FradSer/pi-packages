---
name: using-monitor
description: >
  Use when working with the monitor extension — running background commands and
  streaming their stdout to the agent as notifications. Load this skill when the
  user asks to watch logs, deploys, CI runs, file changes, or test output, or
  asks to set up a monitor/background watcher.
---

# Monitor Extension — Usage Guide

This skill documents the `@fradser/pi-monitor` Pi extension: background process
monitoring that streams a command's stdout to the agent as notifications, so the
agent reacts to events the moment they happen instead of polling.

## When to use it

Use `monitor_start` instead of `bash sleep`-polling loops whenever you need to
wait on something of unknown duration and react to its output:

- watching a deploy or CI run for errors
- tailing a log file for a specific message
- watching a file or directory for changes
- waiting for a server to print "ready" or an error

## Tools

| Tool | Purpose |
|---|---|
| `monitor_start` | Run a shell command in the background; stream its stdout to the agent |
| `monitor_list` | List active monitors with status and notification counts |
| `monitor_stop` | Stop a monitor by id, or all of them |

## Quick Start

```
1. Start watching a log:
   monitor_start command="tail -f /var/log/app.log" description="errors in app.log"

2. Watch a deploy, waking only on failures (noise-free):
   monitor_start command="pnpm test 2>&1" description="test failures" match="fail|error|TypeError"

3. Start a deploy watcher with a longer timeout:
   monitor_start command="gh run watch --exit-status" description="CI run status" timeout_ms=900000

4. List what is running:
   monitor_list

5. Stop one (or all):
   monitor_stop monitor_id="monitor_1"
   monitor_stop
```

## The noise problem — always prefer `match`

A monitor is event-driven, but a noisy command (a build, `npm install`, a
verbose deploy) prints hundreds of progress lines. Without a filter, every one
of those becomes a notification that wakes the agent — noise. When you are
waiting for ONE specific thing, pass `match` so the monitor stays quiet until
that thing happens:

- Only stdout lines matching `match` (a case-insensitive regex) wake the agent.
- Non-matching lines are suppressed and counted, then reported when the monitor
  ends as `[suppressed N non-matching stdout line(s)]`.
- Example: `match="error|fail|ready|TypeError"` watches for the interesting
  events and ignores the 1000 lines of progress in between.

## Semantics

- **stdout only** drives notifications. Each batch of matching stdout lines
  (arriving within 200ms) becomes one `[monitor ...]` message that wakes the agent.
- **stderr** is captured but does not trigger notifications; it is reported in
  the final message when the monitor ends.
- **Timeout**: non-persistent monitors auto-stop after `timeout_ms`
  (default 300000 / 5 min, max 3600000 / 1 hr). Set `persistent=true` to run
  for the whole session.
- **Event cap**: a monitor auto-stops after 40 notifications to protect context.
- **Session-scoped**: all monitors are killed on session shutdown.
- The command must not require interactive input.

## User-facing UI

- A widget below the input box shows `N monitor(s) running — /monitor to inspect`
  whenever monitors are active (display only, never intercepts keys).
- `/monitor` opens a full-screen console: `↑`/`↓` select, `x` stop the selected
  monitor, `a` stop all, `q`/`Esc` close.
