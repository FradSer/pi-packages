---
name: pi-kit-internal-dependency
description: pi-kit is an internal runtime dependency of the pi-packages workspace; consumer packages use dependencies.workspace and pi-kit has no pi manifest
type: project
---

## Why

The pi-packages monorepo intentionally extracts shared runtime logic into `@fradser/pi-kit`. Cross-package imports are allowed for this package; avoiding all internal dependencies is not a project constraint.

## How to apply

- Consumer packages declare `"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
- `packages/pi-kit/package.json` has no `pi` key and has zero runtime dependencies beyond Node built-ins.
- Keep the dependency graph one-way: `pi-kit` must not import any consumer package.
- Add `@fradser/pi-kit` to the release workflow publish allowlist and release it before consumers.
- Validate both workspace development (`pnpm install`) and packed end-user installation; the latter verifies that `workspace:*` is rewritten to a real version in the tarball.
