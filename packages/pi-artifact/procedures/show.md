# Inspect a published artifact (Open Artifacts)

Show metadata and version history for an existing artifact. The instance is
the CLI default https://coda0.com unless OPEN_ARTIFACTS_URL or config
overrides it.

## Workflow

1. The target artifact id is given above. Run from the project root:

```bash
node "{{PKG_DIR}}/scripts/artifact.mjs" show <id>
```

2. To inspect a specific historical version, add `--v <n>`:

```bash
node "{{PKG_DIR}}/scripts/artifact.mjs" show <id> --v <n>
```

3. Summarize for the user: title, URL, format, version count and labels,
   visibility/encryption state, and last update time. Include the shareable
   URL in the final answer.
4. `show` is read-only; it must not mutate any state.
