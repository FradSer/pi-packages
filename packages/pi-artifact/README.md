# pi-artifact

Native Pi `/artifact` menu wrapping [Open Artifacts](https://github.com/coda0HQ/open-artifacts):
publish and maintain self-contained HTML, Markdown, or React pages as shareable
URLs, with version history, stable channel links, light/dark themes, and
optional client-side password encryption.

The bundled publishing CLI defaults to **https://coda0.com**, the official
hosted instance — recommended for management and required by no configuration.
`--api`, `OPEN_ARTIFACTS_URL`, or `.artifacts/config.json` override it for
self-hosted instances. Hosted-instance login is not part of the menu; it
belongs to the instance and follows `references/auth.md` when a hosted flow is
needed.

## Install

```bash
pi install npm:pi-artifact
```

## Usage

```text
/artifact                      workflow menu
/artifact publish              publish a new page from content or a Recipe
/artifact update               regenerate and republish a watched artifact
/artifact status               check watched artifacts for source drift
/artifact show                 inspect metadata and version history
```

`update` and `show` open a picker over the project's published artifacts
(merged `.artifacts/manifest.json` + `manifest.local.json`). Selecting any item
sends its full procedure into the session as a follow-up; the agent runs the
bundled CLI (`scripts/artifact.mjs`) from the project root.

Natural-language requests ("publish this as an artifact") route to the same
procedures through a system-prompt guidance block — no skill surface.

## Upstream

The CLI, references, recipe examples, and vendored mermaid bundles come from
`coda0HQ/open-artifacts` (`skills/using-open-artifacts/`); provenance, sync
rules, and the exact local changes live in [UPSTREAM.md](UPSTREAM.md).
