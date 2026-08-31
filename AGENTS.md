# Repository Guidelines

This is a pnpm monorepo of native Pi packages. Manifest-backed workspace
packages live under `packages/*`, with scoped contributor rules in the nearest
`AGENTS.md` (including `packages/context/AGENTS.md`).

## Project Structure & Module Organization

- Workspace packages currently include `agent-teams`, `btw`, `context`,
  `keyboard`, `monitor`, `pi-continual-learning`, `pi-kit`, `plan-mode`,
  `recap`, `matt-pocock`, `skill-router`, `utils`, and `vision`. The
  skill-router package routes externally hosted skill collections and ships no
  collection content; matt-pocock provides the persisted workflow harness.
- Extension code lives in `src/`, `extensions/`, or a package-root `index.ts`;
  skills, procedures, references, and bundled agents use their named folders.
- BDD scenarios are in each package's `features/`; executable tests are in
  `tests/`. Release metadata lives in `.changeset/` and `.github/workflows/`.
- `pi-kit` is the shared runtime and intentionally has no Pi manifest. The
  release script publishes an explicit allowlist in dependency order; check
  `scripts/publish-release.mjs` before changing package release behavior.

## Build, Test, and Development Commands

```bash
pnpm install
pnpm test
npx tsc --noEmit -p tsconfig.extensions.json
```

`pnpm test` runs pytest across `packages/`; run one package with
`python3 -m pytest packages/<name>/tests/ -q`. Some packages also document a
strict per-file TypeScript command in their README. There is no separate build
step: Pi loads the TypeScript extensions and packaged resources directly.
Use `pnpm --dir packages/<name> pack --dry-run` to inspect package contents;
`pnpm pack --dry-run` at the root packs the private workspace root instead.
For the SDK example, run `pnpm example:sdk`.

## Coding Style & Naming Conventions

Use ESM TypeScript targeting Node 20 or newer, follow surrounding indentation,
and keep package, command, and tool names explicit and stable. Runtime package
manifests use an explicit `pi.extensions` entry and complete `files` entries;
Pi core imports are peer dependencies, while reusable `@fradser/pi-kit` is a
workspace dependency. `pi-kit` has no `pi` field or runtime dependencies. Do not
add Claude Code plugin artifacts or Claude-only skill frontmatter. Use pnpm
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
under the package's `tests/` directory. Python tests use pytest and modules
follow `test_*.py`; runtime TypeScript harnesses belong under `tests/`, not the
repository root. Run affected package tests, `pnpm test`, and the strict
TypeScript check before opening a pull request. Include package dry-run output
when changing manifests or published files.

Every published-package update requires a Changeset. Do not hand-edit package
versions for ordinary changes: GitHub Actions runs the Changesets workflow,
opens the version PR, and publishes after that PR is merged.

Package work is done only when the package is installed in the live agent
config and exercised once in a real Pi run: `pnpm check:install` must pass
(workspace pi packages vs `~/.pi/agent/settings.json`), plus one live
`pi --print` smoke run touching the new surface. Package tests are necessary
but never sufficient — an uninstalled package fails silently (no error, only
absence). Renaming or moving a package directory must update `settings.json`
in the same task; cleaning a dead entry without installing the successor is
data loss.

## Pi UI and Extension Rules

- Interactive popups use `ctx.ui.custom`; do not intercept terminal input globally.
  Respect the established `packages/btw` wrapping, scrolling, theme, and cleanup
  patterns. Keep passive widgets display-only.
- Published extension manifests declare `"pi": { "extensions": ["./index.ts"] }`
  and declare imported Pi core packages as peer dependencies. Packages that
  ship skills or other resources list them explicitly in `files`.
- `files` must include everything that ships (`skills`/`extensions`/`procedures`/`references`/`scripts`).
- **Progressive tool disclosure:** Register every custom tool so it can be
  activated at runtime, but keep only capabilities useful in ordinary sessions
  active initially. A tool whose purpose depends on an explicit workflow,
  mode, or durable state must remain inactive until that transition succeeds;
  enable it with `pi.setActiveTools()` at the transition, preserve unrelated
  active tools, and remove it again on every exit, cancellation, or invalid
  state-restoration path. Scope its description, `promptSnippet`, and
  `promptGuidelines` to the prerequisite state. Prefer this availability
  boundary over a tool-call guardrail: a guardrail remains defense in depth,
  not routine routing after the model has already selected an irrelevant tool.
  Cover initial inactive, activation, restoration, and exit behavior in BDD
  and an executable active-tool-list test, then verify it in a live Pi run.
- **Never** add `.claude-plugin`, `${CLAUDE_PLUGIN_ROOT}`, or Claude-only skill frontmatter (`allowed-tools`, `user-invocable`, `argument-hint`, `model`). Skill frontmatter: `name`, `description`, optional `disable-model-invocation`.

## Tool Result Text and Coordination-State Semantics

Treat tool output as a contract for both the model and the transcript, not as an
incidental sentence. Keep the domain model abstract and preserve the distinction
between:

- a **coordination container**, which scopes shared state for one execution
  context;
- a **work item**, which is one independently addressable unit inside that
  container;
- an **actor**, which may be assigned ownership or receive a delivery;
- an **intent**, which requests a state transition but may still be awaiting
  application, validation, or verification.

Every state-changing operation must make its transition semantics explicit:
creation adds a work item without implying execution; inspection returns a
snapshot without mutating state; acquisition transfers ownership; submission
records a proposed outcome; application or verification is the point at which
the durable state may become final. Never report a later transition as complete
when the operation only queued an intent or wrote a marker.

Structure successful results into stable semantic groups chosen for the domain:
context, summary, items, ownership, routing, validation, next action, and
participants. Use short section labels consistently, mention the coordination
context once, and keep each item line limited to identity, lifecycle state,
subject, ownership, and blocking relationships. Put diagnostics in a separate
warning or note group. Do not duplicate the same state in prose, summaries,
participant lists, and detail paragraphs.

The result should answer four questions in order:

1. What state or transition was addressed?
2. What actually happened synchronously?
3. What remains pending, blocked, queued, or subject to verification?
4. Who or what performs the next transition?

Keep successful result text compact, factual, and actionable. Avoid ambiguous
claims such as a generic "state updated" when only an intent was recorded or a
delivery was queued. State the observed transition, the unobserved transition,
and the next actor/action without embedding domain-specific assumptions in a
shared guideline.

For TUI tools, use the shared `@fradser/pi-kit` lifecycle abstraction: one
compact `started` or `event` row in the transcript, with grouped details behind
the standard expansion affordance. The collapsed row identifies only the
operation and subject; expanded details carry the semantic groups above. Keep
internal identifiers, raw diagnostics, and large participant lists out of the
collapsed row unless required to distinguish the operation.

## Command menus vs skills (settled UX)

- Workflow surfaces are native Pi commands, not per-workflow skills. The
  `pi-continual-learning` `/memory` menu loads its selected procedure as a
  follow-up; `/btw` is a separate interactive read-only overlay. Keep command
  registration and procedure loading aligned with each package's guide.
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
- **Alignment with native rows**: pi's native loader row is ` ⠋ Working...` — one leading space before the spinner. Custom widget/spinner rows must match (e.g. ` ⠴ Dreaming... · <activity>`) so the spinner columns align — see `packages/pi-continual-learning/extensions/inject-memory.ts`.
- `ctx.ui.custom` `render(width)` must fit the terminal: word-wrap with `wrapTextWithAnsi`, truncate with `truncateToWidth`.
- pi negotiates the **Kitty keyboard protocol** (flags=7) with supporting terminals (Ghostty): Esc arrives as `\x1b[27u`, Shift+↑/↓ as `\x1b[1;2:1A`/`\x1b[1;2:1B` (event suffix). Match keys with CSI-u-aware regexes; filter releases with `isKeyRelease`.
- Shared worker state between extension and child processes goes through a **shared JSON file** written atomically (tmp + rename); merge worker writes back on a poll/exit and never let a worker's write un-read a message the user already read.

## Commits & Pull Requests

Use the Conventional Commit style established in history: package-scoped
forms such as `fix(mon):`, `refactor(teams):`, and `feat(utils):`, plus
`feat(packages):`, `docs(packages):`, and `chore(release):`. Keep commits
focused. Add a Changeset for every published package change; keep
`scripts/publish-release.mjs` and package metadata aligned when release scope
changes. There is no committed PR template; describe affected packages,
behavior, verification commands, release impact, and README changes in the PR.
Update both root READMEs when the public package list or install commands change.

## Constraints

- Commits go through git-agent (`git-agent commit` with an intent built from the session) — never bare `git add`/`git commit`; scope with exact staging + `--no-stage`.

## Memory

- Project memory lives in two places that must stay identical for safe files: harness `~/.pi/agent/memory/<escaped-cwd>/` (canonical, private ok) and `.memory/` (public git-tracked, safe-only).
- `/memory` menu consolidates; search existing memories before writing a new one; one decision per file (frontmatter `name`/`description`/`type` + **Why** + **How to apply**).
