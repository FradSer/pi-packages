# Check watched artifacts for drift (Open Artifacts)

Report which watched artifacts are stale relative to their declared sources.
The instance is the CLI default https://coda0.com unless OPEN_ARTIFACTS_URL or
config overrides it.

## Workflow

1. Run from the project root:

```bash
node "{{PKG_DIR}}/scripts/artifact.mjs" status
```

2. Summarize the result for the user: for each watched artifact, whether it is
   fresh or stale, and which watch globs changed.
3. For stale entries, offer to update them (one at a time) — never republish
   automatically; the user decides per artifact.
4. If there are no watched artifacts, say so plainly instead of inventing work.

## Constraints

- `status` is read-only; it must not mutate manifests, credentials, or remote
  state.
- Report evidence: artifact id, recipe path, and what drifted.
