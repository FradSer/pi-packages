# @fradser/pi-subagents

Delegate a prompt to one Pi child with a minimal tool grant and receive its
complete Session Result. A valid disk `agent.md` declares a durable identity;
otherwise the role and conversation are temporary and stay in memory.

```ts
// A label never selects a saved identity.
agent_start({ label: "file-review", prompt: "Inspect this file", tools: ["read"] });

// Select an existing disk identity explicitly.
agent_start({ identity: "reviewer", prompt: "Review these changes" });

// Copy the returned exact session; next input can wait behind active work.
agent_input({ session: "session:reviewer:<incarnation>", prompt: "Check the edge case too", delivery: "next" });
```

## Intent tools

The five intent tools are the only child tool surface: `agent_start`, `agent_input`,
`agent_stop`, and `agent_list`. An explicit intent host selection
remains selected, whether partial or complete. The loader cannot add excluded
tools. Startup requires a prompt. `identity` selects an existing disk definition;
`label` changes display only. Missing identities
fail before effects. Do not combine a saved identity with temporary `instructions`.

`agent_input` requires `delivery: "next"` or `delivery: "steer"`. Next input starts
once after current settlement and acknowledgement. A child holds at most eight
pending inputs and 256 KiB of pending bodies. Overflow is refused. Stop or exit
reports each input that never started. Steer guides active work without aborting
or starting another sequence. An idle steer is refused.

`agent_message` is an optional child-only capability. Add it explicitly to a
standalone child's effective grant when bounded intermediate progress should
reach the parent; it is never added to temporary or saved grants by default and
hosted children do not claim this channel. Each active input accepts at most 32
messages and 64 KiB in aggregate, with 16 KiB per message. The parent supplies
the trusted session and input attribution; message bodies are execution data,
not user consent, accepted work, or a final Session Result.

Receipts declare version 1, disposition, observed state, and input ID. Results carry
the same input ID. Cancellation ends the caller's wait, not an accepted reservation.
Readbacks retain bounded previews; complete final answers remain separate deliveries.

## The retired `agent` tool

The `agent` tool and its six actions are gone. The intent family is the only
child tool surface. A recorded branch that named `agent` receives the intent
family on its next session start. No user data moves, and no compatibility
adapter remains. The changeset carries the same announcement for every
published version. Read [ADR-0008](../../docs/adr/0008-retire-the-legacy-agent-tool.md)
for the decision and its reasoning.

**Both temporary and durable children become IDLE after every settled result.**
They accept next input in that same incarnation until `agent_stop` or parent shutdown.
No child process survives its parent Pi. There are no model-facing `persistent`,
`memory`, `worktree`, definition-creation or promotion parameters.

This is a runtime library and an independently installable Pi package. Installing
it loads the extension declared in `pi.extensions` and registers the intent family;
no task storage, Git branch or coordinator is required. `@fradser/pi-agent-teams`
and `@fradser/pi-tasks` consume the library, and the teams package bundles all three.

Read [VISION.md](VISION.md) for the execution contract and acceptance criteria, and
[AUTHORITY.md](AUTHORITY.md) when authorizing definition creation, migration or
child controls. Those documents are authoritative; the examples below show usage.

## Definitions and private homes

Create a disk identity by authoring `agent.md`, or explicitly authorizing the
library's `persistAgentDefinition` operation. The model-facing tools never
create a disk definition. For example, a user-authored reviewer definition is:

```text
<agent-dir>/agents/reviewer/agent.md
```

```markdown
---
name: reviewer
description: Review scoped changes and report evidence and limitations.
tools: read, grep, find, ls
---
Review only the supplied scope. Separate confirmed findings from unverified risks.
```

Supported frontmatter is `name`, `description`, `tools`, optional `model` and
`verify`; the body supplies standing instructions. Memory is present for every
disk identity, not a frontmatter opt-in. An inline `description` or `role_prompt`
only defines a session role when no disk definition wins.

| Scope | Canonical definition path |
| --- | --- |
| user | `<agent-dir>/agents/<name>/agent.md` |
| project | `<project>/.pi/agents/<name>/agent.md` |
| project-local | `<project>/.pi/agents/<name>.local/agent.md` |
| session | In-memory inline role; no definition file |

Precedence is project-local > project > user > session. A disk definition supplies
the role and tool ceiling; inline input cannot replace it, and explicit tools may
only narrow its grant, including to `[]`. A saved name is not a way to request an
amnesiac temporary execution.

`<agent-dir>` defaults to `~/.pi/agent` and respects `PI_CODING_AGENT_DIR`. Every
durable identity uses one private data home there, across definition scopes:

```text
agents/<name>/
  agent.md                  # user-authored identity, only for user scope
  state.json                # creation time, last project, memoryEntryCount
  memory/
    MEMORY.md               # derived index, at most 8 KiB
    <entry>.md
    proposals/
  workspace/                # ordinary scratch directory, not a checkout
  projects/<slug>/parents/<parent-key>/session/ # private parent/project history
```

A project definition may use this private home without creating a user definition.
Directories and `state.json` are derived data, not declarations of identity.
Read-only discovery creates nothing. Temporary children get neither a durable
home nor Memory and run with `--no-session`. This includes `fork`: the detached
structured conversation travels on the RPC control pipe and stays in a child-only
context extension. A versioned correlated setup acknowledgement precedes input or
readiness, and generic RPC `handled` is not evidence setup succeeded. The seed is
not a user message, session entry, temporary history file or environment value.

## Lifecycle and results

`agent_start` requires a prompt. It confirms RPC-accepted input, not the answer:
the complete result arrives asynchronously as an automatic follow-up. Continue
independent work, or end the turn when the next step depends on that result.
Do not poll, sleep, duplicate starts or search session files to wait for delivery.
Report only received results, tied to their prompt and session.

| Tool | Meaning |
| --- | --- |
| `agent_start` | Start a child and deliver its kickoff prompt; report effective configuration. |
| `agent_input` | Deliver nonempty input to one exact incarnation, queued with `next` or delivered with `steer`. |
| `agent_stop` | Record intent and close the exact child; release authority only after confirmed closure. |
| `agent_list` | Read the roster: known live or stopped incarnations and their bounded status summaries without controlling it. |
| `agent_list` | Page summaries of saved-but-offline definitions, live children and stopped incarnations. |

Each tool declares one closed input object, and the executor validates direct
library calls with the same rules. Wrong types, unknown or misplaced fields are
refused instead of coerced or silently ignored. `prompt`, inline `description`
and `role_prompt` retain authored whitespace; identifiers alone are normalized.
For example, `agent_list` cannot carry a `prompt` or tool grant.

`agent_list` accepts `offset` (default 0) and `limit` (default 20, range 1–50). Follow
`page.nextOffset` for a stable roster; a smaller page may be needed to meet the
aggregate budget. Readbacks/receipts have at most 16 KiB UTF-8 and 200 text lines,
and 32 KiB for either `details` or `structuredContent`, with explicit shortening
metadata. Totals count the complete roster, not only the page. Read one exact handle only through
one answer/error preview; the full final result is still delivered separately.

All model tools declare `outputSchema` and return matching `structuredContent`.
Programmatic callers (including codemode) receive that typed object rather than
receipt text. Intent data includes operation, disposition, observed state, pending
intent when applicable and the next actor. `content/details` remain available
for model text, TUI rendering and compatible callers. Consumers must stop parsing
receipt strings to discover the exact handle or acceptance outcome.

Tool cancellation before dispatch performs no effects. After a reservation or
native control is dispatched, it cancels only the caller's wait: the return is
`cancelled`, with `controlOutcome: uncertain`, pending intent and the exact handle
when known. It is not rejection, stop or authorization to resend. The original
ACK/progress/closure still settles the same resident; inspect before retrying.
Standalone startup controls allow thirty seconds for Pi loading and native
confirmation of the initial prompt, idle readiness or in-memory fork setup.
Prompt and steer controls for an already running child retain their five-second
acknowledgement window. After fork setup confirms the loaded child, its kickoff
also uses that ordinary window. Expiry does not repeat input, and these control
deadlines do not limit the child's model turn.
A host reserves its new exact incarnation synchronously and binds closure control
before awaiting readiness/input confirmation. A cancelled pending startup can
therefore be explicitly stopped through its original host. Its late confirmation
must match that reservation; it cannot claim or rebind a same-name successor.
The eager binding checks existing ownership before writing or pinning a handle;
a record already owned by another start is refused even with the same host object.
Late returned or thrown control failures remain bounded diagnostics on the pinned
record even when the caller stopped waiting, never on a replacement and never as
a guessed process-state transition. A definitive negative ACK still follows the
existing rejection contract, distinct from uncertain delivery.
An accepted child lives until explicit stop or parent shutdown, not parent-turn
cancellation. Cancellation never silently rolls back written durable data.

Copy the complete `session:<name>:<incarnation>` handle, including `session:`, from
`agent_start` or `agent_list`. A malformed handle is refused; a retired handle cannot reach a
replacement. Steering an idle child is refused and points at next input.
Results leave either kind of child IDLE, not stopped.

A stopped entry still retained on the roster can be inspected by its exact handle;
this reads recorded facts, not a living process or a completion verdict. Unknown
or replaced handles report `No known session` and never read a successor. There
is no historical archive or recovery of a lost parent roster. `agent_input` and
`agent_stop` continue to require a living exact incarnation. Recorded error
readbacks in `agent_list` are sanitized and limited to 1000 preview
characters with an explicit truncation marker; the raw roster error is unchanged.

Each settled turn delivers one Session Result: final UTF-8 text verbatim inside an
`<agent-result from=… session=… turn=…>` envelope. Intent inputs also carry input IDs. Preview limits never shorten the
delivered answer; hard transport limits fail explicitly. A result is execution
evidence, not another workflow's acceptance. A published coordinator owns its
hosted deliveries; standalone durable execution keeps its private history and
result owner. Library callers provide their own delivery callback.

Every intent result paints one collapsed row. A single-child row reads
`[tool] label · @name · status`. The name appears once, and the state word is not
repeated when the label already carries it. The authored prompt or steer headline
stays on the row, because it is the work itself. The collapsed view fits the
current width instead of applying a fixed-character headline; expansion wraps the
complete bounded input once, including the tail of its first line. Every other
fact, including the exact session, observed state, pending intent and next actor,
appears only after expansion. A moved line is dropped when the detail list already
carries it. Ctrl+O uses Pi's configured expansion keybinding; no package-specific
input hook is added.

Intent operation rows use the child's display label consistently, including
queued input, steering, inspection and failure notices. A roster has no state of
its own and names no child, so `agent_list` reads `[agent] listed`, and
`[agent] listed · 3 of 9` only when the page omits entries. The count stays
collapsed because a page that shows a subset must say so without being opened;
a page that shows everything has nothing to add, and a count that says "all of
them" answers a question nobody asked. A stop row confirms process closure, not
task completion.

Successful result rows display the Agent headline and one Markdown-rendered copy of the answer.
Native Markdown styles headings, lists, emphasis, links, and code blocks. Display
formatting never changes the original result text or its provenance.
Turn/session provenance stays in the original message content/details, not a
repeated `Session Result · turn N` display body. A short answer has no expansion
hint; pi-kit adds one only when the current width hides answer text and wraps
that same complete answer on expansion. There is no fixed character preview cap
or duplicated first line.

An authoritative empty/whitespace answer, provider error/abort, response length
limit or missing final message returns an explicit `unanswered` follow-up, never a
blank success envelope. It names the exact incarnation, sequence and observed stop
reason; any original partial/blank text remains verbatim, while provider diagnostics
are sanitized and bounded. TUI displays an error-band unanswered row, and roster
readbacks expose that outcome. This is no review verdict or acceptance. The child
stays IDLE for explicit input; the package launches no new task input or replacement.
Before settlement, an explicit recovery extension classifies the known diagnostic
`stream disconnected before completion: stream closed before response.completed`
for Pi's native retry policy. It preserves original text and error details, uses
the configured retry budget, and adds no retry loop or tool replay. Disabled or
exhausted retry still returns unanswered. Native readiness and intermediate frames
cannot consume this terminal classification.

Durable **data**, not a live child or an addressable session handle, can survive a
Pi restart. Reopening the same parent Pi session may restore its private child history with a new
incarnation and handle. Temporary roles and context cannot survive parent shutdown,
be promoted, or be recovered retroactively by defining the name on disk.

## Scratch workspace and project writes

Every durable identity has an ordinary persistent `workspace/` for scratch files.
The child receives its launch cwd and original project path explicitly. The
scratch directory is **not a project checkout**: to edit project files, the child
writes the original working tree directly. Parallel children must respect their
assigned file ownership; this layer does not arbitrate shared edits.

There is no Git worktree, branch, automatic commit, merge, rollback snapshot or
preserve/release hook. Stopping a child does not undo its writes. A tool grant,
prompt or private scratch directory is not an operating-system sandbox; shell
access can reach files available to that OS user.

Private durable Pi history lives at
`agents/<name>/projects/<slug>/parents/<parent-key>/session/`. The parent key is
the full SHA-256 digest of the native parent Pi session ID with a `parent-`
prefix. Reopening the same parent session restores only its own child history;
a new parent session starts with independent conversation history. Different
parents can run the same identity in the same project simultaneously, while
sharing the identity's Memory and ordinary scratch. Forked context is a snapshot.

Existing `projects/<slug>/session/` history is preserved in place and is not
automatically imported into a new parent partition. No data is moved or deleted.
Headless callers of `executeChildIntent` can set the trusted runtime option
`parentSessionId` to preserve history across process restarts. Omitting it uses
one process-local identity. The model-facing tools cannot select that ID.
The two-argument `agentSessionPath` helper keeps returning the legacy path for
callers inspecting existing data; actual tool execution supplies the parent ID.

## Agent Memory

All disk roles receive Agent Memory at `<agent-dir>/agents/<name>/memory/`;
temporary roles do not. Entries describe reusable methods, judgment criteria and
operating patterns. Project facts, decisions and history belong to Project Memory,
which `pi-continual-learning` owns.

Only the bounded index of filenames and one-line relevance cues is injected,
never entry bodies. The complete Memory block, including guidance and omission
notices, obeys the 8 KiB UTF-8 budget. `MEMORY.md` obeys the same budget. Shortening
is visible and omissions are counted; entry files remain authoritative. Read a
full entry with `read` when needed. The child refreshes its index for each input.
Regenerating the index updates `memoryEntryCount` in existing state without
replacing creation time, last project or unrelated fields.

For consolidation, `listAgentMemoryRoots()` returns existing canonical Memory
folders in stable order. A user `agent.md` must validate, or the home's valid
`lastProject` locator must still resolve a matching project/project-local disk
definition. State alone declares no identity; stale or unbound project data is
not listed. Discovery does not create or migrate data.

`agent_memory action=append` creates or **replaces a same-name entry**, rather
than appending bytes. It requires an effective `edit`, `write`, `bash` or
`powershell` grant and nonempty `name`, `description` and `body`. A shell is not
read-only. `action=propose` writes an unaccepted local candidate, requiring `body`;
it never merges that candidate. Read-only execution roles may use this narrow
proposal-write exception, not capability append or generally read-only disk
access. They can also report lessons in their results. Existing overwrite and
proposal authority are unchanged by the tool-definition improvements. Proposals live in `memory/proposals/` and never automatically
become entries. Review and merge remain separate decisions for continual-learning
or a human reviewer; creating a definition or data home accepts no proposal.

## Legacy storage

Old flat `agents/<name>.md` definitions, entries directly under `agents/<name>/`,
`subagent-sessions/` history and legacy workspaces require an **explicit,
user-approved migration**. Discovery and startup do not migrate them. Migration
must inventory known sources, copy rather than delete originals, preserve
provenance, refuse conflicts and symlink escapes, and never remove legacy Git
worktrees or user output. See [AUTHORITY.md](AUTHORITY.md) before migrating.

## Activation, UI and child contributions

The validation cohort is Pi **1.0.0**. Tool selection is availability, **not** a
security authorization gate: delegation still needs user or applicable instruction
authorization and any host permission policy. No model-controlled `authorized`
flag or extra user-interaction tool is introduced. The intent tools are
not advertised as read-only or idempotent; even a read-only caller can start a
process or request its closure. On providers that support transcript-anchored
tool additions, the small `subagents_enable` loader selects the recorded intent
family under explicit delegation authorization, without starting a process. Other providers start eagerly
to avoid rewriting a cached prompt prefix. Native selection records restore the
active branch; a model switch does not reshuffle it.

In TUI mode, standalone children have a pi-kit above-editor row throughout their
resident lifetime. Starting or working children show a spinner and current activity;
settled children retain a static `Idle` row indicating that they can receive input.
Idle rows do not repeat the previous turn's streaming text. Roster callbacks
refresh the display without polling. Confirmed stopped children leave the widget;
parent shutdown clears it.
Print/RPC sessions mount no terminal widget. A coordinator renders its hosted
children; standalone rows are not duplicated.

Intermediate parent messages use a separate `subagents-parent-message` custom
message and the same passive lifecycle band. The collapsed row is a short
`[agent] message · @name` line; expansion keeps the original body as Markdown
and reveals exact session, input and sequence metadata. Delivery follows the
parent turn with `followUp` and `triggerTurn: true`; during shutdown it queues
as `nextTurn` with `triggerTurn: false`.

The spawner hardcodes no extension path or capability tool set. Consumers supply
explicit repeatable `-e` contributions with matching `capabilityTools`:

```ts
spawnResident({
  agentName: "reviewer",
  extensions: [SUBAGENT_EXTENSION_PATH],
  capabilityTools: ["agent_memory"],
  tools: ["read"],
  env: {
    [SUBAGENT_ROLE_ENV]: "reviewer",
    [SUBAGENT_TOOLS_ENV]: "read,agent_memory",
    [SUBAGENT_DEFINITION_ENV]: definition.source, // absolute canonical agent.md
    [SUBAGENT_SCOPE_ENV]: definition.scope,      // user, project or project-local
    PI_SUBAGENT_PROJECT_CWD: projectCwd,
  },
  // Other configuration and lifecycle callbacks supplied by the caller.
});
```

The runtime contributes stream classification to every public child and Memory
to every disk identity. The stream contribution registers no tools or storage.
Memory does not apply to temporary children.
Declaring capability tools without an extension to register them is refused.
Children use `--no-extensions` and only explicit paths, never ambient parent
extensions. The Memory contribution validates its explicit disk definition path,
scope and name. An ambient role marker, data home or state file alone is inert;
project bindings validate the project source without requiring a user `agent.md`.

A child receives an allowlisted environment, not the parent's whole environment.
`PI_CODING_AGENT_DIR` preserves configured model/auth resolution, while
`PI_TEAMMATE_ENV_ALLOW` permits additional exact names. This reduces credential
leakage; it does not confine disk access. See `src/child-env.ts`.

## Library boundary

| Module | Owns |
| --- | --- |
| `src/agents.ts` | Canonical disk definitions, scopes and inline session roles |
| `src/workspace.ts` | Private durable data homes, ordinary scratch and project history |
| `src/migration.ts` | Explicit, user-approved copy-only legacy migration |
| `src/memory.ts` | Capability entries, bounded indexes and unaccepted proposals |
| `src/agent-extension.ts` | This package's child Memory contribution |
| `src/stream-recovery.ts` | Known premature-close classification for Pi's native retry policy |
| `src/spawner.ts` | Native RPC child transport, readiness, input acknowledgement and termination |
| `src/agent-tools.ts` | Grantable Pi built-in tool ids and drift checks |
| `src/child-execution.ts` | Shared child execution, intent operations and standalone result delivery |
| `src/intent-tools.ts`, `src/input-sequences.ts` | Five model tools, input reservations and FIFO sequencing |
| `src/roster.ts`, `src/session-route.ts` | Incarnation facts and exact handles |
| `src/session-result.ts`, `src/leader-reports.ts` | Results, provenance and delivery records |
| `src/parent-message.ts`, `src/parent-message-extension.ts` | Explicit child-to-parent intermediate messages and bounded validation |
| `src/work-context.ts` | Safe active-context snapshots, without parent tool authority |
| `src/participant-registry.ts` | Read-only cross-package participant shape, not coordination policy |
| `src/tool-activation.ts`, `src/extension.ts`, `src/rows.ts` | Activation, entry wiring and passive lifecycle UI |

The execution layer neither schedules work nor arbitrates ownership, exchanges
peer messages, integrates branches or accepts results for another workflow.
For focused authoring guidance, read [references/agent-roles.md](references/agent-roles.md).

## License

MIT
