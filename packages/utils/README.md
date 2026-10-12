# @fradser/pi-utils

A pi-native package offering `/effort` for setting model thinking levels, `/autoname` for model-generated session names, `/继续` (`/continue`) for resuming interrupted tasks, `/init` for scoped `AGENTS.md` contributor guides, multi-session directory awareness (`/sessions`), private live-session control, npm publish guarding, and git worktree isolation.

## Structure

```
text
utils/
├── index.ts              — Package-root extension entry point
├── extensions/
│   ├── autoname.ts       — /autoname model-generated session name
│   ├── continue.ts       — /continue and continuation keyword interception
│   ├── effort.ts         — /effort thinking-level menu
│   ├── init.ts           — /init repository guide generation
│   ├── sessions.ts       — /sessions directory awareness + listing tool
│   ├── live-sessions.ts  — /live-sessions command + live-session socket lifecycle
│   ├── live-sessions/    — Protocol, client, server, and transport
│   ├── npm-publish-guard.ts — publish/credential guard
│   ├── worktree.ts       — git worktree add path redirect
│   ├── worktree-completion.ts — worktree-aware @ filtering
│   ├── worktree-session.ts — EnterWorktree / ExitWorktree session switching
│   └── git/worktrees.ts  — Shared git worktree plumbing (one porcelain parser,
│                           one canonicalizer, one .pi/worktrees definition)
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

An idle session runs the guide task at once; a busy one queues it as a follow-up
and says so. A delivery that is rejected reports the reason instead of leaving
the task looking queued.

### `sessions` — cross-session directory awareness

`/sessions` lists active and recent Pi coding sessions in the current directory (`cwd`), including their PID, status, latest goal, and recent work.

```
/sessions                           # List active/recent sessions in cwd
```

**Features**:
1. **Cross-Session Awareness**: Multiple Pi sessions in the same project directory register their status, latest goal, and touched files in `~/.pi/agent/directory-sessions/`. Directory names use pi-kit's canonical hashed identity, so slash-versus-hyphen paths remain separate; existing paths use `realpath` and missing paths use their absolute spelling. A session that moves between directories (for example by entering a worktree) removes its record from every directory it registered under when it shuts down.
2. **Automated Prompt Injection**: When multiple sessions run in the same directory, `before_agent_start` automatically injects a concise directory recap into the system prompt so each agent is aware of parallel work.
3. **Dead PID Pruning**: Stale or dead process IDs are automatically detected (`process.kill(pid, 0)`). A dead process whose record is still fresh is reported with status `exited` so recent work stays visible, and the record is deleted once it is stale. Reads and cleanup verify the record's canonical `cwd`; foreign or malformed records remain untouched when ownership cannot be proven, and old directory names are not migrated.
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
is clamped to the model's capabilities, and the confirmation reports the level
pi actually applied, so a clamped request never reads back as the requested one.
The menu is narrowed with the same
rule pi itself applies (a model without reasoning only gets `off`; a `null`
`thinkingLevelMap` entry hides a level; `xhigh`/`max` need explicit entries).
Argument completions list the canonical levels and their aliases regardless of
model support, because Pi offers completions without a command context.

### `autoname` — model-generated session name

`/autoname` asks the current model to name the session from what the
conversation is actually about. An optional argument steers the name:

```
/autoname                        # name from the conversation
/autoname release notes rewrite  # name, steered by the argument
```

Pi's own `/name` is compiled into the interactive mode: submitting it with no
argument and no name set answers `Usage: /name <name>`. An extension cannot
replace it, because that built-in branch runs before extension commands are
consulted. `/autoname` is therefore the model-generated counterpart. Use
`/name <name>` when you want to choose the name yourself.

The name is built from the user's own requests only, so it describes the task
rather than the assistant's wording. The request asks for the subject of the
work as a noun phrase and shows one good name against one bad one, so a session
is listed as `Worktree root selection` and not as `Fix the utils package`. A
model answer is reduced to a plain
display name: quoting, markdown, list markers, and any sentence after the first
line are dropped, and a long name is cut at a word boundary.

Generation always settles. A deadline of 20 seconds, an aborted session, a
missing model, absent credentials, a provider rejection, and an unusable answer
each report their own cause instead of hanging the command. A provider that
ignores its abort signal cannot hold the command open, because the deadline
races the request rather than only signalling it.

The name request asks for no reasoning. A reasoning model shares one response
budget between its thinking and its answer, so a small budget would be spent
before any name exists.

The request is a bounded one-shot: no tools, an output budget of at most 1024
tokens that leaves room for reasoning, no caching, and the current session id is
forwarded so conversation-routing gateways accept the nested call.

## npm publish guard

Bash calls that would publish a package or run an npm credential flow are
blocked, because they cannot succeed from a non-interactive shell (2FA
web-auth exits immediately with EOTP, and an invalid token surfaces as a masked
404 PUT on unpublished packages):

```
npm publish            # blocked
pnpm -r publish        # blocked
pnpm publish --dry-run # allowed: the exemption is scoped to that exact flag
npm login              # blocked
npm token create       # blocked
```

The block reason carries the corrected procedure: verify credentials, ask the
user to run the command in their own terminal, then verify the registry and
let CI own future versions. Never ask for OTP codes in chat. In a pnpm
workspace the reason redirects the command to `pnpm publish`, because `npm
publish` does not rewrite `workspace:*` protocols; outside one the warning is
conditional and the command is reported unchanged.

## Live session control

Installing `@fradser/pi-utils` also enables private discovery and text delivery
to running Pi sessions without terminal input injection or session-file edits.
It is available on Unix/macOS with Node 20+.

The extension reports live instances and their `idle` or `running` state through
its internal versioned protocol. Text delivery returns `accepted` or `queued`;
neither receipt means the task completed. Busy sessions default to `followUp`,
while `steer` requests steering. Request IDs make retries replay-safe, and a
live instance ID changes when Pi reloads, resumes, forks, or restarts.

The `/live-sessions` command is the capability's only entry point:

```
/live-sessions                                  # list live instances
/live-sessions <sessionId> please re-run the failing test
/live-sessions steer <sessionId> stop and summarize
```

Session ids are offered as argument completions, the listing is capped at ten
rows, and delivery arguments are length-checked before any socket call. A
discovery failure reports its cause, and a session that cannot open its socket
says so when it starts, so an unusable control directory never reads as an
empty one.

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

The managed directory belongs to the repository, not to the shell's directory:
a command issued from a subdirectory is rewritten to the absolute
`<repo root>/.pi/worktrees/<name>`, so the worktree lands in the same place
`/enter-worktree` and the isolation filters look. When the repository does not
git-ignore `.pi/`, the redirect reports that the linked worktree would appear
as untracked; the extension never edits a repository's `.gitignore`.

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
same transition batch are blocked, regardless of their order, and the block
reason names the pending transition. Aborting the run drops the queued
transition and says so instead of leaving the model believing one is coming; a
worktree command issued while a transition is queued is refused rather than
racing it. After entering, Pi resumes the pending task through the replacement
context with an explicit active-cwd instruction. Relative file operations and
shell commands then run in the selected worktree. This is not a shell sandbox:
explicit shell paths must still target the active worktree. Their TUI uses the
same pi-kit lifecycle style as `monitor_start`: an empty tool-call row followed
by one compact event row, for example `[worktree] enter · feature-auth` or
`[worktree] exit · current worktree`.

`/exit-worktree` returns to the parent session. For worktrees created by Pi, it
asks whether to keep or remove the worktree; dirty work is kept unless the user
explicitly chooses forced removal. Existing worktrees are never removed by
this command.

Both commands wait for a running turn to finish before they switch, because a
session replacement aborts the active turn. A cancelled switch removes the
worktree, branch, and forked session file it created. A switch that fails after
replacement was requested keeps the worktree for its edits and reports the path,
branch, and removal command, so nothing is silently left behind.

## License

MIT
