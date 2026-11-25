# Deprecated packages

Packages in this directory are retired. Their sources and Git history are kept for
reference, but they are outside the active `packages/*` workspace and outside the
publish allowlist. Do not add features or change runtime behavior here; only
documentation and migration notes belong in an archived package.

Each archived package has a `DEPRECATED.md` naming the reason and any remaining
compatibility obligations.

- [`tasks`](tasks/DEPRECATED.md) — the task plugin is no longer suitable for
  current SOTA models. It was removed from the user's Pi configuration and from
  new releases; the published npm version remains only for existing consumers.
- [`plan-mode`](plan-mode/DEPRECATED.md) — the plan plugin was retired in favor
  of the repository's `pi-sdlc` and `pi-matt-pocock` planning flows. It was moved
  out of the active workspace, off the publish allowlist, and out of the
  maintainer's Pi configuration.
