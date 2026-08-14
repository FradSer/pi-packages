# Utils Pi Package

A pi-native package offering `/effort` for setting model thinking levels, `/继续` (`/continue`) for resuming interrupted tasks or continuing based on recommendations, multi-session directory awareness (`/sessions`, `/recap`), plus a git worktree path redirect.

## Installation

```bash
# published
pi install npm:@fradser/pi-utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Commands

### `sessions` & `recap` — cross-session directory awareness

`/sessions` (or `/recap`) lists active and recent Pi coding sessions in the current directory (`cwd`), including their PID, status, latest goal, and recent work.

```
/sessions                           # List active/recent sessions in cwd
/recap                              # Show directory session recap
```

**Features**:
1. **Cross-Session Awareness**: Multiple Pi sessions in the same project directory register their status, latest goal, and touched files in `~/.pi/agent/directory-sessions/`.
2. **Automated Prompt Injection**: When multiple sessions run in the same directory, `before_agent_start` automatically injects a concise directory recap into the system prompt so each agent is aware of parallel work.
3. **Dead PID Pruning**: Stale or dead process IDs are automatically detected (`process.kill(pid, 0)`) and cleaned up from the directory registry.
4. **Agent Tool (`list_directory_sessions`)**: Exposes a tool for agents to inspect active sessions in the directory programmatically.

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

A standalone, simple `git worktree add` bash command is rewritten so the
linked worktree lives inside `.pi/worktrees/<name>` instead of a sibling
directory:

```
git worktree add ../foo feature/foo
# → mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo
```

The redirect preserves Git's documented `worktree add` options, including
`--lock` (a flag), `--reason <string>`, `--orphan <branch>`, `-b <branch>`,
`-B <branch>`, and the optional `<commit-ish>`. It preserves quoted and escaped
path arguments, and leaves an already redirected path untouched.

For safety, it only rewrites the direct `git worktree add` form. Commands with
shell operators, redirections, substitutions, expansions, malformed quoting,
unknown options, or extra arguments are left unchanged rather than being
partially rewritten.

## License

MIT
