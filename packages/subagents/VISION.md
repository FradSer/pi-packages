# Subagent execution contract

## Purpose

Give one child a prompt and the smallest useful tool grant, let it process that
input, and return the complete result. One parent and one child are sufficient;
no tasks, coordinator, Git branch or worktree is required.

## Identity and lifetime

A valid disk `agent.md` is the only durable identity declaration. A definition
has `user`, `project` or `project-local` scope; an inline role has `session` scope
and exists only in memory. The model-facing tool cannot create a disk definition.
There are no `persistent`, `memory`, `worktree` or promotion parameters.

Every child, temporary or durable, becomes **IDLE after a settled result** and
accepts next input in that same exact incarnation. Settlement does not close the
process. Steering guides active execution without replacing the turn;
`agent_stop` and parent shutdown close the process. No child survives its parent Pi.
Durable data survives process shutdown; temporary context and roles do not.
A temporary conversation cannot be retroactively promoted or recovered by
creating a definition later.

The intent interface separates `identity`, `label`, and the exact session handle.
An explicit identity selects a valid disk definition; a missing identity is refused.
A label changes display only. It never selects identity or changes private storage.
Temporary instructions cannot accompany a saved identity. Explicit tools only
narrow its ceiling. The definition resolver retains its original precedence.

## Definition and storage

Frontmatter contains `name`, `description`, `tools`, optional `model` and `verify`.
The body supplies standing instructions. Canonical user definitions live at
`<agent-dir>/agents/<name>/agent.md`. Project definitions live at
`<project>/.pi/agents/<name>/agent.md`, and project-local overrides at
`<project>/.pi/agents/<name>.local/agent.md`; precedence is project-local >
project > user > session. A project definition does not automatically get copied
into the user definition library.

Each durable identity has one private data home under the configured agent dir:

```text
agents/<name>/
  agent.md                 # user-authored identity, if user scope
  state.json               # creation time, last project, memory entry count
  memory/
    MEMORY.md              # index, 8 KiB injection budget
    <entry>.md
    proposals/
  workspace/               # ordinary scratch directory, no Git metadata
  projects/<slug>/parents/<parent-key>/session/ # private parent/project Pi history
```

A project-scoped definition may use that same private data home without creating
a user-scope `agent.md`. Derived directories and state are not identity records.
Memory and scratch remain shared by the identity. History is separately keyed by
the original project and the trusted parent Pi session ID, hashed into a path.
Reopening that same parent session resumes its history; a new parent session
starts independently. Two different parents can run the identity simultaneously.
Existing project-only history remains untouched and is not automatically imported.
Headless embeddings can supply `parentSessionId` in runtime options; without a
native or explicit ID, their history uses one process-local identity.
Durable identities always have Memory and a scratch workspace; temporary roles
have neither and use no-session. Session history candidates must be regular
single-link files, never symlinks, hard links or jsonl directories. Temporary forks
use serialized structured history on the control pipe and a child-only context
extension; no seed/history file is written. The child receives both its launch
cwd and the original project path explicitly. A private workspace is not a checkout: changing
project files means changing the original working tree directly. There is no
branch, merge, rollback snapshot, automatic commit or privilege confinement.

`agent_list` distinguishes saved definitions with no current process from live and
stopped incarnations. Read-only discovery creates no directories. `agent_list`,
`agent_input` and `agent_stop` require complete exact incarnation handles and
cannot resolve a predecessor to its replacement. The read-only roster also accepts
a known stopped incarnation still retained on the roster, exposing its recorded
status, bounded output and errors without reviving or controlling it. This is not
a history archive: a replaced entry or a lost parent roster cannot be recovered
by inspection. Process controls still require a living exact incarnation.

## Tool boundary

Model sessions use five closed input objects: `agent_start`, `agent_input`,
`agent_stop`, and `agent_list`. The intent family is the only
child tool surface. A recorded branch that named the retired `agent` tool receives
the intent family on its next session start; no compatibility adapter and no
in-transcript notice remain. Startup requires a prompt.
Input requires an exact session, prompt, and `delivery` enum: `next` or `steer`.
Next input starts after the active sequence settles and its ACK is observed.
Each incarnation holds at most eight pending records and 256 KiB of pending bodies.
Overflow is refused. Stop or exit reports each unstarted reservation as cancelled.
Steer retains the active input ID; it never becomes next input or aborts a turn.
Queued dispatch consumes prior terminal reports and rechecks the original host
policy before changing input IDs or settlement flags. It never bypasses task authority.
A steering receipt pins its active input ID before awaiting native acknowledgement.
Failed or uncertain startup confirmation grants no accepted-input authority.

`agent_message` is an explicit standalone capability for bounded intermediate
progress. It is absent from temporary children and saved grants unless named in
the effective grant; hosted children currently refuse this standalone capability.
A future host-owned channel requires its own public contract. The runtime accepts messages only from the
current living exact incarnation while an input is active, deduplicates tool
calls per input, and limits each input to 32 messages and 64 KiB aggregate with
16 KiB per body. Parent notices carry trusted session/input attribution and a
monotonic per-incarnation sequence. They are untrusted execution data and never
settle the final result or establish user consent, accepted work, or authority.

The exported `executeChildIntent` API keeps one intent-named operation set and
names the operations it offers. Recorded branches restore the same intent family.
Excluded tools remain excluded; a renamed tool cannot widen a saved grant.
Wrong types and unknown fields are refused before effects. Authored prompt bytes
stay unchanged. Only `agent_list` accepts pagination controls.

Management receipts and readbacks have aggregate budgets: at most 16 KiB UTF-8
and 200 lines for text, and 32 KiB for either details or structuredContent.
`agent_list` pages are deterministic for an unchanged roster and report totals,
omissions and nextOffset. The roster reads each retained exact incarnation with
explicitly marked preview shortening; truncation never changes raw roster state or
final-result delivery. Successful and returned failed calls share a declared
structured output contract, with operation, disposition, observed state and next
actor; acceptance receipts are never a final answer. Codemode receives
structuredContent rather than parsing text; content/details remain the
human/model and renderer projections.

Every result paints one collapsed row. A single-child row reads
`[tool] label · @name · status`, naming the child once, and it does not repeat a
state word the label already carries. The authored prompt or steer headline stays
on the row. A roster subject has no state, so it reads
`[agent] listed · @children · N of M`. Every other fact is expansion detail, and
a moved line is dropped when the detail list already carries it.

Cancellation before dispatch performs no operation. After dispatch it cancels the
caller's wait only: return cancelled with uncertainty, pending intent and the exact
handle when known. The original acknowledgement/progress/closure continues to
settle that exact incarnation and is always observed; no automatic kill, repeated
input, guessed idle restoration or successor retargeting. Once accepted, a child
is parent-session-owned, not owned by the lifetime of its parent tool turn.
A successful hosted start reserves its new roster incarnation synchronously before
awaiting confirmation. Its original host owns exact closure control from that
reservation, including while the caller's startup wait is cancelled. Confirmation
must match the reserved incarnation and may not rebind a successor. Before eager
binding, an already-owned exact record is refused as another invocation's
reservation, even if that invocation uses the same host object. A later roster
snapshot alone cannot prove original-reservation provenance. Returned
failures and rejected promises that settle after caller cancellation remain
bounded diagnostics on only the still-current pinned record; recording them
changes no status and grants no retry or process-success authority.

Tool availability is not authorization. The loader changes selection, never
authorizes delegation or starts a process. User/instruction authorization and
host permission policy remain outside the tool's model-controlled arguments.
Memory append keeps its existing create-or-replace semantics; read-only execution
roles may write unaccepted proposal files under the existing narrow exception.
Neither behavior changes merely to improve naming or output types.

## Responsibilities

- Definitions, session-only roles and resolved tool grants.
- Child creation, native RPC readiness and acknowledged input.
- Fresh/forked context without unfinished tool exchanges or parent tool authority.
- Complete Session Results, input IDs and one delivery per settled sequence.
- Explicit, bounded child-to-parent intermediate messages, separate from results.
- Bounded next-input records, FIFO dispatch, and explicit cancellation of unstarted records.
- Private durable homes, parent/project-scoped history and capability Memory.
- Credential leakage defense and explicit child extension contributions.
- Provider-compatible activation and pi-kit passive above-editor activity rows.
- Non-destructive, explicit migration of known legacy storage.

The execution layer does not schedule dependencies, arbitrate shared work,
exchange peer messages, integrate branches or accept another workflow's output.
A result is execution evidence, not acceptance. A completed blank message, failed
provider response, length limit or missing final message is an explicit unanswered
execution outcome, not a review verdict. Such outcomes resume the parent once
with diagnostics and leave the resident IDLE; no new task input or replacement
is launched. Before settlement, the explicit child recovery contribution classifies
a known premature stream closure for Pi's configured native retry policy.
That policy alone owns the retry budget, backoff and cancellation. It does not
replay completed tools or dispatch the original task again. Disabled or exhausted
retry still produces an honest unanswered result. Intermediate frames are not outcomes.
Memory proposals are candidates;
review/merge remains with continual-learning.

## Acceptance

1. Write Given/When/Then scenarios before RED regression tests and GREEN changes.
2. Exercise real parsing and callback order at the highest available seam.
3. Preserve final UTF-8 bytes; hard transport quotas fail explicitly, and display
   previews never silently truncate the delivered result.
4. Separate startup, accepted input, settled output and confirmed close.
5. Exact handles and late callbacks cannot reach a replacement; uncertain control
   outcomes retain honest authority.
6. The receipt reports effective configuration. No invocation widens an existing
   role grant or creates a disk identity.
7. Run affected tests, Pi 1.1.0 TypeScript checks, packed-resource validation,
   isolated real Pi print/RPC verification and interactive TUI verification.
8. Migration preserves originals, refuses conflicts and symlink escapes, and does
   not delete legacy worktrees or user output. No publication or remote writes.

Read @AUTHORITY.md when modifying authorization, migration or child controls.
