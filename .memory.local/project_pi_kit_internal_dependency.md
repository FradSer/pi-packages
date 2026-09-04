---
name: pi-kit-internal-dependency
description: pi-kit is the shared internal runtime package of the pi-packages workspace (packages/kit); consumers use dependencies.workspace and pi-kit has no pi manifest
type: project
---

## Why

The pi-packages monorepo extracts shared runtime logic into `@fradser/pi-kit` (`packages/kit/`). Cross-package imports are allowed for this package; avoiding all internal dependencies is not a project constraint. The first extraction batch removed duplicated code across agent-teams, btw, memory, recap, vision, and utils.

Pi package-owned TUI output must share this runtime rather than silently falling back to package-local transcript, notification, status, spinner, widget, or panel formatting. Keeping each package limited to domain state and interaction behavior prevents visual and lifecycle semantics from drifting.

## How to apply

- Consumer packages declare `"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
- `packages/kit/package.json` has no `pi` key, no `pi-package` keyword, and zero dependencies — its `src/` must not import pi core (`@earendil-works/*`) or consumer packages (one-way graph, enforced by `packages/kit/tests/test_pi_kit.py`).
- Shared TUI surface:
  - `PI_SPINNER_FRAMES` / `PI_SPINNER_INTERVAL_MS` match the native loader cadence.
  - `createPiThemeStyle(theme)` is the standard accent/muted/dim/border/success/error/fg style language.
  - `renderPiPanel` owns bordered overlay and full-screen console geometry; `renderPiWidgetRow` owns passive widget alignment.
  - `renderToolLifecycle`, `createToolLifecycleMessageRenderer`, and `createToolLifecycleResultRenderer` own expandable tool/custom-message lifecycle bands. Use the static renderer variants when model-facing procedure/output text must not enter the user-facing expanded row. Lifecycle `summary` lines remain visible both collapsed and expanded.
  - `notifyPi` sanitizes native notifications; `setPiStatus` / `clearPiStatus` sanitize package-owned transient status; `startPiWorkingIndicator` / `clearPiWorkingIndicator` start the shared spinner or restore Pi's native indicator.
- A native Pi primitive is still appropriate at the host edge: empty `Text` call slots, host error components, Markdown rendering, selection/input dialogs, and rich expanded teammate report composition. Do not duplicate `@earendil-works/pi-tui` utilities already deliberately excluded from pi-kit (`wrapTextWithAnsi`, `truncateToWidth`, `visibleWidth`, `Key`, `matchesKey`, `isKeyRelease`).
- `renderToolLifecycle` caps expanded details at 50 lines by default; use explicit `detailLimit: "all"` only for user-requested readbacks where losing detail would be incorrect.
- `scripts/publish-release.mjs` lists `@fradser/pi-kit` first so it publishes before consumers.
- Validate workspace development, packed installation, `pnpm check:install`, and one live Pi smoke surface for published-package changes.

## Related

[[project_pi_package_conventions]] [[project_pi_package_npm_publishing]] [[project_monitor_display_pattern]] [[project_teammate_autonomous_and_tui]]
