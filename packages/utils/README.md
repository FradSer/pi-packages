# Utils Pi Package

A pi-native package offering `/effort` for setting model thinking levels, `/继续` (`/continue`) for resuming interrupted tasks or continuing based on recommendations, `/init` for creating or updating scoped `AGENTS.md` contributor guides, multi-session directory awareness (`/sessions`), git worktree session switching, plus git worktree path and `@` completion isolation.

## Structure

```
text
utils/
├── index.ts              — Package-root extension entry point
├── extensions/
│   ├── continue.ts       — /continue and continuation keyword interception
│   ├── effort.ts         — /effort thinking-level menu
│   ├── init.ts           — /init repository guide generation
│   ├── sessions.ts       — /sessions directory awareness + listing tool
│   ├── worktree.ts       — git worktree add path redirect
│   ├── worktree-completion.ts — worktree-aware @ filtering
│   └── worktree-session.ts — EnterWorktree / ExitWorktree session switching
├── features/             — BDD contract
├── tests/                — Package E2E tests
└── README.md
```

## Installation

```bash
# published
pi install npm:@fradser/pi-utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Commands

### `init` — repository contributor guides

`/init` asks the active agent to inspect the repository and create or update
scoped `AGENTS.md` files. It checks existing guides before writing, preserves
useful instructions, and keeps root and nested guides aligned without
needless duplication. An optional argument adds focus:

```
/init
/init focus on package release commands
```

### `sessions` — cross-session directory awareness

`/sessions` lists active and recent Pi coding sessions in the current directory (`cwd`), including their PID, status, latest goal, and recent work.

```
/sessions                           # List active/recent sessions in cwd
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
1. **Input Interception**: Intercepts plain text `continue` and routes it according to the last turn state.
2. **Direct Recovery**: For interrupted, failed, truncated, pending, or tool-error turns, starts a request from the existing conversation state without adding `continue` or an internal instruction as a user message. A hidden marker is removed before the provider request, along with every trailing incomplete assistant response (automatic provider retries can stack several); an assistant tool-call message always stays paired with its saved tool results.
3. **Current-Configuration Retry**: Failures are never re-classified into permanent refusals. After switching models or fixing configuration, the very next `/continue` retries on whatever model and configuration are current.
4. **Suggestion Continuation**: Only after a normally completed assistant turn does `/continue` become a visible user request, allowing the continuation instruction to remain in the transcript and model context.
5. **Session Recovery and Tree Selection**: Before continuing, the last persisted entry is checked against the active session index. The same session file is reloaded only when another process has appended an entry the active session has never loaded. If the user navigated to an earlier tree node, the known selected leaf remains authoritative and continuation starts there instead of resuming the abandoned failed branch.

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

## Git worktree-aware @ completions

Editor file suggestions (`@`) are filtered to the session's own git worktree:
a session in main never suggests linked worktree contents, and a session
inside a linked worktree never suggests sibling worktrees or the main
checkout. Worktree roots are discovered once per session via
`git worktree list --porcelain`; outside a git repository nothing is filtered.
Quoted and `@`-prefixed values are resolved (relative, absolute, and `~/`
forms) before the containment check.

## EnterWorktree / ExitWorktree

Pi cannot mutate the current runtime's `cwd` in place. These commands use Pi's
session replacement API so the built-in `read`, `edit`, `bash`, and `@` tools
are all rebound to the selected worktree:

```text
/enter-worktree feature-auth
/enter-worktree {"path":".pi/worktrees/existing"}
/exit-worktree
```

`/enter-worktree` creates a managed worktree at `.pi/worktrees/<name>` on a
`pi/worktree/<name>` branch, or enters an existing registered git worktree when
`path` is supplied. The replacement session preserves the current conversation
and records the parent session. The LLM-facing `enter_worktree` and
`exit_worktree` tools queue these commands and report `queued` until the session
replacement is applied. Their TUI uses the same pi-kit lifecycle style as
`monitor_start`: an empty tool-call row followed by one compact event row,
for example `[worktree] enter · feature-auth` or
`[worktree] exit · current worktree`.

`/exit-worktree` returns to the parent session. For worktrees created by Pi, it
asks whether to keep or remove the worktree; dirty work is kept unless the user
explicitly chooses forced removal. Existing worktrees are never removed by
this command.

## License

MIT
