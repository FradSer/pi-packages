# @fradser/pi-recap

Session recap for Pi — shows a concise summary of what's happening above the TUI input box, inspired by Claude Code's `recap:` feature.

## Install

```bash
pi install npm:@fradser/pi-recap
```

## How it works

After each turn, the extension captures the last user message and assistant response, generates a one-line summary, and displays it at the top of the input box via `setWidget` with `placement: "aboveEditor"`.

```
recap  Refactoring the API client to use connection pooling...
```

The recap is generated in a background child Pi process — it never blocks the session.

## Commands

| Command | Description |
|---|---|
| `/recap` | Open the recap settings menu |
| `/recap on` | Enable recap display |
| `/recap off` | Disable recap display |
| `/recap auto` | Toggle auto-recap (generate after each turn) |
| `/recap now` | Generate a recap immediately from the last exchange |

## Settings

Persisted in `~/.pi/agent/recap/settings.json`:

- **recapEnabled** (default: `true`) — master toggle
- **autoRecap** (default: `true`) — generate recap automatically after each turn
- **recapModel** (optional) — model override for recap generation, e.g. `"anthropic/claude-haiku-3-5"`

## Design

- Uses the same prefix convention as Claude Code's `recap:` but rendered as a styled widget above the editor (not injected into the conversation).
- Generated from the last user message + assistant response, keeping the recap grounded in the current activity.
- Language-aware: the recap uses the same language as the conversation.
- Single-turn scope: each new turn replaces the previous recap.
- Non-blocking: the recap runs in a background child process; the user can type immediately.