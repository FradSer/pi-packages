---
"pi-matt-pocock": patch
---

Sync the `mattpocock/skills` selection to `v1.3.2` and the three commits after it (checked tree `4ae2317`).

- Classify the new `software-factory` in-progress skill as excluded, and refresh the `implement-spec` and `chief-of-staff` exclusion reasons against the checked tree.
- Adopt the upstream fresh-context-window guidance for delegated work in `code-review`, `research`, `improve-codebase-architecture`, `wayfinder`, `grilling`, and `DESIGN-IT-TWICE`, keeping the local teammate-or-current-context rule.
- Bring the setup procedure's legacy `CONTEXT.md` migration and reachable-repo requirement, plus the GitHub and GitLab tracker conventions, up to the checked tree.
- Run the package on bun only: `bun pm pack` for the packed-package fixture, `bun x tsc` for the live TypeScript fixtures, and bun commands in the contributor docs and reproduction notes.
- Normalize the two recorded model transcripts to bun workspace wording. All hash, status and count fields stay unchanged; these remain historical evidence, not a new run.

Verified with the sync checker against a real upstream checkout, the package test suite, typecheck and packing, with no package-manager shim. The repo-wide bun-only test-tooling guard lives in `tests/test_bun_only_test_tooling.py`.
