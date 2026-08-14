# Pi Packages — Agent Guidelines

Monorepo of native **Pi** packages (`pi-packages/`). Each package under `packages/` is self-contained, installable via `pi install npm:@fradser/<name>` or a local path, and follows native Pi conventions — no Claude Code plugin artifacts.

## Layout & Tooling

- `packages/<name>/` — one pi package each (`btw`, `code-context`, `lark`, `mattpocock`, `memory`, `monitor`, `agent-teams`, `utils`). (The former `git-agent` package now lives at `~/Developer/FradSer/git-agent/git-agent-pi-package`; the former `git`/`github` packages became pure skills in `~/Developer/FradSer/skills`.)
- pnpm workspace at the root (`pnpm-workspace.yaml`); per-package deps live in `packages/<name>/node_modules`.
- **Tests**: `python3 -m pytest packages/<name>/tests/`. BDD: write/update `.feature` files under `packages/<name>/features/` before behavior changes.
- **Typecheck**: `npx tsc --noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution bundler --types "" packages/<name>/src/*.ts` (or `extensions/*.ts`).
- Formatting: Biome, 2-space. Never edit `package.json`/`pyproject.toml` by hand — use `pnpm add` / `uv add`.

## Pi package manifest

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

## Constraints

- Commits go through git-agent (`git-agent commit` with an intent built from the session) — never bare `git add`/`git commit`; scope with exact staging + `--no-stage`.

## Memory

- Project memory lives in two places that must stay identical for safe files: harness `~/.pi/agent/memory/<escaped-cwd>/` (canonical, private ok) and `.memory/` (public git-tracked, safe-only).
- `/memory` menu consolidates; search existing memories before writing a new one; one decision per file (frontmatter `name`/`description`/`type` + **Why** + **How to apply**).
