# Publish a shareable page (Open Artifacts)

Publish a self-contained HTML, Markdown, or React artifact the user can share
by URL. The recommended instance is https://coda0.com — the official hosted
instance and this CLI's default. Self-hosted instances are configured via the
`--api` flag, `OPEN_ARTIFACTS_URL`, `.artifacts/config.json`, or
`~/.config/open-artifacts/config.json`; see `{{PKG_DIR}}/references/deployment.md`.

## Workflow

1. Understand what the user wants to share: audience, content, whether it is a
   report, dashboard, visualization, document, or interactive page. Do not
   publish for short answers, code snippets, or one-off content.
2. Read `{{PKG_DIR}}/references/design.md` and
   `{{PKG_DIR}}/references/recipe.md` before authoring. For canvas formats also
   read `{{PKG_DIR}}/references/canvas.md`; for React read
   `{{PKG_DIR}}/references/scripts.md`.
3. On the first `create` in a project, ask whether the artifact should be local
   and recommend local. Record the choice in `artifact.local`: shared sources go
   under `.artifacts/recipes/` + `.artifacts/fragments/` (committable), local or
   encrypted sources under `.artifacts/recipes.local/` +
   `.artifacts/fragments.local/`.
4. Author the Recipe plus ordered fragments. The Recipe owns title, favicon,
   format, scope, watch globs, channel, level, Canvas mode, locality, and
   encryption policy.
5. Validate, then create — exactly one final publish request:

```bash
node "{{PKG_DIR}}/scripts/artifact.mjs" validate .artifacts/recipes/<name>.recipe.json
node "{{PKG_DIR}}/scripts/artifact.mjs" create .artifacts/recipes/<name>.recipe.json
```

6. Report to the user: the artifact URL, its id, and the version number.

## Constraints

- Run from the project root; Recipes, fragments, manifests, and watch globs
  resolve against the current working directory.
- State-mutating commands (`create`, `update`, `delete`, `migrate`, `ack`,
  `auto-update`) must run strictly sequentially — never concurrently. A lost
  write token is unrecoverable.
- Content is capped at 4 MiB. Sensitive content is encrypted client-side with
  `--password`; the server only stores ciphertext.
- If the CLI reports an authentication error on a hosted instance, point the
  user at `{{PKG_DIR}}/references/auth.md` rather than improvising tokens.
