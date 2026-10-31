# Repository Guidelines

## Project Structure & Module Organization

Packages live in `packages/*`, with `index.ts` loading `src/` or `extensions/`.
Directories differ from npm names: `continual-learning`/`kit` publish
`pi-continual-learning`/`@fradser/pi-kit`. List bundled Markdown, templates,
and scripts in manifest `files`. Package/root `features/` and `tests/` hold
contracts and checks.

## Build/Test/Development Commands

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm pack:check
pnpm check
```

`pnpm check` requires Python 3 with pytest and Bun 1.4.1 and runs
package/root tests, the extension TypeScript project, and registry-free
packed-manifest validation. CI installs both runtimes before this command.
Focus: `uv run pytest packages/<name>/tests/ -q` (or `python3 -m pytest packages/<name>/tests/ -q`).
Pack: `pnpm --dir packages/<name> pack --dry-run`.
SDK example: `pnpm example:sdk`. Pi loads TypeScript without a build step.

## Coding Style & Naming Conventions

Use strict ESM TypeScript (ES2022; Node ≥20), kebab-case modules, snake_case
tools. No formatter/linter is configured; match local style, which overrides the
global Biome preference. Extensions declare
`"pi": { "extensions": ["./index.ts"] }`; Pi-core/TypeBox imports are peers.

## Shared Runtime: pi-kit

Prefer internal `@fradser/pi-kit` for shared helpers/infrastructure:
`"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
If absent, record the gap; invent no replacement or unverified registry dependency.

## Testing Guidelines

Start behavior changes with a failing regression and the global Given/When/Then,
RED, GREEN, refactor loop. Keep `test_*.py` and Node/tsx harnesses in `tests/`;
run both suites and tsc. Runtime changes require `pnpm check:install` and
live `pi --print` verification; test TUI interactively. Package moves must
update installed paths in `~/.pi/agent/settings.json`.

### Test & Experiment Language Separation

Keep TypeScript packages and Python experiment harnesses cleanly separated:
- **TypeScript/Node packages**: Package extensions, tools, widgets, and schemas must have their unit/contract tests run natively in Node/Bun (`bun test` or `tsx --test`). Never write Python tests that act as trivial bridges by embedding JavaScript strings and invoking `subprocess.run(["node", ...])` or `run_bun`.
- **Python for Experiments & Research**: Python is a first-class language in this repo for continual-learning studies, Docker harnesses, AI experiment loops, data analysis, and repository verification. Python test suites and study harnesses (`uv run pytest`) run independently and parallelized with `pytest-xdist`.

## Real Pi Terminal Verification

For TUI changes, run the actual `pi` CLI in an interactive terminal or a PTY.
Renderer/unit tests and `pi --print` do not prove input ownership, viewport
composition, focus, navigation, or resize behavior.

- Use a disposable cwd and agent directory with isolated `HOME` and
  `PI_CODING_AGENT_DIR`. Keep user settings, credentials and package installation
  unchanged. For offline fixture runs, use a deterministic local provider,
  `PI_OFFLINE=1`, and disable unrelated extensions, skills, prompt templates,
  themes, context files and built-in tools; load only the fixture extension.
  Isolation flags are test conditions, not production defaults.
- Spawn `pi` through `pty.openpty()` (or the existing interactive terminal).
  Set dimensions with `TIOCSWINSZ`; resize the same live component and send
  `SIGWINCH`. Exercise 120x40, 48x24 and a short-height case such as 48x12.
  Do not recreate a component and call that a live-resize test.
- Send actual terminal key bytes through the PTY: arrows, Enter, Escape,
  Ctrl-C, Ctrl-O and PageUp/PageDown. Include SS3/CSI variants for custom key
  handling. Synchronize on lifecycle/menu/render events and input release;
  drain output before capture. Fixed sleeps are not acceptance conditions.
- Walk complete paths: command entry, empty/loading/error states where present,
  long lists, list ends and navigation actions, full-body start and tail,
  search input, detail close, parent return, retained selection, and exit.
  Check meaningful labels and essential actions remain readable, not merely
  that rendered lines fit. Check resize preserves the logical reading position.
- Retain raw PTY bytes, terminal dimensions, ordered interactions and structured
  renderer events. Inspect the composed terminal screen as well as component
  lines. ANSI-to-text alone loses cursor placement, color and occlusion; use a
  terminal-state parser for captures and keep its resize sequence. Label images
  reconstructed from terminal bytes as reconstructions, not OS screenshots.
  Record source revision/local changes and capture provenance; never retain
  authentication values or private user data in evidence.
- Distinguish evidence: real CLI + deterministic fixture proves native display
  and interaction only; real-model/service learning and persistent mutations
  require separate acceptance. Test RPC with actual `--mode rpc` requests and
  `extension_ui_response` dialogs; native custom UI is unavailable there.
  Report unverified screen-reader, physical-terminal/theme, service and mutation
  cases explicitly. Never weaken validation to obtain a green result.

Read @packages/continual-learning/AGENTS.md before a continual-learning TUI
audit, Harness run, or learning study.

## Extension Architecture

- Activate state-dependent tools with `pi.setActiveTools()` only after valid
  transitions; remove on exit/invalid restore. Results identify state,
  synchronous outcome, pending intent, and next actor.
- Use pi-kit lifecycle renderers, `renderShell: "self"`, and empty `renderCall`.
  Prefer direct APIs, bounded/sanitized output, abort propagation, and explicit
  headless/missing-auth handling. Shared worker JSON uses atomic tmp+rename.
- UI reference: @packages/btw/src/overlay.ts. `ctx.ui.custom` owns input;
  widgets stay passive, width-bounded, spinner-aligned. Never intercept global
  terminal input.
- Workflow menus are commands; routing uses `before_agent_start`. Do not
  register custom user-interaction tools (`gh_confirm`, `git_ask_name`); use
  TUI menus, slash commands, or native prompts instead.
- Flow/procedure starts are abstract lifecycle lines, never full-text dumps:
  send the procedure via `pi.sendMessage({ customType: "<pkg>-procedure",
  content, display: true, details }, { deliverAs: "followUp", triggerTurn:
  true })` and render it with `pi.registerMessageRenderer` as one
  `[<pkg>] started · <subject>` row (bold `customMessageLabel` prefix,
  `safeDisplayText` subject). Tool starts render the same shape through
  pi-kit lifecycle renderers in `renderResult`. Full content stays in LLM
  context; the transcript shows only the line. Reference:
  @packages/impeccable/src/index.ts, @packages/matt-pocock/src/index.ts.

## Task Records

Record work in `packages/tasks` when a request has several steps or several
files, or when the work outlives the turn. A single edit is not a task.

- `create_task` records the work, its `dependsOn`, and its completion gate.
- `update_task` moves it: `in_progress` takes it, `completed` delivers it with
  its evidence, `pending` reopens it. One call may carry both a content edit and
  a status change; a refused status keeps the edit.
- `get_task` reads one task in full. `list_tasks` reads the list.

A goal is not a task. A goal is one objective that keeps running until it is
met. A task is one unit of work in a list you order, take, and finish.

The task tools do not reach a child process. A subagent cannot take or complete
a task, so the leader records the outcome from the child's report.

## Decision Boundaries & Completion

- **Sign-off**: Contributors and agents modify package code, add or adjust
  tests/features, fix failures, publish to npm, change remote branches, and run
  destructive operations without intermediate sign-off. Report each remote or
  destructive operation, and its result, in the completion evidence. The global
  agent guidelines hold the general boundary rules.
- **Completion gate**: Local work is complete when the target package's tests
  pass (`python3 -m pytest packages/<name>/tests/ -q`), `pnpm typecheck` passes,
  and `pnpm --dir packages/<name> pack --dry-run` confirms manifest packaging.

## Commit & Pull Request Guidelines

Use @.git-agent/config.yml Conventional Commit scopes (`feat(mp):`, `fix(mon):`).
Commit via git-agent with `session_context` intent, exact staging, `--no-stage`;
never bare git add/commit. No PR template: describe packages, behavior,
verification, release impact. Update both READMEs for package/install changes.

Published changes require Changesets; CI versions/publishes after the version
PR merges. Keep @scripts/publish-release.mjs's explicit allowlist pi-kit-first
and packed manifests free of `workspace:` protocols.

## Memory

Search before adding decisions. Keep safe `.memory/` files byte-identical with
canonical `~/.pi/agent/memory/<escaped-cwd>/`; private entries stay private.
Use `name`/`description`/`type` frontmatter, **Why**, and **How to apply**.

Read @packages/continual-learning/AGENTS.md before a continual-learning study,
a paid service call, or a Memory-correction run.
