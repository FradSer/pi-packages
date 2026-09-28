# @fradser/pi-tasks

The Work Item domain: what a durable piece of work is, how Work Items depend on
and exclude each other, and how the board survives a restart.

This is an internal workspace runtime library in the `pi-packages` monorepo, in
the same category as `@fradser/pi-kit` and `@fradser/pi-subagents`. It declares
no `pi` manifest key and is not installed as a Pi extension on its own.
`@fradser/pi-agent-teams` consumes it.

## Boundary

Everything here describes **Work**, not the processes that perform it and not the
messages between them. Nothing in this package knows about spawning, rosters,
presence, or peer mail.

| Module | Owns |
| --- | --- |
| `src/types.ts` | `BoardTask`, `TaskStatus`, `TaskIntent`, `WORK_RUNTIME_VERSION` |
| `src/graph.ts` | Work id derivation, resource normalization, supersession chains, dependency-cycle detection, and the resource-conflict primitive |
| `src/persist.ts` | Board directory layout, atomic board read/write with version rejection, and exclusive-create claim/submit intents |

`resourcesConflict` is the primitive. Deciding *which* held assignments to
compare against it is a roster question and stays with the package that owns the
roster — that separation is what keeps this package free of coordination state.

## Persistence

```text
~/.pi/agent/tasks/<sessionKey>/board.json            leader-owned, atomic replace
~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      exclusive-create claim intents
~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json exclusive-create submit intents
```

The leader is the sole writer of `board.json`. A worker never writes the board;
it expresses intent through an exclusive-create marker, so exactly one racer wins
a contested claim. An absent board is a fresh session; a present but unreadable
one is an error and is never treated as empty, because that would silently
discard durable Work. An incompatible `runtimeVersion` is rejected rather than
migrated.

`sessionKey` comes from `@fradser/pi-kit` so this package and any other keeping
per-session state agree on which session a directory belongs to.

## Status

Extracted from `@fradser/pi-agent-teams` as part of splitting that package into
subagents / task / agent-teams. The board state container, the lifecycle
transitions, the verification gate, and the `work` tool are **not** part of this
extraction and land in later steps. The design and remaining sequence are in
`docs/spec-agent-teams-three-package-split.md` at the repository root.

## License

MIT
