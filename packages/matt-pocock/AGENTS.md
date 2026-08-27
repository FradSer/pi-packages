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

## Harness boundaries

- The only public surface is `/matt-pocock`; do not add one command per
  procedure or a `/skill:matt-pocock` surface.
- Persist workflow choices through `pi.appendEntry`; restore only the latest
  state on the active session branch.
- A state entry records a selected route or explicit end. It does not prove a
  procedure completed. Users move phases manually.
- Inject a selected procedure as a follow-up user message. Add only compact
  route and phase context in `before_agent_start`.
- Keep automatic completion inference, session creation, teammate creation,
  tool-level BDD/TDD write blocking, per-procedure commands, and a second
  skill surface deferred in `TODO.md`.

## Sync and release

Upstream synchronization is selective: preserve Pi-specific interaction,
collaboration, instruction-file, and git-agent guidance. New upstream
`SKILL.md` files become plain procedure Markdown files under `procedures/`,
with frontmatter stripped and cross-procedure calls turned into relative links.
Update `features/matt-pocock.feature` before behavior changes, then extend the
Python contracts. Add a Changeset for a published behavior change.
