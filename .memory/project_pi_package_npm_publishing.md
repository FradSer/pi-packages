---
name: pi-package-npm-publishing
description: Publish pi packages to npm — Changesets-driven, OIDC trusted publishing, release.yml whitelist; first version of a new package must be published manually + npm trust once; daily rhythm = changeset per real change
type: project
---

Pi packages publish to npm through a Changesets-driven GitHub Actions workflow in each repo. Developer writes `.changeset/*.md` via `pnpm change` → push to `main` → `changesets/action` opens/updates a "Version Packages" PR (bumps versions + CHANGELOGs) → merging that PR publishes. Authentication is **OIDC trusted publishing** — no NPM_TOKEN, no long-lived tokens. Only packages with a pending changeset are versioned and published.

**Why (evolution):**
1. Tag-driven publishing → rejected: tags duplicate the version already in `package.json` (user: "不是最佳实践吧？应该是 main 中版本有修改发布").
2. Registry-version-diff workflow (`npm view <name> version` vs local, publish mismatches) → replaced: it sweeps EVERY never-published workspace package — code-context, lark, mattpocock, teammate all carry version numbers but were never published, so a main push tried to publish all of them and aborted on their 404s.
3. pnpm-native `pnpm version -r` (pnpm ≥ 11.13) → replaced by standard `@changesets/cli`: the native implementation has a bug — it READS change intents but does NOT apply the version bump (verified: `@fradser/pi-btw` stayed `0.1.0 → 0.1.0` with both patch and minor intents; `@changesets/cli` applied it correctly).
4. NPM_TOKEN secret → replaced by OIDC trusted publishing (GA 2025-07): no token to generate/rotate/store. Works for **personal accounts** ("Organization or user (required)"). Requires npm account 2FA, npm ≥ 11.15 (`npm trust`), `id-token: write` in the workflow.
5. Side discovery: `pi-packages` was a local git repo with **no remote and no GitHub repo** — `FradSer/pi-packages` was created (PUBLIC) and pushed.

**The workflow (pi-packages `.github/workflows/release.yml`):**
- Trigger: push to `main` + `workflow_dispatch`. `permissions: { contents: write, pull-requests: write, id-token: write }` (contents+pull-requests for changesets/action to commit + open the PR; id-token for OIDC).
- `changesets/action@v1` with `version: pnpm changeset version`, `publish: pnpm publish -r --provenance --access public --filter <whitelist>`.
- **Whitelist is mandatory**: `pnpm publish -r` AND `changeset publish` both sweep every never-published workspace package ("No changesets found. Attempting to publish any unpublished packages"). Only the `--filter` list is ever published. **Current whitelist: `@fradser/pi-memory --filter @fradser/pi-btw --filter @fradser/pi-monitor --filter @fradser/pi-utils --filter @fradser/pi-vision --filter @fradser/pi-recap`.**
- GitHub repo needs `Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests` (API: `PUT /repos/{owner}/{repo}/actions/permissions/workflow` with `can_approve_pull_request_reviews: true`) — otherwise changesets/action fails with "GitHub Actions is not permitted to create or approve pull requests".
- pnpm 11 details: `packageManager` pinned in root package.json (`corepack use pnpm@latest`); `allowBuilds`/`onlyBuiltDependencies` live in `pnpm-workspace.yaml` (not package.json); do NOT pass `version:` to `pnpm/action-setup` when `packageManager` is set (double-specification error); `--allow-build` install flag does NOT exist in pnpm 11.

**First release of a NEW package (chicken-and-egg, npm hard limit):**
OIDC trusted publishing CANNOT publish a package's first version (npm/cli #8544), and `npm trust` 404s for a package that doesn't exist yet. Sequence:
1. Rename to `@fradser/pi-<name>` first (naming convention), add to whitelist, add a changeset, let the version PR merge so CI attempts publish (it will fail with E404 — expected).
2. Manually publish the first version: `cd packages/<name> && npm publish --access public` (browser OTP auth pops). **Agent-run gotcha (npm 12): `otplease` requires a TTY — run without one, publish/trust fail in ~2s with EOTP and the auth URL is redacted (`***`). The web flow also prints "Press ENTER to open in the browser..." and waits. Working recipe: `cd packages/<name> && (sleep 10; printf '\n') | script -q /dev/null npm publish --access public` — the pty satisfies the TTY check and the injected ENTER pops the browser; the human completes OTP in the browser and npm finishes.**
3. Establish OIDC trust: `cd ~/Developer/FradSer/pi-packages && npm trust github @fradser/pi-<name> --file release.yml --repo FradSer/pi-packages --allow-publish --yes` (browser OTP again).
4. Re-trigger `gh workflow run release.yml --repo FradSer/pi-packages` → CI publishes the bumped version via OIDC with provenance. **Verification quirk: right after a first publish, `registry.npmjs.org` packument may 404 for minutes (edge-cache lag) while `registry.npmjs.com` shows it instantly and the tarball URL serves 200 — verify with `curl https://registry.npmjs.com/@fradser/pi-<name>` or `npm install` before assuming failure.**

**Daily maintenance rhythm (user's explicit guidance):**
- Docs/internal-only changes, no release needed → **do NOT add a changeset**; push to main and CI does nothing.
- Bug fix → `pnpm change` with patch → `0.x.y+1`.
- New feature → `pnpm change` with minor → `0.x+1.0`.
- Idempotent: an already-published version is never re-published; re-triggering the workflow 100 times publishes nothing. Version bumps happen ONLY in the "Version Packages" PR, merged deliberately.

**Published packages (verified 2026-08-15):** `@fradser/pi-memory` (0.2.1), `@fradser/pi-btw` (0.1.1), `@fradser/pi-monitor` (1.0.0), `@fradser/pi-utils` (0.3.2), `@fradser/pi-recap` (0.1.1), `@fradser/pi-vision` (0.2.0). All six whitelisted packages are now published and OIDC-trusted; the release workflow runs green (idempotent — an already-published version is never re-published). Note: the second `npm trust` (vision) completed in ~2s WITHOUT a browser prompt (npm reused the existing web-login session); if it prompts, the same `(sleep 10; printf '\n') | script -q /dev/null` recipe applies. Never published and still in the monorepo: code-context, mattpocock, agent-teams (`@fradser/pi-agent-teams`); the former lark and teammate packages were removed from the repo. Single-package repo `GitAgentHQ/pi-git-agent` (unscoped `pi-git-agent`) has its own simpler publish workflow.

**Related:** [[pi-package-npm-naming]]
