# pi-btw-fradser

Side questions for Pi — `/btw <question>` answers a quick side question in a full-width
overlay directly covering the main session input area, **without interrupting the current task and without ever
entering the session history**.

## Why btw

Claude Code's `/btw` answers from conversation context only — it cannot call tools, so
"what does function X do?" gets answered from what the model happens to remember. `btw`
fixes that:

1. **Tool-capable.** The side question runs in a fresh child Pi process that CAN call
   read-only tools (`read`, `grep`, `find`, `ls`) to verify facts in the actual codebase.
2. **Strictly read-only.** Only `read`, `grep`, `find`, `ls` are allowed. `bash`, `edit`,
   and `write` are always excluded — a side question can look, but can never touch.
3. **Zero history pollution.** The child runs with `--no-session` and the `/btw` command
   is consumed by the extension (never recorded as a session message). The exchange is
   gone the moment the display clears.

## Install

```bash
pi install npm:pi-btw-fradser
```

Restart pi, then use `/btw <question>` in interactive mode.

## Usage

```text
/btw what does the --force flag do on git push?
/btw where is the retry logic for the API client?
/btw how do we handle pagination in this repo?
```

The answer appears in a **full-width popup anchored to the bottom of the terminal**
(directly covering the main session input area), with height adapting to the content:

- Spinner while the read-only child answers (same model as your session; override with
  the `BTW_MODEL` env var, e.g. `BTW_MODEL=anthropic/claude-sonnet-4-5`).
- **Multi-turn conversation.** Type follow-up questions directly in the overlay input prompt and press **`enter`** to continue the side thread.
- **`esc`** closes (or cancels while loading).
- **`↑`/`↓`** scroll, **`pgup`/`pgdn`** page, **`home`/`end`** jump.
- Short answers shrink the panel; long answers cap at ~40% of the terminal height and
  remain scrollable without adding a hidden-line count to the answer.
- The footer shows aggregated token usage and cost for the side conversation.

Mouse-wheel scrolling is **not** available: in pi's fullscreen TUI the wheel is owned by
the chat viewport (pi consumes all mouse events before extensions can see them). If you
want the wheel to scroll extension panels, that needs a pi core feature — the package
uses keyboard scrolling instead.

The question is answered with the last ~4 user/assistant messages of the current session
as compact read-only context (capped at 4000 characters), so it can answer about what you
are working on right now — and then verify it against the actual files. Answers are kept
concise: the child is instructed to stay within 150 words or 600 characters, use at most
five short bullets, and avoid report-style summaries.

## Design

| Piece | What it does |
|-------|--------------|
| `src/spawner.ts` | Spawns `pi --print --mode json --no-session` with `--tools read,grep,find,ls --exclude-tools bash,edit,write`; parses the JSONL stream into the final answer + usage. |
| `src/context.ts` | Builds a compact most-recent-first excerpt of session user/assistant messages (4 messages, capped at 4000 chars). |
| `src/overlay.ts` | The interactive popup: loading spinner → answer, `esc` closes, arrows/pgup/pgdn/home/end scroll, height adapts to content (capped at ~40% of the terminal). |
| `index.ts` | Package-root entry point that loads the extension. |
| `src/index.ts` | Registers the `/btw` command and wires context → child process → overlay. |

## Requirements

- pi interactive (TUI) mode — the display needs a terminal.
- The same provider credentials as your main session (the child reuses your env).

## License

MIT
