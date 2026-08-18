---
name: pi-package-npm-publishing
description: Changesets and GitHub Actions OIDC release flow, including registry-aware retries and first-publication coordination
type: project
---

Pi packages publish through the Changesets GitHub Actions workflow in `.github/workflows/release.yml`. A pending `.changeset/*.md` produces a version PR; merging that PR runs the release command. Normal releases use npm Trusted Publishing through GitHub OIDC, with no long-lived `NPM_TOKEN`.

**Why:**

Version PRs keep package versions and changelogs reviewable, while OIDC avoids storing a publish token. Recursive publishing is unsafe in a workspace because unpublished packages also carry versions and a rerun can try to publish versions that are already in npm. The release flow therefore has an explicit package allowlist and must compare local versions with the registry before publishing.

**How to apply:**

- Keep `contents: write`, `pull-requests: write`, and `id-token: write` in the release job.
- Maintain the explicit package allowlist in `scripts/publish-release.mjs`; the workflow invokes that script rather than an unfiltered recursive publish.
- The publish script should compare each local package version with `npm view` and publish only versions that are absent or different. This makes partial runs and retries safe and prevents duplicate-version failures.
- For a new package, add its manifest name to the allowlist and create a Changeset before pushing to `main`. Merge the generated version PR only after the first-release plan is ready.
- OIDC cannot create the first version of a package that does not exist in npm. Publish the exact version from the version PR branch manually with npm and browser/2FA authentication, then run `npm trust github <package> --file release.yml --repo FradSer/pi-packages --allow-publish --yes`.
- Coordinate the manual first publication with the version PR: if CI uses a plain `pnpm publish` and sees the same version already published, it fails with a 403. Use the registry-aware publisher (current flow) or otherwise advance the version before CI runs.
- Verify the package on `registry.npmjs.com` or with `npm view` after publishing; npm registry edge caches can lag briefly.
- Do not run a root-level recursive local publish as the normal release path. Use the GitHub Actions workflow.

**Related:** [[pi-package-npm-naming]]
