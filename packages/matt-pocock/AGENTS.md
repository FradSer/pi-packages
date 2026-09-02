# Repository Guidelines

## Project Structure

`packages/matt-pocock/` publishes `pi-matt-pocock`, a Pi extension package.
`index.ts` is the extension entry; `src/` contains command, state, and procedure
loading logic. `procedures/` contains internal Markdown procedures and support
files. These are package resources, not skills: no `SKILL.md` may be shipped.
BDD scenarios live in `features/`, and executable checks live in `tests/`.

## Commands

```bash
python3 -m pytest packages/matt-pocock/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/matt-pocock pack --dry-run
```

## Harness & Tool Design

- **Harness Boundaries**: Expose `/matt-pocock` as the command surface; do not add per-procedure commands or skills. Persist choices via `pi.appendEntry` and inject procedure Markdown as a follow-up user message. State entries record route/phase selection, not procedure completion. When a procedure's done condition makes the next applicable procedure clear, the agent transitions with `matt_pocock_workflow` immediately; the command menu transition is an explicit user override.
- **Workflow Tools**:
  - `matt_pocock_workflow`: Uses TypeBox unions across the 5 stable routes (`idea-to-ship`, `hard-bug`, `triage`, `wayfinding`, `architecture`). If an invalid procedure is passed, falls back to the route default with a diagnostic note.
  - `matt_pocock_ask`: Progressive interview tool enabled via `pi.setActiveTools()` only while a workflow is active. Presents 2–4 choices via `ctx.ui.select` (with custom typing option); falls back to the recommended choice on timeout (default 60s) or in headless mode (`!ctx.hasUI`).
  - `matt_pocock_workflow` renders a compact monitor-style activation row (`[matt pocock] started · <route and phase>`); `matt_pocock_ask` delegates its lifecycle transcript rendering to `@fradser/pi-kit` (`[matt pocock] ask ·`).

## Sync and release

Upstream synchronization is selective: preserve Pi-specific interaction,
collaboration, instruction-file, and git-agent guidance. New upstream
`SKILL.md` files become plain procedure Markdown files under `procedures/`,
with frontmatter stripped and cross-procedure calls turned into relative links.
Update `features/matt-pocock.feature` before behavior changes, then extend the
Python contracts. Add a Changeset for a published behavior change.
