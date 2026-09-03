---
name: npm-package-release
description: Release and publish npm packages with Trusted Publishing (GitHub OIDC) in a monorepo, covering both first-release bootstrap (interactive publish + npm trust setup) and subsequent CI-owned releases via Changesets. Use whenever releasing a new package for the first time, diagnosing release or publication failures (EOTP, PUT 404, 409 Conflict, EPUBLISHCONFLICT, E401), handing off releases to CI, or triaging GitHub Actions release workflow runs.
---

# npm package release and publishing

npm OIDC Trusted Publishing cannot create the **first** version of a package
that does not exist yet, and a trust relationship cannot be created for a
package that does not exist. The first version therefore needs one deliberate,
human-in-the-loop publication; every later version is owned by CI.

Distinguish the two scenarios before acting:

- **Scenario A: First release (Bootstrap)** — The package has never been published
  to npm (registry returns 404). Follow the full bootstrap procedure (manual
  initial publish, then configure `npm trust`).
- **Scenario B: Subsequent releases (CI / Second+ release)** — The package already
  exists on npm (`latest` version exists, trust is configured). Releases belong
  entirely to GitHub Actions CI via Changesets. Do not treat subsequent releases,
  version bumps, or CI retries as a first-release bootstrap.

## Hard rules

- Never ask the user to paste an OTP code into chat, and never automate
  `npm login`, browser approval, or OTP entry. Interactive steps belong to the
  user's own terminal, where prompts and browsers are visible to them.
- Publish **before** configuring trust. `npm trust github` on an unpublished
  package fails with `404 Package not found` — that error means ordering, not
  a missing name.
- In pnpm workspaces always publish with `pnpm publish`. It rewrites
  `workspace:*` dependencies to real versions; plain `npm publish` would ship
  an unresolvable manifest.
- Do not run recursive root-level publishes (`pnpm -r publish`). Publish one
  package from its directory.

## Procedure

### 0. Preconditions

- The package name is on the repository's release allowlist (for pi-packages:
  `scripts/publish-release.mjs`), so CI can take over after handoff.
- Version/changeset coordination is decided: either a pending changeset will
  produce a version PR, or the manifest version is already the exact version
  intended for first publication. The registry-aware CI publisher skips
  versions equal to what is on npm, so publishing an exact version early is
  safe.

### 1. Check credentials before anything else

```bash
npm whoami
```

- Success: continue.
- `E401`: the stored token is dead. npm actively retires bypass-2FA tokens, so
  tokens die silently even days after login. Ask the user to run `npm login`
  themselves and confirm when done. Do not proceed on a dead token.

A dead token is also why a publish of a brand-new package can fail with
`PUT ... 404 Not Found`: the registry masks authorization failures for
nonexistent packages as 404 instead of 401/403. When you see 404 on PUT,
check `npm whoami` first before suspecting the package name.

### 2. Check registry state and route scenario

```bash
curl -s https://registry.npmjs.org/<package-name>
```

- **404 / no versions**: Scenario A (First release) — proceed with Steps 3, 4, 5.
- **Package exists with versions**: Scenario B (Subsequent release) — **STOP**.
  - Do **NOT** ask the user to manually publish from their terminal.
  - Do **NOT** run `npm trust` again (trust relationship is already active).
  - Normal flow: create a Changeset (`pnpm changeset`), commit, push to `main`, and merge the Changesets Version PR. CI publishes automatically via OIDC.
  - If CI fails during a subsequent release: inspect CI logs first before assuming manual intervention is needed. For example, if the version already succeeded in publishing in the `changesets/action` step, a subsequent retry step encountering `409 Conflict` simply means the package is already published on the registry (an eventual consistency or idempotency artifact), not an authorization or bootstrap failure.

---
## Scenario A: First release bootstrap procedure

### 3. User publishes the first version (interactive)

The user runs, from the package directory:

```bash
pnpm publish --access public
```

pnpm prompts `Enter OTP:` inline; they type their authenticator code. If the
branch is not the configured publish branch, pnpm asks to continue — answering
yes is expected on wip/release branches.

If the user must publish the exact version a changesets version PR produces,
check out that PR's branch and publish from there, then merge it; the CI
publisher compares local vs registry versions and skips what already exists.

### 4. Establish the trust relationship

Still the user's terminal:

```bash
npm trust github <package-name> --file <release-workflow>.yml \
  --repo <owner>/<repo> --allow-publish -y
```

For pi-packages: `--file release.yml --repo FradSer/pi-packages`. This prints
an auth URL and waits ("Press ENTER to open in the browser..."); the user
approves in their browser. Requires npm >= 11.5.

If this fails with `Package not found`, step 3 has not actually completed —
verify the registry before retrying.

### 5. Hand off to CI

Merge the feature/version PR. The release workflow's registry-aware publisher
sees the published version and skips it; all subsequent versions publish via
GitHub Actions OIDC with provenance — no local token involved ever again.

### 6. Verify

```bash
curl -s https://registry.npmjs.org/<package-name> | jq '."dist-tags".latest'
```

Registry edge caches can lag briefly after publish.

## Failure quick table

| Symptom | Real cause | Fix |
| --- | --- | --- |
| `PUT ... 404 Not Found` on a new package | Dead token masked by the registry | `npm whoami`; if E401, user re-runs `npm login` |
| `EOTP` exiting immediately under automation | Non-TTY clients cannot complete web-auth | Stop automating; user runs the publish interactively |
| Trust setup: `Package not found` | Package not published yet | Complete step 3 first, then re-run trust |
| `EPUBLISHCONFLICT` / 409 Conflict | Version already published on npm | In CI retry: version succeeded in previous step; verify with `npm view <pkg> versions`. Do not re-bootstrap as first-release. In local dev: advance package version. |
| Token dies again days later | npm retiring bypass-2FA tokens | Re-login; prefer granular tokens with read-write packages |

## Related project memory

- `project_pi_package_npm_publishing` — allowlist + version-PR coordination.
- `github-ci-npm-publishing` (pi-git-agent) — CI-only releases, `npm trust` CLI.
- `npm-trusted-publishing` (apple-events) — trust requires existing package.
