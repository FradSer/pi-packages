# The intent family is the only child tool surface, and one result paints one row

`@fradser/pi-subagents` keeps its five intent tools and loses the `agent` tool, its six-action API, its selection branches and its receipt language. Every child result then paints one collapsed row that names the child once.

## Context

The package shipped two model-facing families for the same work. The intent family (`agent_start`, `agent_input`, `agent_stop`, `agent_inspect`, `agent_list`) is a thin layer over `executeAgentAction`, which still speaks the legacy verbs `start`, `send`, `interrupt`, `stop`, `inspect` and `list`, and still produced the legacy uppercase receipt (`AGENT ·`, `GRANT ·`, `RESULT ·`) and its own row spec. The selection machinery read recorded branch history to restore `agent`, exposed `--subagents-interface legacy`, and kept a loader path that could revive the adapter after the fact.

Two costs followed. The legacy row repeated the child's name, once in the title and once in the body line, so a person's read of `[agent] inspected · @reviewer` was `inspected`, `working` and the same name again. And the wider design kept two vocabularies for one operation, which is why a `stopped` receipt could disagree with the intent family's `disposition` about what just happened.

The README promised support for the legacy surface through the 0.1 release line and required an announced migration plus a release decision before removal. Both conditions are now met: this ADR is the decision, and the changeset and README carry the announcement.

## Decision

1. **One family.** The extension entry registers the five intent tools and `subagents_enable`. The `agent` tool, `AGENT_TOOL_PARAMS`, `AGENT_CAPABILITY_TOOLS`, `agentRowSpec`, the `--subagents-interface legacy` flag and every restore path that selects `agent` are removed.
2. **One executor vocabulary.** The shared executor is intent-named and its operations are the intent operations, so the six-action union leaves the public API. The published coordinator seam (`setAgentHost` and its start/stop contract) stays, because ADR-0007 depends on it.
3. **Recorded branches move silently.** A branch whose recorded selection names `agent` receives the intent family on the next session start. No hidden adapter and no in-transcript notice: an in-transcript notice would not reach the model that still asks for `agent`, so the migration is announced in the changeset, the README and the tool descriptions instead.
4. **One collapsed row per result.** A single-child row reads `[tool] label · @name · status`. The name appears once, the state word is not repeated when the label already carries it, and the authored prompt or steer headline stays on the row because it is the work itself. Every other fact is expansion detail, and a moved line is dropped when the detail list already carries it.
5. **A roster subject has no state.** `agent_list` reads `[agent] listed · @children · N of M`. The count stays collapsed because a page that shows a subset must say so, and one child's status never becomes the subject's status.

## Lifecycle update (2026-10-05)

`agent_inspect` is retired too. The per-child read existed to answer "what is this
child doing, and what did it say"; after the row contract landed, the roster says
the first and a delivered Session Result carries the second, so the tool only
offered a way to poll. Its removal changes three things: `CHILD_OPERATIONS` has four
entries, the `agent` input operation carries its own delivery rather than a
separate steer verb, and `RETIRED_TOOLS` in the selection machinery now scrubs
`agent_inspect` as well as `agent`, because a name recorded before its removal
would otherwise stay active on a transport that never registered it. The list
receipt says a status summary only; the answer arrives with the Session Result.

## Consequences

- Calling `agent` is a breaking change for any recorded script. The announced migration is the changeset, the README and the five tool descriptions; no user data moves and no migration runs on discovery or start.
- `@fradser/pi-agent-teams` calls the renamed executor. Its coordinator host keeps the same authority, so its behaviour is unchanged.
- The legacy uppercase receipt disappears with the legacy row. Anything that parsed those lines must read the structured `details` instead.
- Schema and row tests that exercised `AGENT_TOOL_PARAMS` and the legacy row are replaced by intent-tool equivalents, so coverage follows the surviving surface rather than the deleted one.
- The selection machinery loses its family switch, which removes the recorded-branch precedence rules it needed and the flag that selected them.
