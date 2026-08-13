# Frad's Pi Packages ![](https://img.shields.io/badge/packages-7-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable agent skills, extensions, and project workflows.

## Invocation

Skills are invoked with Pi's `/skill:<name>` command. Arguments are appended after the skill body. Pi does not expand `$ARGUMENTS` or run shell injections inside skill Markdown. Workflow packages use native commands instead (`/memory`, `/btw`, `/teammate`).

## Packages

### [`btw`](packages/btw/)

`/btw <question>` answers a side question in a read-only overlay above the input box. It never interrupts the current task and never enters session history. Unlike Claude Code's `/btw`, it calls read-only tools (`read`, `grep`, `find`, `ls`) to verify facts in the codebase, and it is strictly read-only: `bash`, `edit`, and `write` are always excluded.

**Command:** `/btw <question>`

**Installation:**
```bash
pi install npm:@fradser/pi-btw
# or from this repo: pi install /path/to/pi-packages/packages/btw
```

---

### [`code-context`](packages/code-context/)

Retrieves code context through DeepWiki, Context7, Exa, direct git clone, and web fetches. The retrieval methods are native pi tools (`context_deepwiki`, `context_context7`, `context_exa`) calling the public REST APIs directly; git clone and HTTP fetch always remain available as fallbacks.

**Skills:** `code-context`, `get-context`

**Installation:**
```bash
pi install npm:@fradser/code-context
# or from this repo: pi install /path/to/pi-packages/packages/code-context
```

---

### [`mattpocock`](packages/mattpocock/)

BDD-first engineering and productivity skills adapted from Matt Pocock's skills. Covers TDD, implementation, debugging, architecture, research, code review, planning, handoff, teaching, and skill writing.

**Skills:** `engineering`, `productivity` (with per-topic skills inside)

**Installation:**
```bash
pi install npm:@fradser/mattpocock
# or from this repo: pi install /path/to/pi-packages/packages/mattpocock
```

---

### [`memory`](packages/memory/)

Native `/memory` command for auto-memory guidance, an instructions menu, and memory consolidation (clustering, staleness checks, ground-truth verification, privacy validation). Consolidation runs as an inline procedure in a background worker. No skill surface.

**Command:** `/memory` menu (consolidate now, edit instructions, open auto-memory folder, toggle auto-memory) plus `/consolidate` for one-shot consolidation

**Installation:**
```bash
pi install npm:@fradser/pi-memory
# or from this repo: pi install /path/to/pi-packages/packages/memory
```

---

### [`monitor`](packages/monitor/)

Runs a shell command in the background and streams its stdout to the agent as notifications, so it reacts to logs, deploys, CI runs, or file changes the moment something happens. No polling loops.

**Tools:** `monitor_start`, `monitor_list`, `monitor_stop` · **Skill:** `using-monitor` · **Command:** `/monitor`

**Installation:**
```bash
pi install npm:@fradser/pi-monitor
# or from this repo: pi install /path/to/pi-packages/packages/monitor
```

---

### [`teammate`](packages/teammate/)

Multi-agent team system: register teammates, assign tasks, mailbox messaging, and autonomous child-Pi workers that watch their mailbox and decide when to close. Managed through the `/teammate` full-screen console.

**Tools:** `teammate_register` / `list` / `send` / `read_mailbox` / `assign_task` / `list_tasks` / `update_task` / `broadcast` / `spawn` / `task_deps` / `remove` / `cleanup` / `reset` / `update_model` · **Command:** `/teammate` · **Skill:** `using-teammate`

**Installation:**
```bash
pi install npm:@fradser/teammate
# or from this repo: pi install /path/to/pi-packages/packages/teammate
```

---

### [`utils`](packages/utils/)

Pi-native utility commands: `/effort` sets the session thinking level (menu or inline, e.g. `/effort max`), `/continue` (or `/继续`) resumes from an interrupted step or continues the previous response, and `git worktree add` paths are redirected into `.pi/worktrees/`.

**Commands:** `/effort`, `/continue` · `/继续`

**Installation:**
```bash
pi install npm:@fradser/pi-utils
# or from this repo: pi install /path/to/pi-packages/packages/utils
```

## Notes

The `git-agent` pi package moved to the git-agent repo (`git-agent/git-agent-pi-package`); it exposes the `commit` / `commit-and-push` workflow via `/git-agent` (AI atomic commits through the git-agent CLI), no skill surface. The `memory` package follows the same menu pattern (`/memory`, no skill surface).

## SDK Harness

`examples/sdk-session.ts` shows a programmatic `createAgentSession()` consumer that wires package extensions and inspects discovered skills.

```bash
pnpm example:sdk
# or directly:
npx tsx examples/sdk-session.ts
# optional live model turn:
PI_SDK_LIVE=1 npx tsx examples/sdk-session.ts
```

## Adding a Package

1. Create a package directory under `packages/`.
2. Add `package.json` with the `pi-package` keyword and a `pi` resource manifest.
3. Add skills, extensions, prompts, or themes under the paths declared in `package.json`.
4. Install the local package with `pi install /path/to/pi-packages/packages/<name>` and run its tests.
5. Run `/skill:update-readme` to synchronize both README files.

## Publishing

Packages are published to npm under the `@fradser` scope and appear in the [pi.dev/packages](https://pi.dev/packages) gallery via the `pi-package` keyword.

```bash
pnpm install          # install workspace dev dependencies
pnpm publish          # publish all packages (pnpm -r publish --access public)
pnpm publish:dry-run  # build tarballs to inspect package contents
```

## Licensing

Each package declares the MIT license in its own manifest. The repository does not have a separate root license file.
