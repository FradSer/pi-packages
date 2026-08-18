---
name: pi-package-npm-naming
description: npm package naming ladder for Pi packages: use an available unscoped name, otherwise the established @fradser name, never invented -fradser suffixes
type: feedback
---

When naming a Pi package, prefer the concise unscoped name that matches the package when it is available. If that exact unscoped name is occupied, keep or choose the established `@fradser/<name>` package name. Do not invent names with suffixes such as `-fradser` merely to avoid a scope.

**Why:**

The package name is a public API and should be recognizable, stable, and unambiguous. Registry availability must be checked before changing a name: several useful unscoped names were already owned by unrelated packages, while `pi-mattpocock` was available. Suffixing every package with the publisher identity produces names that are not acceptable for this project and makes the naming scheme inconsistent.

**How to apply:**

1. Query the anonymous npm registry for the exact unscoped name (`curl -s https://registry.npmjs.org/<name>`); a packument means the name is occupied.
2. Use the unscoped name only when it is available and semantically appropriate.
3. Otherwise use the existing `@fradser/<name>` package name; do not switch to `<name>-fradser`.
4. Update the manifest, Changeset package key, release allowlist, tests, and installation docs together before publishing.
5. Treat a published package name as permanent; do not rename it after release without an explicit migration decision.

**Related:** [[pi-package-npm-publishing]]
