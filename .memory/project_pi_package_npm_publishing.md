---
name: pi-package-npm-publishing
description: Publish pi packages to npm via GitHub Actions — OIDC trusted publishing (no tokens), main-branch version-diff triggers, publish only bumped packages (idempotent)
type: project
---

Pi packages publish to npm through a GitHub Actions workflow in each repo, triggered on push to `main` (plus manual `workflow_dispatch`). The workflow compares each package's local `package.json` version against the latest npm registry version (`npm view <name> version`) and publishes **only** the packages with a version bump. Authentication is **OIDC trusted publishing** — no NPM_TOKEN secret, no long-lived tokens.

**Why:**
- Tag-driven publishing (e.g. `<name>@<version>` tags) is not best practice for a monorepo: the version already lives in `package.json`, so tags duplicate the source of truth (the original workflow spent half its logic verifying tag version == manifest version). The user pushed back ("不是最佳实践吧？应该是 main 中版本有修改发布"), and the tag-triggered workflow was replaced with the version-diff approach.
- The NPM_TOKEN secret approach was then replaced by OIDC trusted publishing (GA since 2025-07): no token to generate, rotate, or store per repo. Works for **personal accounts**, not just organizations ("Organization or user (required): Your GitHub username or organization name"). Requires npm account 2FA enabled, npm ≥ 11.15 (`npm trust` command), and `id-token: write` in the workflow.
- Side discovery: `pi-packages` was a local git repo with **no remote and no GitHub repo at all** — the workflow had nothing to run on; `FradSer/pi-packages` was created (PUBLIC) and pushed.

**How to apply:**
1. Single-package repo (`GitAgentHQ/pi-git-agent`): `.github/workflows/publish.yml` — on main push / manual dispatch, `npm view "$PKG_NAME" version` vs local; `publish=true` only on mismatch; then `npm publish --provenance --access public`.
2. Monorepo (`FradSer/pi-packages`): same trigger; loop `find packages -name package.json` (skip node_modules), `npm view <name> version` each (404/unpublished → treat as `0.0.0`), collect names with `local != registry` into `GITHUB_OUTPUT changed`, then `pnpm publish --filter <pkg> --provenance --access public --no-git-checks` per changed package.
3. **OIDC workflow shape**: `permissions: { contents: read, id-token: write }`; **do NOT set `registry-url` on actions/setup-node and do NOT pass NODE_AUTH_TOKEN** — setup-node's registry-url interferes with the OIDC trigger (npm docs issue #1960). Publish commands carry `--provenance`.
4. **npm-side one-time setup per package** (run locally, needs 2FA): `npm trust "OWNER/REPO/.github/workflows/publish.yml" --user <npm-username> --package <pkg-name>` (e.g. `npm trust "FradSer/pi-packages/.github/workflows/publish.yml" --user fradser --package @fradser/pi-memory`; `npm trust "GitAgentHQ/pi-git-agent/.github/workflows/publish.yml" --user fradser --package pi-git-agent`).
5. Idempotent by design: an already-published version is never re-published; untouched packages are skipped. No tags required.
6. Release flow: bump version in `package.json` → merge to `main` → CI detects the diff and publishes.
7. `publishConfig: { "access": "public" }` is set in both manifests (required for unscoped packages; pi packages are always public).
8. **Current scope**: only `pi-git-agent` and `@fradser/pi-memory` are published by these workflows (user's explicit choice). The other `@fradser/*` packages (btw, teammate, lark, utils, code-context) have never been published to npm — verified 404 on registry.

**Related:** [[pi-package-npm-naming]]
