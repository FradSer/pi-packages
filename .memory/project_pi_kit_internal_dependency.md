---
name: pi-kit-internal-dependency
description: pi-kit is the shared internal runtime package of the pi-packages workspace (packages/pi-kit); consumers use dependencies.workspace and pi-kit has no pi manifest
type: project
---

## Why

The pi-packages monorepo extracts shared runtime logic into `@fradser/pi-kit` (`packages/pi-kit/`, landed 2026-08-18). Cross-package imports are allowed for this package; avoiding all internal dependencies is not a project constraint. The first extraction batch removed duplicated code across agent-teams, btw, memory, recap, vision, and utils.

## How to apply

- Consumer packages declare `"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
- `packages/pi-kit/package.json` has no `pi` key, no `pi-package` keyword, and zero dependencies — its `src/` must not import pi core (`@earendil-works/*`) or consumer packages (one-way graph, enforced by `packages/pi-kit/tests/test_pi_kit.py`).
- Current surface: `PI_SPINNER_FRAMES` / `PI_SPINNER_INTERVAL_MS` (native loader cadence; memory/recap still use their own 80ms widget intervals), `createPiThemeStyle(theme)` (the btw accent/muted/dim/border/success/error/fg style language; `BtwOverlayStyle` aliases `PiThemeStyle`), `extractTextContent(content, separator)`.
- `buildMarkdownThemeCallbacks(style)` renders Markdown `---` as the literal sentinel `__OVERLAY_SEPARATOR__` — every overlay that displays its output must map lines containing that sentinel to a styled `─` rule before display, matching on `.includes()` then comparing the normalized line (pi-tui may emit it bare; future theme changes could wrap it in ANSI). Consumers: btw and plan-mode overlays use `.includes()` mapping; recap's widget compares exact equality. The 2026-08 btw bug "second question shows `_OVERLAY_SEPARATOR`" was exactly this contract violated: pi-kit renamed the sentinel but btw still filtered only its old private name.
- Deliberately NOT in pi-kit: `wrapTextWithAnsi`/`truncateToWidth`/`visibleWidth`/`Key`/`matchesKey`/`isKeyRelease` (import from `@earendil-works/pi-tui` directly — monitor's hand-rolled escape check was replaced by `matchesKey(data, Key.escape)`); scroll-offset math and border/footer primitives wait for a third usage point.
- `scripts/publish-release.mjs` lists `@fradser/pi-kit` first so it publishes before consumers.
- Validate both workspace development (`pnpm install`) and packed end-user installation; the latter verifies that `workspace:*` is rewritten to a real version in the tarball.

## Related

[[pi-package-conventions]] [[pi-package-npm-publishing]]
