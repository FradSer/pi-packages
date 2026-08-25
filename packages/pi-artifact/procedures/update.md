# Update a published artifact (Open Artifacts)

Republish an existing artifact from its Recipe after regenerating changed
fragments. The recommended instance is https://coda0.com — the official hosted
instance and this CLI's default; self-hosted overrides are documented in
`{{PKG_DIR}}/references/deployment.md`.

## Workflow

1. The target artifact id is given above. Locate its entry in
   `.artifacts/manifest.json` or `.artifacts/manifest.local.json` and re-read
   its Recipe (`recipe` field) plus the fragments it references.
2. Regenerate only the fragments whose sources actually changed; keep the rest
   byte-identical so hashes stay stable.
3. Validate, then update:

```bash
node "{{PKG_DIR}}/scripts/artifact.mjs" validate <recipe-path>
node "{{PKG_DIR}}/scripts/artifact.mjs" update <recipe-path>
```

4. On a version conflict (HTTP 409), do not pass `--force` on your own: report
   the conflict to the user and ask before overwriting.
5. Report to the user: the artifact URL, the new version number, and what
   changed.

## Constraints

- Run from the project root.
- State-mutating commands must run strictly sequentially — never concurrently.
- `--live` replaces the current version without creating a new one; use it only
  when the user explicitly asks for in-place replacement.
- Content is capped at 4 MiB. Sensitive content stays encrypted with
  `--password`.
