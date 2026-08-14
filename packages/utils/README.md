# Utils Pi Package

A pi-native package offering `/effort` for setting model thinking levels, `/继续` (`/continue`) for resuming interrupted tasks or continuing based on recommendations, plus a git worktree path redirect.

## Installation

```bash
# published
pi install npm:@fradser/pi-utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Commands

### `continue` — resume or continue execution

`/continue` (or simply typing "continue" in conversation):

```
/continue                           # resume from interrupted step or continue based on last suggestion
/continue Please focus on performance  # optional custom follow-up prompt
```

Behavior:
1. **Input Interception**: Intercepts plain text `continue` and transforms it into explicit instructions for the model to pick up where it left off.
2. **Interrupted Step Recovery**: If a tool execution failed or was interrupted, prompts the model to inspect error details and retry from the interrupted step.
3. **Model/API Failure Recovery**: If the provider request ends with `stopReason: "error"`, classifies context overflow, authentication, quota/billing, malformed requests, transient provider failures, and safety/content blocks. Deterministic failures show an actionable error instead of blindly retrying.
4. **Truncated Response Recovery**: If the response ends with `stopReason: "length"`, resumes from the last completed step without repeating completed work. Empty-output truncation is treated as possible context exhaustion.
5. **Incomplete Tool Recovery**: Handles pending/tool-use turns and tool results caused by truncated arguments, invalid tool calls, permission blocks, or execution failures.
6. **Suggestion Continuation**: If the previous assistant message ended with steps or recommendations, prompts the model to continue implementing them.

### `effort` — set the thinking level

`/effort` with no argument opens a menu of the thinking levels the current
model supports (the current level is marked). With an argument it sets the
level directly:

```
/effort          # menu
/effort max      # set directly
/effort min      # aliases: min, med, xh, none, 0
```

Valid levels: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
Unknown values are rejected with a hint listing the valid levels. The level
is clamped to the model's capabilities, and the menu is narrowed to what the
model actually supports (a reasoning-off model only gets `off`).

## Git worktree redirect

Any `git worktree add` bash command is transparently rewritten so the linked
worktree lives inside `.pi/worktrees/<name>` instead of a sibling directory:

```
git worktree add ../foo feature/foo
# → mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo
```

Flags (`-b`, `-B`, `--reason`, `--lock`) and trailing positional arguments
(branch, start commit) are preserved, and a path that is already inside
`.pi/worktrees/` is left untouched.

## License

MIT
