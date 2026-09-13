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
Focus: `python3 -m pytest packages/<name>/tests/ -q`.
Pack: `pnpm --dir packages/<name> pack --dry-run`.
SDK example: `pnpm example:sdk`. Pi loads TypeScript without a build step.

## Coding Style & Naming Conventions

Use strict ESM TypeScript (ES2022; Node ≥20), kebab-case modules, snake_case
tools. No formatter/linter is configured; match local style. Edit dependencies
through pnpm. Extensions declare
`"pi": { "extensions": ["./index.ts"] }`; Pi-core/TypeBox imports are peers.
For resource authoring, consult @.memory/project_pi_package_conventions.md.

## Shared Runtime: pi-kit

Prefer internal `@fradser/pi-kit` for shared helpers/infrastructure:
`"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
If absent, record the gap; invent no replacement or unverified registry dependency.
For shared-runtime changes, consult
@.memory/project_pi_kit_internal_dependency.md.

## Testing Guidelines

Start behavior changes with Given/When/Then `.feature` scenarios, then RED,
GREEN, refactor. Keep `test_*.py` and Node/tsx harnesses in `tests/`; run
both suites and tsc. Runtime changes require `pnpm check:install` and
live `pi --print` verification; test TUI interactively. Package moves must
update installed paths in `~/.pi/agent/settings.json`.

## Extension Architecture

- Activate state-dependent tools with `pi.setActiveTools()` only after valid
  transitions; remove on exit/invalid restore. Results identify state,
  synchronous outcome, pending intent, and next actor.
- Use pi-kit lifecycle renderers, `renderShell: "self"`, and empty `renderCall`.
  Prefer direct APIs, bounded/sanitized output, abort propagation, and explicit
  headless/missing-auth handling. Shared worker JSON uses atomic tmp+rename.
- UI reference: @packages/btw/src/overlay.ts. `ctx.ui.custom` owns input;
  widgets stay passive, width-bounded, spinner-aligned. Never intercept global
  terminal input. For raw keys, consult
  @.memory/reference_pi_kitty_csi_u_keys.md.
- Workflow menus are commands; routing uses `before_agent_start`. For user
  interaction/gates, consult @.memory/feedback_no_custom_interaction_tools.md.
- Flow/procedure starts are abstract lifecycle lines, never full-text dumps:
  send the procedure via `pi.sendMessage({ customType: "<pkg>-procedure",
  content, display: true, details }, { deliverAs: "followUp", triggerTurn:
  true })` and render it with `pi.registerMessageRenderer` as one
  `[<pkg>] started · <subject>` row (bold `customMessageLabel` prefix,
  `safeDisplayText` subject). Tool starts render the same shape through
  pi-kit lifecycle renderers in `renderResult`. Full content stays in LLM
  context; the transcript shows only the line. Reference:
  @packages/impeccable/src/index.ts, @packages/matt-pocock/src/index.ts,
  @.memory/project_monitor_display_pattern.md.

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
