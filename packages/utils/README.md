# @fradser/pi-utils

A pi-native package offering `/effort` for setting model thinking levels, `/继续` (`/continue`) for resuming interrupted tasks, `/init` for scoped `AGENTS.md` contributor guides, multi-session directory awareness (`/sessions`), private live-session control, and git worktree isolation.

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
│   ├── live-sessions.ts  — Live-session socket lifecycle
│   ├── live-sessions/    — Protocol, client, server, and transport
│   ├── worktree.ts       — git worktree add path redirect
│   ├── worktree-completion.ts — worktree-aware @ filtering
│   └── worktree-session.ts — EnterWorktree / ExitWorktree session switching
├── features/             — BDD contract
├── tests/                — Package E2E tests
└── README.md
```

## Installation

```bash
pi install npm:@fradser/pi-utils
```

Requires Pi 0.85.1 or newer for command dispatch during session transitions.

## Commands

### `init` — repository contributor guides

`/init` asks the active agent to inspect the repository and create or update
scoped `AGENTS.md` files. It audits existing instructions, removes stale or
overprescriptive rules, and preserves useful guidance in independent directory
scopes. There is no word quota or required section template: documentation is
referenced by task, and safe local autonomy and completion boundaries must be
supported by repository evidence. Relevant skill recommendations favor precise
triggers and progressive disclosure; skill files are not edited unless requested. The prompt is repository-agnostic: it derives the toolchain,
shared-module conventions, and contribution workflows from the target project's
files rather than prescribing this package's development policies. Outside a Git
checkout, it uses the starting directory as the project root and omits unavailable
history. An optional argument adds focus:

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
1. **Cross-Session Awareness**: Multiple Pi sessions in the same project directory register their status, latest goal, and touched files in `~/.pi/agent/directory-sessions/`. Directory names use pi-kit's canonical hashed identity, so slash-versus-hyphen paths remain separate; existing paths use `realpath` and missing paths use their absolute spelling.
2. **Automated Prompt Injection**: When multiple sessions run in the same directory, `before_agent_start` automatically injects a concise directory recap into the system prompt so each agent is aware of parallel work.
3. **Dead PID Pruning**: Stale or dead process IDs are automatically detected (`process.kill(pid, 0)`) and cleaned up from the directory registry. Reads and cleanup verify the record's canonical `cwd`; foreign or malformed records remain untouched when ownership cannot be proven, and old directory names are not migrated.
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

## Live session control

Installing `@fradser/pi-utils` also enables private discovery and text delivery
to running Pi sessions without terminal input injection or session-file edits.
It is available on Unix/macOS with Node 20+.

The extension reports live instances and their `idle` or `running` state through
its internal versioned protocol. Text delivery returns `accepted` or `queued`;
neither receipt means the task completed. Busy sessions default to `followUp`,
while `steer` requests steering. Request IDs make retries replay-safe, and a
live instance ID changes when Pi reloads, resumes, forks, or restarts.

Sockets live in `~/.pi/live-sessions`, overridable for integration hosts with
`PI_UTILS_LIVE_SESSIONS_DIR`. The user-owned directory is mode 0700 and sockets
are mode 0600. The feature opens no TCP listener and treats same-user processes
as trusted. Inputs, text, discovery, socket paths, timeouts, and replay receipts
are bounded. This is an internal `@fradser/pi-utils` capability; the package
does not publish a separate live-session executable or package.

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
checkout. The built-in `read`, `edit`, and `write` tools also block direct access to a
foreign worktree and direct the agent to `enter_worktree`. This prevents stale
absolute file paths from modifying the parent checkout after switching. Worktree roots are discovered once per session via
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
`exit_worktree` tools defer these commands until the current agent run settles
and report `queued` until session replacement is applied. Other tools in the
same transition batch are blocked, regardless of their order. After entering,
Pi resumes the pending task through the replacement context with an explicit
active-cwd instruction. Relative file operations and shell commands then run
in the selected worktree. This is not a shell sandbox: explicit shell paths
must still target the active worktree. Their TUI uses the same pi-kit lifecycle style as
`monitor_start`: an empty tool-call row followed by one compact event row,
for example `[worktree] enter · feature-auth` or
`[worktree] exit · current worktree`.

`/exit-worktree` returns to the parent session. For worktrees created by Pi, it
asks whether to keep or remove the worktree; dirty work is kept unless the user
explicitly chooses forced removal. Existing worktrees are never removed by
this command.

## License

MIT
