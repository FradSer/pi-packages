# Deprecated: @fradser/pi-plan-mode

Status: archived on 2026-11-21.

The user retired this plugin. Its planning contract is already covered by the
repository's active planning surfaces — `pi-sdlc` intent and plan stages and
`pi-matt-pocock` planning workflows — so a separate read-only plan extension kept
its own model switching, tool guard, worker plumbing and session-replacement path
without adding a capability the other packages lack. The source is kept for
history and migration reference.

## What changed

- The directory moved from `packages/plan-mode/` to `deprecated/plan-mode/`, so
  it is outside the active `packages/*` workspace.
- `@fradser/pi-plan-mode` was removed from the publish allowlist in
  `scripts/publish-release.mjs`; no release from this repository publishes it.
- The package entry was removed from the maintainer's Pi configuration, together
  with its recorded changelog version. `/plan` commands are no longer registered.
- Repository tests and the `plan` commit scope now describe the archived path.

## Compatibility

No published package declares a dependency on `@fradser/pi-plan-mode`, so nothing
else in the workspace or on npm breaks when it stops receiving releases. Existing
npm versions stay installable for anyone who pinned them; the supported registry
action is `npm deprecate @fradser/pi-plan-mode "retired; use the sdlc or
matt-pocock planning workflows"`, which warns installers without breaking an
existing install. That registry mutation was not performed by this change.

Users who still rely on the archived command surface can see what it did in
[README.md](README.md) and [AGENTS.md](AGENTS.md). Treat this directory as
frozen: no new features, fixes, or runtime behavior changes belong here.