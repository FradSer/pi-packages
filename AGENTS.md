# Repository Guidelines

This is a pnpm monorepo of native Pi packages. Each directory under `packages/`
is independently installable and follows Pi package conventions.

## Project Structure & Module Organization

- `packages/<name>/` contains the ten published packages: `agent-teams`, `btw`,
  `context`, `keyboard`, `mattpocock`, `memory`, `monitor`, `recap`, `utils`, and
  `vision`. Shared runtime code belongs in the internal `pi-kit` package when
  that workspace package is available.
- Package code lives in `src/` or `extensions/`; distributable skills,
  procedures, and agents use their corresponding directories.
- BDD scenarios are in `features/`; executable tests are in `tests/`.
- Root release metadata lives in `.changeset/` and `.github/workflows/`.
  `README.md` and `README.zh-CN.md` document the published package surface.

## Build, Test, and Development Commands

```bash
pnpm install
pnpm test
npx tsc --noEmit -p tsconfig.extensions.json
```

`pnpm test` runs the Python test suite across `packages/`; run a single package
with `python3 -m pytest packages/<name>/tests/`. Use `pnpm pack --dry-run`
inside a package to inspect its published contents. There is no separate build
step; Pi loads the TypeScript extensions and packaged resources directly.

## Coding Style & Naming Conventions

Use ESM TypeScript targeting Node 20 or newer, follow the surrounding file's
indentation, and keep package names and command/tool names explicit and stable.
Manifests need the `pi-package` keyword, a `pi` resource declaration, complete
`files` entries, and Pi core packages as peer dependencies. Do not add Claude
Code plugin artifacts or Claude-only skill frontmatter. Use package-manager
commands such as `pnpm add` instead of hand-editing dependency manifests.

## Shared Runtime: pi-kit

Prefer the internal `@fradser/pi-kit` runtime for reusable helpers and shared
Pi-package infrastructure before adding duplicate code to a package. It is a
workspace runtime dependency, not a Pi package: consumer manifests use
`"@fradser/pi-kit": "workspace:*"` under `dependencies`, never
`peerDependencies`, and it has no `pi` manifest. Keep its dependency direction
one-way: pi-kit may use Node built-ins, but must not import consumer packages.
If the package is not present in the current checkout, do not invent a local
replacement or external registry dependency; record the gap and coordinate the
shared package first. Keep the release allowlist and pack/install checks in sync
when pi-kit is introduced or changed.

## Testing Guidelines

Write or update a `.feature` scenario before behavior changes, then add tests
under the package's `tests/` directory. Python tests use `pytest`; test modules
follow `test_*.py`. Run the affected package tests and the strict TypeScript
check before opening a pull request.

## Pi UI and Extension Rules

- Interactive popups use `ctx.ui.custom`; do not intercept terminal input globally.
  Respect the established `packages/btw` wrapping, scrolling, theme, and cleanup
  patterns. Keep passive widgets display-only.
- `package.json`: `"keywords": ["pi-package"]`, `"pi": { "skills": [...], "extensions": [...] }`; extensions packages declare `"peerDependencies": { "@earendil-works/pi-coding-agent": "*" }`.
- `files` must include everything that ships (`skills`/`extensions`/`procedures`/`references`/`scripts`).
- **Never** add `.claude-plugin`, `${CLAUDE_PLUGIN_ROOT}`, or Claude-only skill frontmatter (`allowed-tools`, `user-invocable`, `argument-hint`, `model`). Skill frontmatter: `name`, `description`, optional `disable-model-invocation`.

## Command menus vs skills (settled UX)

- `memory`/`btw` expose workflows as **pi menu commands** (`/memory`, `/btw`), not skills: `pi.registerCommand(...)` + `ctx.ui.select` + the full procedure embedded via `pi.sendUserMessage(..., { deliverAs: "followUp" })` with `{{PKG_DIR}}` substituted at send time. Keep this pattern; do not reintroduce per-workflow skills. (The former `git-agent` package follows the same pattern from `~/Developer/FradSer/git-agent/git-agent-pi-package`; the former `git`/`github` packages moved to pure skills in `~/Developer/FradSer/skills`.)
- Skill names are global — avoid collisions (the old `commit`/`commit-and-push` clash between `git` and `git-agent` was resolved by moving to menus; the git/github skills now live in `~/Developer/FradSer/skills`).
- Natural-language routing ("commit this", "create a PR") is preserved with small `before_agent_start` GUIDANCE blocks, not skills.

## TUI pattern — follow `@packages/btw` (canonical)

Interactive extension UI mirrors `packages/btw/src/overlay.ts`:

- **Primitive**: `ctx.ui.custom(..., { overlay: true })` for interactive popups — `setWidget` is display-only (no keys, no mouse, no esc). Popup shape: full-width, bottom-anchored right above the input box (`overlayOptions: { anchor: "bottom-center", width: "100%", margin: { bottom: 4 } }`).
- **Adaptive height**: `render()` returns content-sized lines; short answers shrink the panel, long bodies cap at ~40% of terminal rows (`maxAnswerBody`) and scroll with `↑/↓`, `pgup`/`pgdn`, `home`/`end`. **Mouse wheel is not available** in pi's fullscreen TUI (the wheel belongs to the chat viewport) — keyboard scrolling only.
- **Style language** (`BtwOverlayStyle`): `accent`/`muted`/`dim`/`border`/`success`/`error` callbacks mapped from `theme.fg` and passed into the component (don't depend on pi's internal Theme type). Layout: top + bottom border (`─`.repeat(width)), accent header line (e.g. `btw  <title>`), 2-space-padded body, dim footer hint line ("esc close · ↑↓ scroll · pgup/pgdn page · home/end jump"). Markdown bodies use the `Markdown` component with a theme built from these callbacks.
- **Loading**: `CancellableLoader` spinner with a model label; escape closes or cancels.
- Full-screen (non-popup) extension views use `ctx.ui.custom` WITHOUT `{ overlay: true }` and the same border/header/footer style language — see the `agent-teams` package's `/teammate` console.

## Extension gotchas (hard-won)

- **Never drive a widget with `ctx.ui.onTerminalInput`** — the listener runs before pi's keybindings and breaks the model selector, prompt history, and dialogs. Interactive UI = `ctx.ui.custom` (owns input) or `ctx.ui.select/confirm/input`. A `setWidget` is display-only.
- **Alignment with native rows**: pi's native loader row is ` ⠋ Working...` — one leading space before the spinner. Custom widget/spinner rows must match (e.g. ` ⠴ Dreaming... · <activity>`) so the spinner columns align — see `packages/memory/extensions/inject-memory.ts`.
- `ctx.ui.custom` `render(width)` must fit the terminal: word-wrap with `wrapTextWithAnsi`, truncate with `truncateToWidth`.
- pi negotiates the **Kitty keyboard protocol** (flags=7) with supporting terminals (Ghostty): Esc arrives as `\x1b[27u`, Shift+↑/↓ as `\x1b[1;2:1A`/`\x1b[1;2:1B` (event suffix). Match keys with CSI-u-aware regexes; filter releases with `isKeyRelease`.
- Shared worker state between extension and child processes goes through a **shared JSON file** written atomically (tmp + rename); merge worker writes back on a poll/exit and never let a worker's write un-read a message the user already read.

## Commits & Pull Requests

Use the Conventional Commit style established in history, such as
`feat:`, `fix(scope):`, `docs:`, `test(scope):`, `refactor:`, and
`chore(release):`. Keep commits focused. Add a Changeset for a published
package change. Pull requests should describe the affected packages, behavior
and verification commands, and any release or migration impact. Update both
root READMEs when the public package list or install commands change.

## Constraints

- Commits go through git-agent (`git-agent commit` with an intent built from the session) — never bare `git add`/`git commit`; scope with exact staging + `--no-stage`.

## Memory

- Project memory lives in two places that must stay identical for safe files: harness `~/.pi/agent/memory/<escaped-cwd>/` (canonical, private ok) and `.memory/` (public git-tracked, safe-only).
- `/memory` menu consolidates; search existing memories before writing a new one; one decision per file (frontmatter `name`/`description`/`type` + **Why** + **How to apply**).
