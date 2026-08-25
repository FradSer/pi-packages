# Upstream: coda0HQ/open-artifacts

The Open Artifacts publishing surface in this package is vendored from
[coda0HQ/open-artifacts](https://github.com/coda0HQ/open-artifacts)
(`skills/using-open-artifacts/`), MIT licensed.

- Vendored from upstream commit `2720b65`
  ("Merge pull request #73 from coda0HQ/feat/public-artifact-latest-version-only").
- Vendored trees: `scripts/`, `references/`, `examples/`, `vendor/mermaid/`.
  `scripts/lib/*` resolves `<pkg-root>/references` and `<pkg-root>/vendor`
  two levels up, so the vendored directories must stay at the package root.
- The upstream SKILL.md is intentionally not shipped: its content is replaced
  by `procedures/*.md` (Pi menu procedures) plus the guidance block in
  `extensions/index.ts`. Sync upstream skill changes by re-reading SKILL.md
  for workflow changes and folding them into the procedures.

## Local changes (keep on every sync)

1. `scripts/artifact.mjs` — added `DEFAULT_API_URL = "https://coda0.com"` and
   appended it to the `loadConfig()` resolution chain (`--api` >
   `OPEN_ARTIFACTS_URL` > project config > global config > default), replacing
   the fail-without-config branch; help text documents the default.
2. Everything else must remain byte-identical to upstream so future syncs stay
   mechanical.
