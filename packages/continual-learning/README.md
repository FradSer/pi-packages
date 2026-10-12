# pi-continual-learning

Learns durable Memory and scoped Harness rules from completed user tasks.
Model weights are out of scope.

- **Memory** supplies a bounded metadata index before generation. Full entries
  are read only when needed; omitted entries remain discoverable.
- **Harness** uses one flat `rules` list for new declarations: `skill` and `text`
  deliver scoped guidance, while `bash` supplies messages and optionally confirms
  or blocks a command before execution. Installed legacy policies retain their
  original protections through read-only compatibility.
- **AGENTS.md consolidation** keeps common project instructions small and moves
  detailed knowledge into Memory or skill rules, retaining conditional pointers
  when needed.

These surfaces have different authority. Memory is durable, untrusted reference
knowledge injected into later context; it cannot enforce behavior. Harness is the
executable-validation surface: a rule can guide, confirm, or block only through
the parent-owned evaluator and its evidence-backed positive/negative cases.
`skill`/`text` rules and AGENTS.md are guidance for a bounded context, not proof
that the model complied. Manual, built-in, personal, disabled, invalid, and
legacy protections remain human-owned. A task may produce proposals for more
than one surface, but the same statement is not copied merely to increase
coverage.

## Install and commands

Python 3 must be available as `python3` for the bundled Memory validator.

```bash
pi install npm:pi-continual-learning
```

| Command | Purpose |
| --- | --- |
| `/memory` | Open the Memory management panel |
| `/memory <request>` | Record an explicit natural-language Memory request; the parent validates a Memory-only change |
| `/consolidate` | Learn from the current task |
| `/consolidate full` | Perform full Memory, Harness and AGENTS.md maintenance |
| `/harness` | Open the Harness rules panel and choose its write scope |
| `/harness <request>` | Create or update a rule in project shared configuration by default |

The `/memory` panel has three top-level entries: **Browse memories**, **Learning
settings**, and **Recent learning**. Phase policies are under **Advanced** in
Learning settings. Lists scroll with keyboard focus; history targets precede
compact dates. Readers preserve the logical text position when resized and
default to Close. Settings and policies return to their direct parent with
selection retained; closing a detail returns to
its previous list position. The native reader supports Up/Down and Page Up/Down
without copying document bodies into the chat. History lists show numbered dates,
phases, targets and outcomes. A history item opens its preview and its **Undo** action;
headless undo still requires the exact id and `--yes`. Policy menus show effective
values and explain that they control automatic phases; explicit consolidation uses
validated plans and still honors AGENTS.md disablement. Existing Memory retrieval
continues when automatic learning is off. RPC hosts retain native select dialogs.

An explicit `/memory <request>` asks the parent to retain the user's request as
Memory. It can be used while automatic learning is off, and it changes only the
Memory surface. The request is evidence for a bounded proposal; validation,
privacy checks, mutation and the receipt remain parent-owned. A request can
correctly produce no write when it is not durable, safe, or sufficiently
grounded.

Learning uses the current session model unless a separate provider/model pair
is configured. An explicit invalid or empty pair in `memory.json` is diagnosed
and prevents a worker from silently using a different model; `{}` retains the
session-model default. The metadata index is deterministic and bounded; it does
not rank entries against each new request. The complete indexes remain available
for discovery when the injected list omits entries.

The Harness panel lets the user choose the target layer before submitting a
rule request. Project shared configuration remains the default authoring target
for `/harness <request>`; personal and user-shared scopes require an explicit
choice in the panel.

### Advanced and compatibility commands

The compact panel and six primary command forms are the supported everyday
surface. Older forms remain available for scripts and recovery:

| Compatible command | Purpose |
| --- | --- |
| `/memory model [provider/model]` | Select a configured Memory worker model or set one directly |
| `/memory show` or `/memory status` | Inspect effective controls, storage, pipeline and backlog diagnostics |
| `/memory policy [memory\|harness\|agents] [apply\|propose\|off]` | Inspect or set one automatic phase policy |
| `/memory history [change-id]` | List private learning history or inspect one record |
| `/memory undo <change-id> [--yes]` | Restore one applied change after preview and conflict checks; headless use requires `--yes` |
| `/memory evaluate <suite.json>` | Compare supplied baseline and candidate rules without model calls |
| `/consolidate backfill` | Retry up to three eligible source-verified learning references; retain failures and costs without repeating task tools |

`/harness` compatibility flags remain accepted: `--local`/`-l` and
`--project-local` select project personal configuration; `--shared`,
`--project`, `--repo` and `-p` select project shared configuration; and
`--global`, `--user`, `--global-shared`, `--user-shared` and `-g` select user
shared configuration. The panel is preferred when a user needs to choose the
scope interactively.

## Harness layers

Four user-owned layers, nearest wins:

1. Project personal — `<project>/.pi/harness.local.json`
2. Project shared — `<project>/.pi/harness.json`
3. User, scoped to this project — `~/.pi/agent/harness/<scopeKey>.json`
4. User, shared — `~/.pi/agent/harness.json`

The scoped user layer reuses Memory's scope key, so a personal rule authored for
one project cannot silently govern another. It lives in a directory parallel to
`memory/` and never inside a Memory root: a Memory root admits only regular
`.md` children, so a JSON configuration beside them fails consolidation's
privacy validation and aborts the run. The all-projects layer is kept, so a
genuinely cross-project rule still applies everywhere.

## Harness rules

```json
{
  "rules": [
    {
      "id": "review-checklist",
      "skill": "review",
      "instructions": "For this review task, check the project's documented release constraints."
    },
    {
      "id": "project-a-status",
      "text": "Project A|A项目",
      "instructions": "When discussing Project A, use its confirmed replacement plan."
    },
    {
      "id": "confirm-publish",
      "bash": "\\bpnpm\\s+publish\\b",
      "action": "confirm",
      "message": "Confirm the package, version, and registry before publishing."
    }
  ]
}
```

`review` above is an example registered skill name, not a bundled skill. Use an
exact skill name available in the current session. Every rule has a stable `id`
and exactly one selector:

| Selector | Payload | Meaning |
| --- | --- | --- |
| `skill` | `instructions` | Guidance for that expanded `/skill:<name>` task |
| `text` | `instructions` | Guidance for subjects matching a regex in retained conversation |
| `bash` | `message`, optional `action` | Message with the real command result, or `confirm` / `block` before execution |

Omit `action` to allow a Bash call and append its message to the real result.
Empty strings, `null`, and `observe` are not actions. A block wins over confirmation;
multiple confirmation reasons produce one prompt. Missing UI, rejection, and
confirmation timeout leave the call unexecuted. Regex patterns inspect command
text, not an interpreted shell execution tree; verify both intended and unrelated
cases. Tests that might cause side effects use evaluator fixtures, not live commands.

### Configuration and ownership

User-owned layers, nearest last:

1. `<agent-dir>/harness.json` — user shared.
2. `<agent-dir>/harness/<scopeKey>.json` — user instructions scoped to the canonical project.
3. `<project>/.pi/harness.json` — project shared and default authoring target.
4. `<project>/.pi/harness.local.json` — explicit personal choice.

`<agent-dir>` defaults to `~/.pi/agent` and honors `PI_CODING_AGENT_DIR`.
There is no global `harness.local.json` or project `.pi/agent/harness*.json` layer.
A personal filename is not a guarantee of Git exclusion; check ignore settings.
Package defaults are the outermost layer.

The nearest declaration of an `id` replaces the whole rule. Different identities
remain independent. `{ "id": "example", "enabled": false }` disables an inherited
identity; a complete nearer definition can re-enable it. Invalid winning rules
are diagnosed rather than replaced with an outer same-id rule. An unreadable or
malformed layer is marked incomplete; any retained parse snapshot is labelled
stale, never verified as the current file.

Authoring reads the exact supplied file, assesses whether the request can be
represented, and writes a complete valid candidate once. Unsupported or ambiguous
requests leave files unchanged. Recommending AGENTS.md as a better home does not
authorize editing it. Existing invalid data requires an explicit native confirmation
preview before replacement; headless repair fails closed. If several layers need
repair, a strictly valid, approved target can be repaired independently while
unchanged other layers still have diagnostics. Activation remains incomplete and
Bash stays fail-closed where coverage is incomplete until those layers are fixed.
Approval binds the exact tool arguments and predecessor bytes across the entire
call, including any later policy confirmation. Target and other-layer raw bytes
are rechecked after the final asynchronous approval; changes require fresh
validation even when resolved diagnostics are identical. Execution policy is
resolved after asynchronous preflight and repair checks, so newly installed
protections govern the call. Recovery bypasses only incomplete coverage, never a
valid policy protecting configuration reads or writes.
The native `write` gate validates the whole candidate; `edit` is blocked for
Harness targets. This is not an OS sandbox or an interceptor for arbitrary shell writes.

Automatic learning writes only project-shared configuration. Evidence and
positive/negative evaluator cases are required. New identities cannot collide
with other layers, disabled declarations, invalid declarations, or manual rules.
`learnedRules` is parent-owned provenance binding each learned identity to its
current revision; a manual edit invalidates automatic ownership. Updates cannot
change the selector, re-enable a rule, or weaken its Bash action automatically.

### Guidance scope and delivery

A skill read is not an invocation. Skill guidance names the applicable skill task
in model-visible text. Text guidance names its matching condition and does not
turn a historical mention into permission to apply it to unrelated work.

At `before_agent_start`, text matching scans the current prompt plus retained
branch conversation: user and assistant text, visible tool results and string
arguments, and retained summaries. Thinking, metadata, excluded shell output,
abandoned history, and Harness's own messages are not matching sources.

Guidance is a persistent tail message, not a changing system prompt. Text
revisions already retained are not appended again. Delivery revisions include the
message format, so reload/resume appends one scoped replacement for an older
unscoped delivery. If compaction removed its original trigger, an outdated
delivery is retired once instead of injecting unrelated instructions; a later
matching task can reactivate it. Updates and retirements are new tail messages;
previous history stays in place for traceability and stable request prefixes. Incomplete scans
preserve previous delivery state. Guidance is prompt text, not a guarantee that
the model follows it.

Known limits: keywords first introduced by tools in the same run are picked up at
the next agent start. Synchronous regex evaluation has volume limits, not
preemptive cancellation of a single pathological pattern. Avoid unbounded patterns.
Configuration readback proves persistence only; report effective activation,
actual trigger verification, and unverified behavior separately.

### Transcript display

Harness authoring starts with one `[harness] started · <request>` row; the full
procedure stays in model context. Failed and incomplete events use error and warning
tones. Learning receipts retain failed/rejected/cancelled phases beside applied
changes, so a partial success never appears as an unqualified success.

Expanded policy rows keep the policy, action, outcome, tool, source and file;
check rows keep their phase, policy and artifact path. Reasons already shown in
the title and check statuses already shown in its label are not repeated as
fields. Guidance rows likewise carry the `[harness]` tag and show the skill or rule as
their title subject, with source, file and the complete prompt below, including prompts longer than 50
lines. Clipped titles wrap when expanded. This display-only cleanup does not
change enforcement, guidance delivery or stored event data.

### Existing configuration and safe upgrades

Installed `policies`, `disabled`, and `skillPrompts` remain supported runtime
input through a read-only compatibility boundary. A compatible old format is
reported as a notice, not unavailable configuration. In particular, a valid
write/edit-only policy does not block unrelated Bash commands after an upgrade.
Loading preserves every configuration byte. Existing cumulative `disabled` names
retain their historical same-ID effect, including saved flat rules, so upgrading
does not reactivate paused protections. Legacy same-name overrides of equivalent
built-in policies also keep their prior meaning.

New authoring and learning still produce flat `rules`. Adding them preserves
existing containers and provenance. Removing installed protections requires an
explicit before/after preview and authorization; old manual or learned entries
do not become automatically owned flat rules. No automatic migration is performed.

Legacy output/artifact checks, tool-argument paths and `require` gates retain
their original behavior. Legacy skill guidance retains its exact registered
invocation, optional user-message matcher, and configured system/user target.
These are compatibility capabilities, not new flat selectors. Mixed rules must
not bypass a matching block or create redundant approval prompts. Invalid
policies restrict only their identifiable tool/phase scope; unknowable scope or
unreadable configuration is conservatively diagnosed.

Built-in protection for futile interactive authentication and bulk Memory deletion
remains. A weaker Bash/text rule is never presented as an equivalent replacement
for an installed file or artifact policy. See the upgrade decision in
`docs/adr/0005-preserve-installed-harness-protections.md` in the source repository.

## Learning pipeline

With auto-memory enabled (the default), `agent_settled` runs a deterministic
zero-token evidence screen after queued continuations and retries finish.
The fallback selector chooses integer positions from a parent-frozen metadata
index and explicit phase flags. The parent resolves exact filenames and binds the
task digest; the worker does not transcribe artifact identity. Invalid positions,
duplicates, mixed identity fields and missing decisions fail closed. Existing
selection artifacts retain their original identity and validation contract.
These decisions select review inputs; they do not authorize mutations.

Routine tasks launch no learning model. A metadata-only selector chooses the
minimum sufficient existing Memory and relevant phases for the current Task
Slice. Selected bodies and task evidence form one authoritative Learning Dossier.
Only explicit full maintenance explores the whole corpus.
An empty Memory index plus explicit human facts or preferences lets automatic
learning route its already evidenced phases locally, without a selector model
call. An initial `/memory <request>` likewise goes straight to Memory planning.
The receipt marks this parent routing; planners and all validation still run.
Nonempty indexes and ambiguous inputs retain the metadata selector, and ordinary
manual `/consolidate` retains its reviewed routing.
When Jev is enabled and applying Memory is authorized, an uncertain new record
does not have to discard other independently verified knowledge. For a mixed
pure-create plan, the parent reviews every original candidate and their
relationships before applying an unchanged, independently usable subset.
Rewrites and deletions remain atomic. Held records and the complete original
proposal remain pending; partial learning is reported as partial, and verified
records are available for retrieval in subsequent tasks. These extra bounded
reviews retain their usage and cost; unavailable or uncertain proof grants no
additional writes.
Full maintenance also extracts grounded new knowledge when the Memory corpus is
empty. If the current session has no user or tool evidence, the parent may freeze one recent session
for the same canonical project (within seven days, at most 12 candidates and
8 MiB per source). Pi's active context projection excludes removed evidence;
older SDKs decline sources containing context edits. The receipt identifies the
source session and SHA-256 digest. This does not replay the backlog or change
automatic/incremental learning's current-task scope. With no usable evidence or
existing Memory, full maintenance makes zero model calls and reports
`no learning input`; use `/memory <request>` to supply knowledge directly.

Package-owned `prompts/*.md` protocols are bound through typed builders. Planners
are read-only, have resource discovery disabled, and return bounded deltas or a
no-op. The parent owns identity, evidence, privacy, path and source-hash checks,
mutation, rollback, indexes, and receipts. An assistant's success claim is not a
receipt. Later planning can overlap; mutation remains sequential. A later phase
failure does not undo an earlier verified phase.

Real user tasks are coalesced while learning runs; extension continuations do not
train themselves. Print/JSON sessions await completion and receipts. Turning
auto-memory off stops learning without disabling Memory retrieval. Receipts count
every selector/planner attempt, applied operations, duration, input/output tokens,
cache reads/writes, and provider cost availability.
Selector failures also retain a parent-generated diagnostic in the attempt;
raw model output and worker stderr are not copied into that diagnostic. A rejected
selector response is retained separately in its private run directory, bounded to
64,000 characters with the frozen context digest and a truncation flag.

An explicit `/consolidate` always reaches selection, including tasks without
automatic-screen keywords. Explicit continuation prompts retain the original
request and its evidence. Task slices preserve complete human and tool entries
within their byte budget, report omitted entries, and reject an oversized original request rather
than clipping evidence. Assistant context retains visible text and tool calls,
while excluding reasoning, signatures, and provider transport metadata.
A failed tool invocation followed by a successful check
is eligible for Memory review; the planner still must justify a durable lesson,
and a reviewed selector verdict is not overridden by that recovery alone. Harness evidence means Harness-owned transcript evidence: guardrail event
entries, Harness guidance delivery, and the notes Harness attaches to tool
results. Repository text that merely mentions policies or harness files is not
evidence, so it starts no planner.

The zero-token screen is an opportunity filter, not a completeness claim. It
can miss a lesson; when it starts no pipeline, the parent may store a bounded
backlog reference to the settled session slice. Failed learning also stays pending.
`/consolidate backfill` retries up to three eligible, source-verified references;
auto-learning can recover one eligible reference after a normal attempt. It never
repeats task tools. Individual acknowledgments preserve failed siblings, project
leases prevent duplicate concurrent learning, and attempt ledgers retain failures
and known usage. Automatic retries stop after three attempts with backoff; explicit
backfill still has a finite attempt cap. Missing or changed source stays unresolved.
An interrupted provider call without returned usage has unknown cost, not zero cost.
A latest phase with pending candidates cannot acknowledge its task as learned,
even if other candidates applied or that phase returned noop. Summaries warn and
show the latest unresolved count; a later completed phase supersedes its earlier
pending disposition. Source-verified backfill with an empty index uses the same
parent routing for explicit durable evidence as automatic learning, preserving all
mutation validation and semantic review.

Fresh tasks receive at most three complete relevant Memory bodies, each at most
4,000 characters and 8,000 characters for the complete reference block. Lexical
metadata ranking can miss useful entries; larger bodies remain on-demand reads.
Delivery records filename and revision, not proof that the model used or benefited
from the knowledge. Current evidence and instructions take precedence. Ordinary
correction planning revisits recently delivered entries; an explicit `/memory`
request retains its selected scope.

An automatically learned project Harness rule may be revised or retired only with
an exact predecessor revision, current user correction, positive/negative fixtures
and approval of the exact replacement by semantic review. A retired rule remains
as a disabled revision and in history. Manual or changed rules remain protected.

### Phase policies and history

All three automatic phases default to `apply`, preserving existing behavior.
`propose` validates and saves a private plan without changing learned files;
`off` skips that phase. For example, `/memory policy harness propose` leaves
automatic Memory and AGENTS.md behavior unchanged. Policies are stored in
`<agent-dir>/memory/settings.json` under `automaticPhases`, keyed by `memory`,
`harness` and `agents`. Explicit `/consolidate` and full maintenance still apply
validated current plans; the existing `agentsMd.disabled` setting remains
authoritative. AGENTS extraction is saved as a proposal if it would write to
a Memory or Harness phase configured to propose or off.

Incremental Memory planning and repair use the same exact proposal schema.
A bounded repair must preserve recognizable proposal names and selected
operations, including existing rewrite/delete intent; an empty replacement
cannot silently discard them. Failed repairs retain both rejection reasons in
bounded, sanitized private diagnostics. Representation validation permits at most
one structural correction, followed by at most one separate semantic correction
if complete review holds the accepted plan. Neither phase replans or loops. Each
correction keeps its own receipt usage and cost, and only the final accepted
attempt owns applied operations. Structural rejection metadata and screened
structural response remain available even if later semantic correction succeeds.
All original final validation and mutation gates remain mandatory.

Harness also permits one read-only repair when structured output is missing or
a parsed plan fails validation. It uses the original frozen evidence and model;
both worker attempts contribute to receipt usage, cost, and retry counts.
Identity mismatches, ambiguous plans, output bounds, and cancellation remain
terminal rejections.

Incremental Memory planners receive a parent-rendered JSON identity envelope;
models fill the delta without calculating or retyping snapshot hashes. The parent
still rejects any changed identity. Memory support questions retain each
candidate's parent-validated original citation indexes and exact quotes alongside
complete source entries. Quotes do not establish additional claims by themselves.
Harness counter-evidence windows check contradictions, narrowing and revocation;
lasting authority and matcher scope remain separate checks against the cited user
evidence. An irrelevant window need not repeat authorization. These changes retain
the existing probability, confidence, privacy and complete-evidence gates; they do
not establish that learning improves later tasks.
Source comments establish reported source reasoning, not independent proof of an
external defect. Planning and bounded repair distinguish that from observed
configuration/conditional behavior and avoid persisting historical test counts as
lasting guarantees.

For a new literal `addRule` only, a nonempty message that is a strict prefix of its
single validated original user quote may be completed to that exact quote before
semantic review. Only display wording changes. Corrections, updates, complex
matchers, multiple citations and sensitive text are excluded. Both pre-completion
and completed plans are retained privately; the completed actual candidate is
revalidated and passes the same authorization, scope, privacy and complete
counter-evidence checks before application. The exact-quote wording check grants
no execution authority.

The opt-in real continuous-project study gives both arms the same experimental
parent tool cap: eighteen admitted calls, followed by an empty active tool set.
Excess calls already in a batch are blocked and counted as task failures. Original
observations remain in the same session; independent learning workers and semantic
review are unchanged. The standalone version-execution instruction is scoped to correction/retirement
tasks: both orientation models had interpreted a conditional shared instruction
as an immediate request, so that earlier cohort remains a distinct protocol.
Earlier prompt-only-budget cohorts and their failures/costs
remain separate evidence because this changes the experimental protocol. This
study cap is not a production default or an automatically learned project rule.
Correction/retirement tasks must also produce a successful standalone version
probe in the real model session. An attempted call or a post-learning rule-engine
decision does not establish that the task actually executed its requested probe.

Settings are strictly schema- and path-validated. A missing settings file keeps
automatic learning enabled; malformed, unknown, unsafe, or unreadable settings
disable learning and show a repair diagnostic instead of silently using defaults.
The learning backlog is a private, scoped reference index: its JSONL file is
capped at 4 MiB, each record at 4 KiB, and a full file rejects new entries
without silently deleting older ones. New records carry the project scope key
and use a scope-specific cursor. Legacy records require a bounded session-header
scope check; the historical global cursor is consulted only for those legacy
records and never consumes a scoped record. Unscoped or malformed records are
reported. Appends and cursor updates share a private process lock; contention
refuses the write without delaying the user task, and cursors cannot decrease.
Backlog inspection is status-only; `/consolidate backfill` retries bounded
learning work from verified original evidence and does not replay task tools. Full state
checks validate settings, backlog limits, scope binding, malformed references,
and cursor updates before status is shown.

Applied mutations and proposals are recorded privately under
`<agent-dir>/memory/history/<escaped-canonical-cwd>/`. History includes exact
before/after bytes, including indexes and mirror repairs. New pipelines attach an
exact parent-owned batch identity; the native Recent learning menu groups these
records and distinguishes index setup from learned knowledge. One learning can
therefore create several file-change records. Older records stay individually
accessible, and undo still previews and confirms one exact change at a time;
there is no batch mutation or grouping inferred from timestamps. `/memory history`
lists the latest 50 records; passing an id shows a bounded preview. Proposal
records are inspection artifacts; running `/consolidate` creates a fresh plan
against current evidence instead of replaying a stale proposal.

`/memory evaluate` reads the suite path explicitly supplied by the user, relative
to the project or absolute, using a bounded regular-file read. It performs no
model calls and does not change learned files.

Undo requires all affected files to match the recorded successor, validates
project scope and Memory privacy, and runs under the consolidation lock. It
refuses later edits, symlinks and invalid records. TUI use confirms a concrete
preview; headless use requires the id and `--yes`. Interrupted undo is recovered
to the applied state on the next learning session, unless an unrelated edit
requires inspection. Pending records from failed mutations cannot be undone.
If an interrupted mutation leaves bytes or permissions different from its recorded
predecessors, subsequent learning stops with a history id for inspection. Existing
AGENTS.md transaction recovery runs first. Reconcile these files to their exact
predecessors after review to resume; the incomplete record becomes `abandoned`.
Unknown current bytes are never automatically attributed to learning or overwritten.
History rejects detected credentials in proposals and file snapshots, matching
assigned values and provider key formats rather than ordinary prose, wiki links
or workflow permission names. A refused snapshot names the learned surface to
clean without echoing the matched bytes. Completed runs keep their run directory
(identity, task, plan, receipts, snapshot) for inspection, like a failed run keeps
its diagnostics.
Older changes made before history was installed have no undo record.

### Independent learning evaluation

`/memory evaluate examples/learning-evaluation.json` compares embedded baseline
and candidate Harness configurations against user-authored held-out cases.
The report includes accuracy, false blocks, missed protections, regressions and
configuration/suite digests. Cases support Bash decisions and skill/text matches.
No commands or models execute. These cases are independent of a planner's own
validation examples; passing them measures the configured rules, not model quality.

For an explicit paired model-task experiment, run from this package directory:

```bash
uv run --no-project scripts/evaluate-learning.py examples/learning-task-evaluation.json --validate
uv run --no-project scripts/evaluate-learning.py examples/learning-task-evaluation.json --model <provider/model> --output /tmp/learning-evaluation.json
```

Each task runs once per arm in a fresh disposable Git project with supplied Memory
snapshots, automatic learning disabled, and only the read tool. Authentication
and model configuration are frozen in one private snapshot for the whole suite;
each task receives a separate copy so runtime refreshes stay isolated.
The report includes literal-answer success, regressions, latency and observed
token usage/cost; missing prices remain unavailable. Output files are private and
never overwritten. Without `--model`, the configured `memory.json` model is used.
The included synthetic example verifies exact answer scoring and native Memory
body-read evidence; use representative held-out tasks for your project. One
paired sample per task does not establish statistical or causal improvement,
learning-pipeline persistence, or Bash enforcement.

## Verifying it is actually effective

One question the rest of this package's verification deliberately does not ask,
because it is not a plumbing question:

```bash
python3 packages/continual-learning/tests/live_effectiveness.py
```

- **Does persisted Memory change behaviour?** Held-out tasks run once with no
  Memory and once with it. Candidate cases require a successful native `read`
  result containing a marker from the Memory body. This is bounded paired
  evidence, not a statistical or causal claim about learning generally. The
  suite is `examples/learning-effectiveness.json`.


The suite is committed rather than generated so the tasks are held out of the
corpus they test. It uses the model configured in `memory.json`.

## Memory

Exactly two roots participate:

- Complete canonical private root: `<agent-dir>/memory/<escaped-canonical-cwd>/`.
- Safe Git-trackable mirror: `<canonical Git project root>/.memory/`.

The project mirror is enabled only at the canonical Git root. There is no
project-local private Memory root. Safe entries synchronize byte-identically;
private entries exist only in the private root and are marked `(harness only)`
in its `MEMORY.md`. Preferences stay private; credentials and secrets are never
stored, including in private files or evidence.

The root name uses Pi's flat path escaping: strip the leading slash, replace
separators and colons with `-`, and wrap with `--`. Names beyond 240 bytes fail
explicitly; no hash fallback exists. Paths with the same escaped name share the
root, lock and run storage. Obsolete roots are neither discovered nor migrated.

Before planning, newer-mtime-wins drift normalization synchronizes safe entries;
ties prefer the private copy. First adoption can import committed shared Memory
when the private root is absent. Privacy leaks and public orphans are removed
under the existing parent-owned validation contract.

### Retrieval and descriptions

The default index injection budget is 6,000 characters. Separately, task relevance
can deliver up to three complete Memory bodies: at most 4,000 characters each
and 8,000 characters total including framing. Compound API names remain
searchable, and generic instruction words do not earn relevance. Bodies that
cannot fit completely stay available through their delivered read paths; claims
and conditions are never cut into arbitrary excerpts. Each injected body records
its exact SHA-256 revision. Delivery proves exposure, not correct use or benefit.

Each body root is declared once and every entry row names its filename, so the
budget reaches relevance metadata instead of repeating an absolute read path per
entry. New descriptions should front-load a concise evidence-backed fact or
preference, naming its subject and applicable project/context, in one line of at
most 120 characters. A bare relevance trigger is insufficient: preserve material
conditions and exceptions in the summarized claim, with full detail in the body.
Existing longer descriptions
are retained when they fit, or shortened with a single-line marker rather than
silently losing a late trigger. Under budget pressure every listed entry stays
reachable and cues give way before entries do.

The loader reports unique entry counts and file-read omissions; final formatting
reports budget omissions. Discovery pointers name `MEMORY.md` and exact roots
for bounded reads/listing. Indexes are discovery metadata and can be stale;
individual bounded files remain the authority. Parent rebuilds include descriptions
in complete indexes. Loading memory never writes indexes. All retrieved content
is explicitly untrusted reference data, not instructions.

Loading runs on every user turn, so it avoids repeat work without weakening its
checks: the read buffer is sized from the file rather than from the byte bound,
unchanged entry metadata is reused in-process while its device, inode, size,
mtime, and ctime still match a regular non-symlink file, the root identity is
re-verified for every real read and for the batch, and the `git` root probe is
memoized per canonical project path within a bounded window. A rewritten,
replaced, or symlinked entry is always read again or dropped, never served from
reuse.

Only strict `[A-Za-z0-9][A-Za-z0-9_-]*.md` basenames are entries; `MEMORY.md` is
metadata. Symlinks, non-regular files, escapes, and root replacement are rejected.
Index rows use the Markdown link target as their identity, regardless of display
label; a row without a valid link can start with a bare filename. Filenames in
ordinary descriptive prose do not introduce entries. Privacy, planning, menus,
undo, and final validation use this same grammar.
New Memory cites exact indexed user/tool-result evidence and cannot overwrite
existing names. Deletes require a contradicted, superseded, or subsumed verdict
plus a mechanically verifiable `preservedIn` target.

## AGENTS.md consolidation

A read-only planner proposes at most five small evidence-cited operations against
project-root AGENTS.md: rewrite, remove, add, or extract. Indexed quotes must match
user/tool-result content; assistant text and metadata do not count. New units
require two distinct evidence entries. The parent simulates exact anchors and
byte budgets before applying changes.

Common constraints and short task-to-document pointers remain always loaded.
Detailed durable knowledge need not be relevant to every task: it can move to
Memory. Registered skill-specific instructions can become a flat skill rule.
An extraction can retain a bounded single-line `replacementText` pointer; it
participates in the same evidence, anchor, size, fingerprint and rollback checks.
A lack of use in one task is not evidence that an instruction is obsolete.

Memory, Harness, AGENTS.md, and receipts participate in one extraction transaction.
A pre-receipt records exact predecessors before mutation; startup recovers an
interrupted transaction only after verifying the canonical scope. User-level
instruction files are never automatic targets. Configure the agent-global phase
in `<agent-dir>/memory/settings.json`:

```json
{ "autoMemory": true, "agentsMd": { "budgetBytes": 16384 } }
```

`agentsMd.disabled: true` skips that phase. At or above budget, changes are
zero-sum rather than mandatory expansion. Empty validated plans are successful no-ops.

## Development verification

```bash
python3 -m pytest packages/continual-learning/tests/ -q
pnpm typecheck
pnpm --dir packages/continual-learning pack --dry-run
pnpm check:install
uv run --no-project packages/continual-learning/tests/live_meaningful_details.py
uv run --no-project packages/continual-learning/tests/live_learning_loop.py
python3 packages/continual-learning/tests/live_smoke.py
python3 packages/continual-learning/tests/live_manual_memory.py
python3 packages/continual-learning/tests/live_manual_harness.py
python3 packages/continual-learning/tests/live_upgrade_smoke.py
python3 packages/continual-learning/tests/live_design_e2e.py
python3 packages/continual-learning/tests/live_harness_learning.py
python3 packages/continual-learning/tests/live_effectiveness.py
python3 packages/continual-learning/tests/live_private_preference.py
python3 packages/continual-learning/tests/live_full_consolidate.py
```

The explicit [Docker project experiment](tests/docker/README.md) runs real Pi
against pinned Click, p-limit, and mitt checkouts with fresh learning storage,
independent project tests, and new-session Memory/Harness verification.

The display smoke runs real Pi print and interactive sessions with an offline
scripted provider and disposable roots, without user credentials or network
requests. It verifies Ctrl+O, narrow-terminal wrapping and complete guidance
readback. The live scripts are not collected by pytest.

The offline learning-loop smoke runs real Pi child processes against a loopback
scripted provider. It checks persisted Memory and learned project Harness rules,
parent receipts, future-session index injection and bounded body reads, and actual Bash block/allow behavior
with automatic learning disabled in that future session. Every storage root is
disposable and no provider credentials are copied. This verifies the mechanism;
it does not measure a real model's learning quality.

The learning smoke reuses configured model/auth in disposable project and agent
roots. It checks a new private preference, a shared project fact, an existing
Memory rewrite, a learned project rule, an AGENTS.md correction, and parent
receipts. It rejects private-marker leakage into shared indexes, Memory bodies,
Harness, or AGENTS.md. A fresh session must read the exact persisted entries,
use their knowledge, block the prohibited Bash call, and execute the allowed
call. A separate check verifies scoped guidance with a harmless Bash command.
It never replaces failed learning with fixtures or edits real user configuration.
The manual-memory smoke drives the native TUI `/memory <request>` path with the
configured real model, waits for the parent receipt, verifies safe and
private Memory separation plus unchanged AGENTS.md and Harness bytes, and then
uses a fresh print session to read the saved project fact. It copies
authentication into disposable private roots and is optional because it may
consume provider quota.
The manual-Harness smoke checks the native `/harness <request>` path: a successful
read of the complete original configuration precedes exactly one complete JSON
write, existing rules and other layers remain intact, and a fresh session verifies
real blocked and allowed Bash
calls. The design probes require successful observations, corrected final output,
and genuine pending-mutation handling. Direct Bun probes also override the agent
directory, so history and recovery checks cannot write to ambient user Memory.

The repeated Harness measurement requires both executable cases and valid
parent-owned rule revisions. The three-task paired Memory evaluation checks
retrieval with native body reads; its fixture results do not establish general
learning gains. The private-preference regression runs automatic Memory in two
fresh roots, requiring the private preference alongside new shared knowledge and
an existing-entry correction. The exact private preference proposal, frozen
snapshot and post receipt must bind to the same applied plan; the automatic
receipt permits only selector and Memory attempts. Other phases are disabled for
that focused check.
These checks spend configured-provider tokens. The native full-command
smoke uses a deterministic loopback provider to check `/consolidate full`, a bound
current-session snapshot, the entire two-entry corpus and selector bypass;
Memory and Harness must finish with verified no-ops in that focused command
check; the AGENTS phase is disabled.

The separate upgrade smoke starts a real Pi process with a disposable old-format
configuration, confirms harmless Bash and unrelated writes execute, and confirms
protected write/batched-edit calls remain blocked while configuration bytes stay
unchanged. The learning and upgrade scripts copy provider credentials into
private temporary roots rather than link to writable user files.

## License

MIT

Real-provider cold-start and repeat verification: `python3 packages/continual-learning/tests/live_full_learning.py` (disposable project and agent directories).

### Optional Jev judgments

Jev is optional. It is enabled by a `jev` section in `~/.pi/agent/continual-learning.json` (or your configured agent directory), **or** by `TYPESAFE_API_KEY` in the parent Pi environment. A key alone uses pinned `jev-1.13.0` and all three semantic stages. No separate `jev.json` is required. Example unified configuration:

```json
{"jev":{"model":"jev-1.13.0","scopes":["selection","memory","harness"],"allowPrivateMemory":false}}
```

The model and scopes are optional overrides; `"jev": true` or `"jev": {}` opts in with defaults. Authentication uses `TYPESAFE_API_KEY` or the section's optional `apiKey`; prefer the environment so credentials stay out of configuration files. `"jev": false` or `"jev":{"enabled":false}` explicitly disables Jev even when the environment key is present. Other unified configuration sections are ignored by this reader and never modified. Invalid, oversized or symlinked configuration disables the feature with a diagnosis.

For one exactly recognized finite Git push matcher, code supplies the proven matching language to scope and complete counterevidence questions. Support still receives the original candidate. Unknown, disabled and non-add rules retain the original path; this syntax proof never supplies authorization or lowers a decision threshold. Fixed real cited-path and heldout comparisons reduced supported-candidate holds (6→3 and 8→5), with zero unsafe accepts in those samples; full-workflow superiority remains unverified. See @tests/jev-cited-followup-evaluation.md. Later R9 full-workflow results remained off 1/3 and on 0/3. A separate finite-authority experiment worsened new-sample holds and was not adopted. Planner proposals now include bounded parent-root cd-wrapper coverage when shell spelling is safe; existing rules are not rewritten and unknown regexes retain general Jev judgment.

For a new blocking rule exactly matching the canonical project push template, the parent supplies its frozen directory/run/scope/evidence binding. Code proves matching syntax; Jev still independently checks lasting user authorization, argument scope and every original counterevidence window. Missing or mismatched bindings, edits to existing rules and confirmation rules keep the general path. The original confidence thresholds and write permissions are unchanged. Fixed V2 real development and previously unqueried heldout samples reduced valid-rule holds (8→0 and 8→4), with zero unsafe accepts among sixteen negative plans per split. Each split contains twelve English/Chinese scenario pairs. Four heldout valid restrictions remained uncertain; this is bounded semantic evidence, not proof of full-workflow superiority. See @tests/jev-cited-followup-evaluation.md.

Complete new-Memory reviews can expose an internal `candidateReview` observation bound to evidence, existing Memory, and candidate digests. It lists each original check as passed or held. This is diagnostic only: it does not establish independence between new candidates or permit partial writes. Incomplete requests, changed inputs, and legacy plans produce no observation; whole-plan holds remain in force.

Memory generation and the existing single semantic-repair attempt now ask for relevant original citations for each body and description claim. Future-task intent alone does not establish verified current state; verification/configuration claims need their actual supporting observations. Later corrections and exceptions remain relevant, and unrelated entries are not attached automatically. Original quote, privacy, retained-identity and full-plan Jev checks still decide application. A read-only original-judge citation study improved known development from 15/16 to 16/16 and fresh heldout from 15/24 to 23/24, with zero unsafe accepts in either arm; these public synthetic results do not prove the production prompt or full workflow improves. The six real isolated Pi/Docker follow-ups finished: Jev off passed 2/3 and on passed 1/3. This did not establish workflow improvement: one on plan contained an unsupported extra claim, valid knowledge and canonical Harness rules were also held, and one off run lacked a real prohibited-command attempt. See @tests/jev-citation-guidance-r14-final-results.json. See @tests/jev-citation-repair-adoption-decision.json and @tests/jev-citation-guidance-r14-docker-manifest.json.

Scopes grant participation in semantic stages, never file-write permission. Omit a stage from `scopes` to retain its legacy behavior. Pin a version for reproducibility; `jev-latest` and `jev-preview` are accepted, with the actual returned version recorded. `/memory status` reports effective model, scopes and credential availability without revealing the key. There is no `/jev` command, and command syntax and phase permissions are unchanged.

Enabling a scope sends bounded frozen task evidence and permitted Memory content to TypeSafe. Private Memory metadata, bodies and candidates require the separate `allowPrivateMemory` permission; absent permission falls back in selection and preserves candidates as proposals. This never changes storage classification. Recognized credentials prevent a request. Existing privacy checks still govern every write.

The integration uses `@typesafe-ai/sdk` 0.6.0. Independent Noul questions detect durable knowledge and lasting behavioral constraints; both can apply. Score questions rank metadata in the same request; selection uses the probability mass across both relevant levels, so ambiguity between two acceptable levels does not itself force fallback. Memory bodies are read only after selection. Empty-index explicit evidence keeps its local route with no semantic selector request. Disabled, missing-key, uncertain or failed selection uses the existing selector; explicit `/memory <request>` always retains Memory processing and excludes Harness and AGENTS.md.

After parent structure, identity and frozen-quote validation, another batch checks candidate support using the knowledge body or rule rather than administrative frontmatter/evidence bookkeeping (while scanning the full original candidate for credentials). For fully cited new Memory, the support question includes only the complete knowledge body; filenames and write/storage metadata cannot become claims requiring user evidence. Rewrite/delete/mixed batches retain the complete preservation context. This batch also checks Memory grounding and relationships against already-read bodies (Choice), and general Harness scope (Choice). For an absolute-end anchored literal block or confirmation rule, parent code proves the exact command matcher and Jev separately checks lasting user authorization and message fidelity. A confirmation rule requires the real native Allow once or Block decision for each invocation; a one-time grant cannot revoke future confirmation, and confirmation cannot weaken an unconditional ban. Plain `$`, whitespace classes and operators never qualify for that proof. Duplicates, conflicts, unsupported or uncertain candidates become proposals; an unavailable candidate judge also produces proposals. For a proved literal/family rule whose message is byte-identical to its validated original user quote, code proves wording equality and omits only the paraphrase judgment. Authorization, matcher scope, complete counterevidence and parent write checks remain mandatory; changed messages still require semantic verification. In the proved ASCII command-family grammar, literal TAB and its regex escape have identical meaning. Counterevidence review receives the exact code-proved command range, block action and original explanation; unproved regexes retain full matching review. Generated fixtures and rule identifiers do not establish user permission. No Jev answer permits a write by itself or disables existing Harness rules. Legal requests have at most 32 questions and 64,000 wire bytes, with at most four requests running concurrently. For quoted new Memory candidates and parent-validated Harness citations, support uses the complete cited entries and existing bodies; a separate counterevidence review covers **every** indexed original entry in windows targeting 20,000 bytes; a larger complete entry occupies its own window and must still fit the unchanged complete-request wire limit. Entries are never truncated or summarized. Every review also receives the original cited support to interpret meaning and scope; later corrections still override that support. There are at most sixteen windows and 68 logical requests, including split support requests (up to four batches per job); the existing connection-only retry permits at most 136 transport attempts. Windows are never merged based only on raw entry bytes. If a cited support entry is also in the current review window, supportEvidence.reviewEntryIndexes points to that exact original entry instead of transmitting it twice; the complete cited context remains present across both fields. All original evidence and all planned requests are checked for sensitive material and bounds and copied before the first transport. Only fully successful windows count toward coverage, and any failed, uncertain or conflicting judgment holds the entire plan. Rewrite/delete/mixed Memory plans and uncited legacy inputs retain full-evidence transport with at most four batches. This is a wire-byte cap, not a token count; API context failures remain proposals rather than discarding possible later contradictions. A batch is atomic for this policy: one questionable candidate holds the whole plan for review. Supported supplements can be applied only under the existing apply policy. Full maintenance also checks its validated candidates; too much evidence falls back to proposals.

Requests are limited to 64,000 serialized UTF-8 wire bytes and 32 questions; cited evidence windows prefer 20,000 bytes. Oversized evidence is not silently truncated: selection falls back, candidates become proposals. Requests default to a 15-second timeout, honor explicit shorter deadlines, use zero SDK retries and at most one connection-only retry, propagate cancellation and disable SDK body logging. Starting thresholds are Noul ≤0.1 / ≥0.9. Memory relation acceptance uses P(unrelated or supplement) ≥0.9; general Harness scope uses P(same or narrower) ≥0.9. Ambiguity between these compatible classes is acceptable; this does not require high confidence in one class. Memory grounding, literal-command authorization and message fidelity require confidence ≥0.8 and winning probability ≥0.9. Harness review includes parent-validated blocked/allowed examples, with frozen evidence remaining the sole source of authorization. Metadata uses P(level 2 or 3) ≥0.9 to select and ≤0.1 to omit on a 0–3 rubric; intermediate probability falls back. These are conservative policy parameters, **not calibrated accuracy claims**. Validate them on your workload before relying on the integration, especially for Chinese.

For an apply-policy Harness plan or incremental Memory plan, an unsupported or uncertain semantic hold may use the existing single read-only repair slot, shared with structural repair. With Jev enabled, the first incremental Memory structural repair also receives the original hash-checked snapshot and selected Memory dossier; it must not turn one-task instructions into lasting preferences. Both files are rechecked after repair, valid original privacy classifications must remain unchanged, and a rejected completed call still retains its usage. This does not add a second repair slot or relax subsequent validation. Memory correction uses frozen evidence and already-read bodies, preserves names, intents and privacy classifications, and retains the original proposal if correction remains held. Duplicate, conflict and service failure do not trigger another correction. A semantic Harness repair may omit unsupported operations, but their exact original evidence is reindexed and saved as private pending proposals. Semantic repair receives an explicit table of the original operation kind, rule identity and complete evidence objects. Retained rule identities and all citation properties must stay unchanged apart from operation indexes; an empty or replacement repair retains the original proposal. Repaired candidates repeat parent validation and Jev judgment; service failures do not cause retries, and unresolved candidates remain proposals. Frozen evidence is checked after each judgment and again in the mutation queue before writing. A direct apply cannot bypass a semantic proposal. Memory index descriptions receive independent support, existing-Memory relationship and full-evidence checks alongside the original body checks. A duplicate description can accompany a body that adds supported knowledge; duplicate bodies and conflicting descriptions remain proposals. All additional questions fit the existing request limits before any call; budget exhaustion retains a proposal.

Receipts show directions, selected filenames, phase outcomes, controlled fallback/proposal reasons, Jev latency, actual model version and returned tokens. Cited judgments also report complete reviewed entries and windows; coverage does not itself establish semantic accuracy. `estimatedCostUsd` uses the published `jev-1.13.0` input-token tariff; it is separate from worker totals and is not an invoice. Failed requests without usage have unknown cost. Multi-request failures retain known input/cost lower bounds and completed request counts without claiming a complete total. A held judgment may identify a controlled candidate index, judgment dimension and optional `field: "description"` to explain correction; it does not include candidate text. After complete responses, `candidateFailures` records the first failure on each held candidate and supplies bounded repair hints; it never grants partial application permission. Complete counterevidence failures additionally report a zero-based evidence window and inclusive original entry range; the range is captured before transport and shown in bounded repair hints. Missing, cancelled or inconsistent responses never infer a failure window from coverage. Persisted location fields are rendered only as validated nonnegative safe integers, with no evidence text. Incomplete service responses do not produce this list. Parent Harness rejections report fixed validation categories and counts. Rejected semantic repairs distinguish identity, citation, structure and omitted-plan validation mismatches without revealing their content. A service failure may include `httpStatus` (400–599) from the first failed SDK request; multi-request receipts keep that status without treating partial responses as acceptance. It does not reveal error bodies, headers or the request URL. Sensitive evidence, SDK error text and raw responses are not added to the receipt.

Official references: [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript), [primitives](https://docs.typesafe.ai/primitives), [models and limits](https://docs.typesafe.ai/models), [confidence](https://docs.typesafe.ai/confidence), [known model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

`bun packages/continual-learning/tests/evaluate_jev.ts` evaluates the fixed bilingual corpus's deterministic baseline offline. `--live` makes paid Jev requests and requires prior authorization of credentials, model and cost limits. It compares the parent screen and code-valid candidates against semantic judgments, **not** the legacy LLM selector or a complete learning workflow. Mock regression results prove boundaries, not model accuracy. See @tests/jev-evaluation.md and @tests/jev-cited-evidence-evaluation.md and @tests/jev-cited-followup-evaluation.md for measured evidence and limitations.

Real native Pi workflow evidence (generation, parent application, fresh Memory reads, exact blocked/allowed tool probes and repeat stability) is recorded separately in @tests/jev-workflow-evaluation.md. Its runner reports individual effects; use `--require-effects` to fail the run unless every recorded effect succeeds. `evaluate_jev.ts --live --fresh-acceptance --require-improvement` requires complete real inference, fewer unsafe candidate accepts and no additional supported-candidate holds on that fixed corpus. This candidate gate alone does not establish end-to-end improvement.

The subsequent bounded improvement acceptance, including real bilingual judgments and native effects with failures retained, is documented in @tests/jev-improvement-evaluation.md.

Full-workflow improvement uses the stricter `live_jev_workflow.py --require-improvement` paired-effects gate. Equal capability does not pass. The overall status and current remaining work are in @tests/jev-workflow-strict-evaluation.md.


The latest fixed four-case native workflow cohort improved 36/50 effects to
50/50, with fourteen gains and zero regressions. This is an iterated public
synthetic benchmark; costs increased and earlier failed trials remain visible.
It does not establish superiority on every project or model call. See
@tests/jev-workflow-strict-evaluation.md for exact native, offline and real
inference evidence, fees, rejected trials and reproduction.

Expanded real bilingual and isolated Docker verification is documented in @tests/jev-expanded-evaluation.md.
Read-only frozen-input design comparisons and the remaining evidence-coverage requirements are documented in @tests/jev-learning-design-reflection.md.

The subsequent R15 original Docker cohort finished off 2/3 and on 0/3; one off-arm setup failed at GitHub DNS. Jev-enabled first structural Memory repair never triggered, so that increment still lacks real trigger coverage. A separate 96-request Harness citation-anchor study increased valid holds from 1 to 2 on completed cases, with one timeout in each arm, and was rejected. These results do not establish overall Jev improvement. See @tests/jev-structural-context-r15-final-results.json and @tests/jev-harness-citation-anchor-adoption-decision.json.

The focused R16 p-limit pair finished off 1/1 and on 0/1. The on arm passed its independent project test and applied Harness, but Jev timed out on Memory and retained both candidates as a proposal. No semantic Harness repair triggered, so the new binding prompt has no real effect evidence yet. Recorded Jev costs remain partial lower bounds. See @tests/jev-harness-bindings-r16-final-results.json.

The same-original-input native Docker repair comparison then reproduced citation-property loss in the baseline (4/5 original properties), while the binding prompt preserved all 5/5 and unchanged pattern/action/scope/permissions. Both original outputs were retained and independently checked. The improved candidate still became a proposal: all three real Jev requests timed out at the unchanged five-second budget, with zero completed semantic judgments and unknown Jev usage. This is one known-input generator observation, not heldout or overall Jev improvement. See @tests/jev-harness-binding-original-real-results.json and @tests/jev-harness-binding-original-independent-review.json.

A subsequent 96-request real Jev deadline comparison used the same known 24-case English/Chinese corpus and exact paired request bodies. Five- and fifteen-second budgets both completed 24/24, with zero unsafe accepts and the same one valid candidate held for authority uncertainty. Longer deadlines were not adopted; the production default remains five seconds. All 96 responses verified Jev 1.13, with 71,564 input tokens and approximately $0.003005688 estimated cost, excluding unverified account billing. This direct SDK small-corpus result does not explain the earlier Docker/large-evidence timeout. See @tests/jev-deadline-real-results.json and @tests/jev-deadline-adoption-decision.json.

A same-host large-original-input diagnostic completed all twelve Jev requests across direct/forwarded and five/fifteen-second arms. Every arm covered all seventeen entries and both counter windows, but all retained the candidate for uncertainty. This run did not reproduce the historical timeout or justify increasing the default deadline. See @tests/jev-original-transport-real-results.json and @tests/jev-original-transport-adoption-decision.json.

A later real continuous-project cohort retained a different frozen request whose connection retry returned HTTP 200 in 6.872 seconds, beyond the five-second default, and the SDK held the Memory repair for timeout. That observed deadline mismatch motivated the current bounded fifteen-second default; the historical unsuccessful diagnostics above remain unchanged. Explicit deadlines, cancellation, connection-only retry bounds and all semantic thresholds remain. Deadline recovery does not establish that a candidate is grounded or that later tasks improve. A subsequent frozen continuous cohort completed all thirteen Jev responses, including two beyond five seconds, but still learned no Memory or Harness changes: semantic holds remained, and its single explicit backfill failed the selector schema. Those failures and costs remain in the study; no downstream effectiveness claim follows.

The original generator used literal tabs in the exact parent-bound project push template. Matching proof now recognizes those tabs and escaped tabs as equivalent spelling, without rewriting the rule or accepting other regex changes. All existing authority, argument-scope, explanation, privacy and full counterevidence checks remain. A subsequent three-request real replay of the same candidate and snapshot allowed the candidate, with full coverage, Jev 1.13, 1.725 seconds and approximately $0.000726558 estimated cost. This is one known-input observation compared with preserved earlier results, not randomized, heldout or full-workflow superiority. See @tests/jev-template-tab-original-real-results.json.


The R17 six-arm isolated Docker cohort preserved the original tasks and gates:
Jev off passed 2/3, Jev on passed 0/3. The mitt off arm failed dependency setup
before inference. All three on arms lacked an accepted Memory judgment; p-limit
and mitt applied Harness, but their early Memory gate stopped fresh recall and
native enforcement checks. Click had an unavailable Memory repair request and a
Harness timeout; p-limit and mitt had complete semantic requests with uncertainty.
There were 153 provider requests (127 main, 26 Jev), with usage recorded for 25 Jev
responses. Client-known Jev cost is approximately $0.00752451 and known main
learning-phase cost $0.054289022; both are lower bounds, not a bill. Proxy usage
is overlapping evidence and must not be added to client usage. All six owned
containers and five recorded continuation process groups stopped; the unrelated
container was preserved. Source and image hashes remained frozen. The initial
orchestrator cleanup-case failure is retained separately from the successful
Click off workflow. See @tests/jev-template-tab-r17-final-results.json.

Source review found additional task-result claims in Click and a mix of stable
configuration and single-run lint history in p-limit. These findings do not label
all uncertain judgments as false holds. The next prospective repair study compares
retaining stable facts in the same original candidate against the current prompt,
while explicitly testing knowledge loss, requested historical results, privacy and
exceptions. It is planned, not executed or adopted. The batch remains atomic. See
@tests/jev-durable-core-research-plan.json.

Research acceptance is governed by @tests/jev-learning-quality-charter.md: reliable useful learning and preserved constraints, not a higher Jev allow rate. New phase-effect observations and unseen-project evaluation must be frozen separately; original cohort results remain unchanged. No positive outcome is required, and Jev stays optional with the existing default.


New project-study reports carry `effectObservationVersion: 1` and separately
record `phaseObservations` for Memory, recall and Harness. A failed Memory gate
skips dependent recall but no longer masks a safe native Harness probe; a failed
recall also no longer masks Harness. All original acceptance assertions remain,
and any failed effect still fails the workflow. Stable failure-check IDs preserve
diagnostics without serializing arbitrary exception text. Auto-learning is disabled
before these probes. Historical reports are unchanged; observation and cost coverage
differs from the earlier early-exit protocol and must not be compared as equivalent.
Offline control-flow and network-disabled Linux evidence verifies scheduling and a
local wrapper, not real-model learning gains or new native Pi hook coverage. See
@tests/jev-independent-effect-linux-results.json and
@tests/jev-independent-effect-assertion-preservation.json.


The bounded durable-core generator pilot now freezes 16 synthetic English/Chinese
samples representing eight scenarios, with 32 independently isolated before/after
arms and at most 128 provider requests. These are authored development scenarios,
not heldout projects or human gold labels. Both arms receive identical frozen
retention requirements; only the after arm appends the bounded clarification.
Original candidate identity, privacy, frontmatter and quote/index pairs must pass
code checks before Jev evaluates full evidence. Outputs are never applied.
The stricter research citation guard does not change production behavior.
Thirty-two network-disabled preflights passed without model calls. A real local
SIGTERM probe verified owned process/container cleanup for the final runner.
Missing, partial or multiply requested main-model usage and incomplete Jev usage
remain unknown rather than zero cost. The paid pilot completed all 32 arms: 80 provider requests (32 main, 48 Jev),
zero timeouts, missing-usage arms or production writes. Actual Jev was 1.13;
known client estimates total $0.043907326, without adding overlapping proxy
usage or claiming verified billing. Independent model review observed complete
knowledge in 14/16 samples in both arms, history noise in 7 versus 2, and a new
requested-history context omission. Two transient-only candidates remained
unsuitable for lasting memory in both arms. Jev allow increased from 11 to 13,
but this does not establish net learning benefit. The clarification was not
adopted; Jev remains optional with its existing default. No heldout project or
actual learning/recall effect was tested here. See @tests/jev-durable-core-generator-manifest.json,
@tests/jev-durable-core-generator-prepaid-review.json and
@tests/jev-durable-core-generator-usage-cancellation.json.

Completed results and the no-adoption decision: @tests/jev-durable-core-generator-real-results.json,
@tests/jev-durable-core-generator-independent-quality-review.json and
@tests/jev-durable-core-generator-adoption-decision.json.

A separate research-only Memory quality pilot froze 48 authored development samples:
32 preserved generator outputs plus 16 newly authored samples, including facts
from pinned Nanoid and Tinypool READMEs. These are neither heldout project workflows
nor human gold labels. Each candidate received a lasting-value Noul and the whole
resulting Memory received an explicit-request omission Noul. Baseline proposals
remained proposals; thresholds and write permissions were unchanged. Raw create
plans, source quotes, exact resulting bodies and case-insensitive inventory
identity were checked before any inference. Transport helpers and runtime bytes
were frozen and reviewed; the final network-disabled preflight made zero calls.

The real study made 80 Jev 1.13 requests in 99.654 seconds, with one quality timeout
and 79 known usage responses. Known estimates total $0.002963268; total cost remains
unknown and billing unverified. Against fixed development labels, combining the
new quality check reduced unsuitable allows from 4 to 1, but also reduced eligible
allows from 20 to 10. Among seven labeled omissions, the omission question definitely detected none:
two were missed and five remained uncertain. The ten new eligible holds were
nine uncertain decisions and one timeout, not ten demonstrated semantic errors. All 16 fresh baselines were proposals, with generic
metadata descriptions causing support uncertainty, so that cohort cannot establish
an improvement in completed learning. These failures are retained, not repaired
retrospectively by changing labels or retrying inference. The new gate is not
adopted; default Jev behavior remains unchanged. No actual Memory writes, recall
or Harness execution occurred in this semantic pilot.

Subsequent Pi generation and project experiments use the user-selected
`cli-proxy / opencode/space-bunny-free`. One isolated real Pi availability probe
returned the expected marker; this does not establish learning quality or verified
cost. Host global configuration was not changed. See
@tests/jev-space-bunny-model-probe.json,
@tests/jev-memory-quality-manifest.json,
@tests/jev-memory-quality-real-results.json and
@tests/jev-memory-quality-adoption-decision.json.

The incremental repair schema example now uses the same concrete fact in its
index description and body, and explicitly forbids treating the example as
candidate evidence. Original citations, identities, privacy, repair count and
Jev checks remain unchanged. A dynamic worker-prompt regression reproduced the
previous mismatch before the fix. This is a local prompt correction, not a
verified model quality gain.

An eight-arm isolated native comparison using `cli-proxy/opencode/space-bunny-free`
attempted both versions on four fixed bilingual Nanoid/Tinypool development
samples. All eight main requests failed upstream, so no candidates or Jev
judgments were available and the quality comparison is unverified. All owned
containers and process groups were stopped; failed-response usage remains unknown.
A separate two-call Pi diagnostic received HTTP 429 with both default thinking
and thinking off; this is not a learning experiment or proof of the earlier
failure's exact cause. Earlier simple model availability does not establish
current workflow availability. See @tests/jev-repair-schema-real-results.json,
@tests/jev-repair-schema-model-diagnostic.json and
@tests/jev-repair-schema-verification.json. No favorable retries or missing-result
zero scores are used to claim improvement.

A subsequent read-only completeness pilot used 20 fixed development outputs:
four real generator outputs, eight previously authored samples and eight new
controls, spanning five request contexts in English and Chinese. Forty-eight
requirements were manually anchored to exact original user spans and independently
model-reviewed before inference. Both the whole omission question and each
requirement-preservation Noul received identical resulting Memory bodies with
frontmatter removed. Unknown responses never become complete; no completeness
answer grants extraction, privacy or write authority. Extra requirement fields
are rejected so evaluation labels cannot enter questions.

Twenty real Jev 1.13 calls completed in 32.003 seconds, with all usage known and
no writes. The joint batch estimate is $0.001129002, billing unverified; separate
method costs and latency were not measured. Against the authored labels, definite
omission detection increased from 3 to 4 of 9, and one unsafe complete judgment
became uncertain. Of 11 complete samples, both methods recognized 8, but two
improvements were offset by two new holds, both Chinese; Chinese recognition fell
from 4 to 3. The 48 item judgments included 38 decisive correct answers and 10
uncertain answers, including five missing requirements still not definitely
identified. This is a local safety signal, not a production learning benefit:
manual requirement extraction, bilingual regressions and actual workflow effects
remain unresolved. The new method is not adopted and Jev defaults are unchanged.

An initial execution preparation failed before any model call because the proxy
read an unfrozen task-local configuration path. Original zero-call failure
artifacts are retained. The final runner checks the actual configuration paths;
an offline regression and renewed network-disabled preflight confirmed the fix
before real inference. See @tests/jev-request-completeness-real-results.json,
@tests/jev-request-completeness-adoption-decision.json and
@tests/jev-request-completeness-verification.json.

A subsequent automatic text-coverage pilot preserves every selected original
user character in 30 source spans, without manually selecting the 48 known
requirements. On the same 20 development outputs in a new joint batch,
whole/manual/automatic judgment detected 2/4/4 of 9 incomplete outputs, but
recognized 9/7/6 of 11 complete outputs; Chinese complete recognition was 4/3/2.
All 20 real Jev calls completed with known usage. Text coverage does not establish
atomic semantic extraction, durable relevance or write permission. This pilot
is not adopted because net benefit is unproven. See
@tests/jev-user-request-coverage-real-results.json and
@tests/jev-user-request-coverage-adoption-decision.json.

A separate two-call readiness diagnostic kept cli-proxy/opencode/space-bunny-free
and compared actual output caps of 524,288 and 8,192. Both calls returned HTTP 429
with `model_cooldown` (roughly 6h36m remaining when tested), so generation and any
output-cap effect on a healthy model remain unverified. No host configuration
change was adopted. CLI exit 0 was separated from assistant failure, and failed
usage remains unknown. See @tests/jev-main-output-budget-real-results.json and
@tests/jev-main-output-budget-adoption-decision.json. The diagnostic's local proxy
sockets and owned containers were closed; remote cancellation is unverified.

Failed or aborted planner replies cannot supply Memory, Harness or AGENTS.md
candidates, even when Pi exits with zero or their partial text contains valid
JSON. They stop before repair, Jev judgment and application. Retry bookkeeping
does not clear cancellation; only a successful fresh reply restores completion.
This also applies to Memory repair through pi-kit. Receipts report missing
worker usage and cost as unavailable, with known subtotals when present, rather
than treating failed calls as free. Legacy v1 receipts remain readable. These
failure-handling checks establish safety behavior, not overall Jev quality gains.
The network-disabled native Docker check loaded the extension with Pi 1.0.2,
observed `stopReason: "error"` with CLI exit zero, rejected the plan and returned
a failed pi-kit worker with empty text and unavailable usage. It used a local
fault transport rather than external inference. A second local transport sent
valid plan-like JSON before a stream error: native Pi retained that JSON with
`stopReason: "error"` and exit zero, while both extractors rejected it. Grounded
full-plan application safety is covered by regression fixtures. See
@tests/jev-failed-planner-native-results.json.

The fixed requirement-indirection comparison used the same 20 development
samples, original user spans, full frozen state, resulting Memory bodies,
criteria and 0.9/0.1 thresholds. Flattening `requirement.quote` into a direct
`requestedFragment` recognized complete outputs in 11/11 cases versus 9/11
for the nested form in this run, but incomplete outputs judged complete also
rose from 0 to 1; definite
omission detection remained 4/9. The new false acceptance involved a Chinese
requested purpose. It is not adopted, and no favorable retry or heldout run
followed that regression. All 20 real Jev 1.13.0 calls returned usage: 36,840
input and 2,096 output tokens, with known input-tariff estimate $0.00154728.
Both arms share each batch, so their latency and cost cannot be compared
independently; total reported request duration was 21,980 ms. There were no
main-model calls, writes, recall or Harness executions. This does not establish
plugin learning net benefit. See @tests/jev-focused-requirement-manifest.json,
@tests/jev-focused-requirement-real-results.json and
@tests/jev-focused-requirement-adoption-decision.json.

### Audit safety and upgrade ownership

Learning workers use only the package's parent-scoped `learning_read` tool, not native read/grep/find/ls or shell tools. Incremental Memory is dossier-only; broader maintenance still checks project containment, symlinks, sensitive paths/content and read bounds. Variable Memory metadata is a replaceable untrusted reference message; the system prompt contains only fixed retrieval instructions.

Readable private paths remain compatible, with canonical project ownership recorded outside Memory entry roots. The first canonical project accessing an unbound legacy scope is bound automatically, preserving upgrade compatibility. This only adds an ownership binding; it never moves, rewrites or merges existing Memory or scoped Harness. Another project's binding cannot be overwritten. First-access binding cannot retrospectively prove historical legacy ownership. A colliding or malformed scoped Harness binding is diagnosed as unavailable rather than reusing another project's cached policy; global/project layers remain loaded.

Application rechecks predecessor bytes and verifies readback. Rollback restores only still-owned writes; newer human edits are preserved with a conflict diagnostic. Interrupted AGENTS extraction uses a durable ownership journal; legacy incomplete transactions without ownership proof require reconciliation instead of guessing.

`/memory` browsing has 32-row pages and a separate 4,096-entry management limit. Selected bodies, history and Harness details support full bounded pagination. Proposed history explains the fresh `/consolidate` next step. Automatic applied/proposed/failed/rejected/cancelled outcomes show a compact receipt. Omitted Task Slice evidence downgrades apply to propose and is shown in receipts. None of these safety checks establishes improved model task success.

Private run artifacts are retained without automatic expiry; this repair does not remove existing snapshots or history.

### Real-model downstream evaluation

Memory persistence and passing package tests do not establish improved task
quality. The explicit paired study at
`tests/live_memory_task_quality.py` learns through the actual Pi parent pipeline,
then runs fresh sessions with and without learned Memory using the same model,
current files and task. It scores a written task artifact against an oracle fixed
before requests, covering settled facts, uncertain claims, one-task instructions,
superseding decisions, expired exceptions and corrections. It records learning
failures, technical-invalid pairs, unsupported answers and regressions separately.
The small authored development/held-out template instances are bounded evidence,
not a general capability or statistical reliability claim. Jev is explicitly off.

These commands use the configured real provider and incur model usage:

```bash
uv run --no-project packages/continual-learning/tests/live_memory_task_quality.py /tmp/memory-quality --split development
uv run --no-project packages/continual-learning/tests/live_memory_task_quality.py /tmp/memory-quality --split heldout
uv run --no-project packages/continual-learning/tests/live_memory_task_quality.py /tmp/memory-quality --split heldout --task-type resolve
```

The `resolve` task combines the learned opaque alias with a fresh five-entry
catalogue to produce a new handoff value. The value never appears in training;
opaque project names and varied catalogue positions prevent category/position
shortcuts. Both arms receive the same complete current-file inventory.

Each run creates a new directory containing the frozen corpus, source hashes,
per-case learning plans/receipts, fresh sessions, task artifacts and report.
Do not merge exploratory, source-drifted or failed runs into the final results.
Ordinary model `write`/`edit` calls cannot modify the current private or shared
Memory roots; maintain knowledge through `/memory` or `/consolidate` so the parent
can validate it and preserve history/undo. This tool boundary is not an OS or
shell sandbox.
Empty scoped discovery is also explicit, including when automatic learning is
off. Retrieval guidance uses supplied roots/indexes and discourages guessed
Memory locations; no available Memory is not evidence for a project fact.

For intermittent AGENTS failures, `tests/live_agents_reliability.py` retains
actual planner-child JSONL, failure output, receipts and before/after documents.
Use `--full-pipeline` to include Memory and Harness. The parent grants the exact
dossier file alongside the frozen snapshot; it does not grant sibling agent
files. Successful retries do not establish the cause of an earlier failure.

`tests/live_real_project_memory.py` is a separate explicit Jev-on Docker study
using pinned p-limit and pluggy source. A real model first performs bounded
read-only source orientation (at most twelve tool calls), runs upstream checks
and learns through the parent pipeline. All original source remains unchanged.
Earlier audit-and-test training cohorts are retained as invalid attempts; the
orientation protocol does not expose the later feature tasks or hidden checks.
A successful applied Memory attempt with real Jev usage is required before any
downstream model task. Fresh sessions implement pause/resume scheduling or a
temporary-plugin context manager with identical post-training code, dependencies,
model and task prompts. The only arm difference is scoped Memory availability.
Hidden behavior and type probes enter containers after model execution; full
upstream checks and original test/configuration hashes prevent weakened checks
from scoring as success. Failures and ties remain results. These authored feature
tasks on previously used public projects are a small experiment, not upstream
issue acceptance or evidence of general model improvement.

The study requires Docker, the isolated Pi 1.0 runtime image
`cl-real-project-runtime:20261010-base`, pinned local source checkouts matching
`tests/real_project_tasks.py`, configured inference, and `TYPESAFE_API_KEY`.
Real keys stay in the host proxy. Do not mount host project or agent directories.
Run the environment/oracle gate before incurring model usage:

```bash
docker build -f packages/continual-learning/tests/docker/real-task.Dockerfile -t cl-real-project-runtime:20261010-base .
uv run --no-project packages/continual-learning/tests/live_real_project_memory.py /tmp/real-memory --preflight-only
uv run --no-project packages/continual-learning/tests/live_real_project_memory.py /tmp/real-memory --repeats 2
```

Each directory freezes the protocol/oracles, source hashes, runtime image digest,
actual sessions, learned Memory, receipts, candidate source and independent check
logs. An invalid training run stops later paid work; it is not a losing baseline
or a Memory improvement. Native terminal interaction, safe application/undo and
downstream task quality remain separate acceptance claims.

Incremental learning retains at most 256 complete entries and 512,000 serialized
UTF-8 bytes. User/tool evidence and assistant tool-call provenance take priority
over plain assistant narration. Any missing primary evidence still forces
proposals-only handling; omitting plain assistant narration alone does not. Exact
citations and Jev validation remain required. Receipts distinguish these omissions
and retain the original session source/count, including runs that apply nothing.

Jev full-evidence review budgets up to four batches for the support job and each
of at most sixteen evidence windows (68 logical requests). The existing single
connection-only retry permits at most 136 transport attempts. Concurrency remains
four, each request stays within 64,000 wire bytes and 32 questions, and every
support/body/description/counterevidence judgment must complete successfully.

With Memory review enabled, every selected existing record omitted by a plan is
reviewed against the complete frozen evidence, including zero-operation plans. Contradicted or uncertain
retained claims prevent a completed receipt and backlog acknowledgment. One
bounded amendment may propose cited rewrites or deletes for the held records;
it must cover every held record and preserve scope and privacy classification.
The parent retains original operations and new proposals exactly, then reviews
the complete combined plan before application. Retention holds cannot enter
partial application. All ordinary parent validation and mutation gates still
apply. Passing these gates does not establish that later model tasks improve.

Malformed incremental JSON with one explicit plan marker may use the existing
structural correction slot only when the extractor found no structured plan and
the selected existing scope is empty. Ambiguous plans and transport/model failures
remain rejected. Regenerated proposals are always private because damaged output
cannot establish trustworthy sharing intent; exact citations, frozen evidence and
Jev gates still apply. The isolated public-source study explicitly allows Jev to
review these private records; it contains no private user data.

To retry learning after a confirmed runtime fix without repeating a successful
source audit, pass `--resume-from /path/to/prior/cohort`. The prior source hashes,
project protocol, original-file checks, upstream tests, model and sole original
source-orientation request must match. The runner copies that real session into
a fresh identical checkout and uses the product's `continue` contract, with only
a final-summary instruction appended to the system prompt. The parent summary
turn disables tools with `--no-tools` instead of relying on that instruction;
learning workers keep their independent read authorization. A new actual model
turn and normal automatic learning run again. One actual parent-bound dossier
must retain every original user/tool observation byte-for-byte as JSON; otherwise
training is invalid. It never seeds Memory or future answers. Usage for resumed
training includes the prior session and is labeled accordingly.

Memory planners receive a model-facing projection that labels each original
Task Slice entry with its parent-generated `snapshotIndex`. The existing repair
uses the same labels. Raw dossiers/snapshots, hashes, citation roles and exact
quote validation remain authoritative and unchanged; other scoped readers only
use this projection when explicitly opted in. This reduces manual array counting
without correcting or accepting a model's invalid citations automatically.

Semantic Memory repair changes only candidates marked by parent-controlled review
results. Omitted delta entries remain unchanged in the parent-owned full plan;
omission cannot delete a proposal or clear pending learning. Full identity,
citation, privacy and semantic validation still runs on the merged plan. Bounded
repair responses are retained privately for diagnosis, omitting sensitive text.
Counterevidence questions retain each candidate's original citation association
alongside the complete evidence windows.

Cited result support also carries the original matching tool call when its id,
tool name and chronology pair uniquely. This establishes invocation provenance,
not success or factual authority for assistant prose. Harness support questions
identify the candidate's exact original quotation; complete context and later
corrections still govern authorization. Automatic source learning favors
non-obvious reusable contracts and pitfalls over routine inventories. Explicit
knowledge requests and personal preferences remain eligible in full.

The continuous study's coverage version 2 includes six real maintenance tasks;
wrapper mapping consumes the corrected type contract in a subsequent fresh
session. Actual failed hidden/type/upstream verification is retained completely
and read once through a source-bound continuation of the original session in both
arms. The learning arm can then perform one explicit bounded backfill; failures
remain failures and feedback/recovery usage is counted. No verifier answer or
Memory is seeded. Processing a failed job differs from learning a lesson: the
latter requires the exact acknowledgment digest, an applied change from that
receipt's parent mutation batch, and later consumption. Legacy receipts without a
batch identity remain readable but cannot establish this stronger attribution.
Correction coverage additionally audits complete old/new Memory against complete
current source through Jev at the unchanged 0.90 probability/0.80 confidence
thresholds, then requires delivery of that exact revision in the next task.
Completed execution with missing evidence is `incomplete-coverage`; positive
coverage alone does not establish a task-quality improvement.

Bounded semantic repair now preserves each independently accepted Memory field:
when only the body is held, the original description/frontmatter and citations
remain; when only the description is held, the body remains. A complete original
review determines the repairable fields; the complete merged plan is validated
again. Promise adoption must not be confused with observable early completion.

Cited rewrites and deletions now use the same complete evidence windows as new
Memory. Support retains the operation target, preservation intent and existing
bodies; every original snapshot entry still receives counterevidence review.
This avoids rejecting long maintenance tasks solely because they were sent as
one request. Invalid citations, oversized whole entries and incomplete review
remain failures, with the same 64,000-byte request bound and semantic thresholds.

Repair responses now use the same bounded unique-plan framing as initial planning.
An explanatory prefix is discarded as framing, never treated as evidence or
permission. Multiple plans and truncated later objects are rejected; the complete
extracted object still passes identity, scope, citations, intent retention, privacy
and full semantic validation. Fixed parent-controlled repair diagnostics identify
framing/intent rejection without recording arbitrary worker errors. Index planning
and repair preserve type-level versus runtime scope and use one independently
supported clause rather than compressing several claims into an ambiguous label.

A selector response with the current identity but missing required routing fields may receive one structural correction using the unchanged task and metadata. Every present authoritative field must already be valid; corrected responses pass full selection and dossier validation. Preserve the original failed attempt and both calls’ usage in receipts, and omit sensitive response material from private diagnostics.

A digest-bound response with an invented schema kind may use the same single
structural correction slot when every present routing field is valid. Its fields
never authorize selection before complete schema validation. Known delivered
Memory remains a maintenance floor; Harness and AGENTS retain independent routing.
Both calls and the rejected response remain recorded, with sensitive material omitted.

Complete evidence windows are additionally split using the actual encoded wire
size and existing per-window question-batch limit. Every split preserves whole
original entries, full cited support, predecessor bodies and proposed operations;
all resulting requests are checked before transport. Indivisible oversized
requests remain failures. Structural correction retains its bounded private
response with the same sensitive-material omission as semantic correction.

Independent summary support and counterevidence judgments explicitly preserve
scope, conditions and observable meaning. An API call or source comment does not
by itself establish an observable runtime outcome. Promise descriptions must
distinguish resolver invocation/adoption from fulfillment or settlement, including
synchronous and already-settled cases; materially misleading ambiguity remains
unclear at the unchanged semantic thresholds.

Memory question batches carry the complete original citations and uniquely paired
tool invocations for the candidates in that batch, rather than repeating the
union of unrelated candidates' citations in every request. Body, description and
relationship questions are grouped by candidate before wire sizing. Every candidate
still receives every original snapshot entry in counterevidence review; exact old
Memory bodies and all same-plan operations remain in support and preservation
requests. Relationship review receives only established comparator records:
rewrites exclude their own predecessor, and deletions require preservation review
without a novelty question. Proposed records never serve as their own comparators.
Successful `edit` results can also ground changed source through their original
`details.patch`. Workers may select exact patch lines with
`{index, lines: {source: "patch", block: 0, start, end}}`; the parent retains diff
markers and extracts the original bytes. Failed edits, assistant arguments and
unrelated metadata cannot use this source. A patch establishes the reported edit,
not runtime correctness or immunity to later changes. All original observations,
privacy checks, semantic gates and mutation permissions still apply.
Privacy is checked on the full original snapshot before projection. The existing
64,000-byte, four-batch, sixteen-window and sixty-eight-request limits remain.

Backlog replay can combine verified prefix extensions of the same original task
so later verifier feedback reaches failure learning. Each queued digest must match
its original session range; new tasks, changed evidence, exhausted/deferred retries
and truncated slices are not silently combined. One parent receipt lists exact
covered backlog identities. Siblings are acknowledged before its owning reference,
and completed receipts are recovered before new work is selected. The unique
cost-bearing ledger preserves earlier failures and avoids duplicate model calls or
usage when acknowledgment is interrupted. Replay retains omission metadata so
incomplete evidence keeps its proposals-only policy.

When the receipt owner moves to a verified longer task prefix, earlier held
Memory plans remain available as untrusted correction context. Parent diagnostics
bind to the exact reviewed plan, including wholly held maintenance plans; legacy
plans without that binding carry no inferred candidate diagnostics. A later
Memory completion resolves only the task evidence it covers. Foreign receipts
cannot suppress prior failures, and cancellation during the attempt save prevents
a new learning call. Every retry still rechecks current evidence and mutation
scope through the ordinary validation gates.

Failure learning may retain an observed, source-bound limitation before a fix succeeds.
It must preserve unresolved status and distinguish requested, implemented and verified
behavior; failed runs cannot establish permanent command failures or new user restrictions.
Successful recovery still requires actual successful verification.

The same single selector correction slot covers a current position decision that
omits a required phase field. Present fields must validate against the unchanged
index. Missing flags are never filled by the parent; a second incomplete response
remains a failure, with both attempts and costs retained.

Memory support review distinguishes actual failed verification plus matching inspected
source from a temporary service failure. An explicitly unresolved defect is limited
to that source state; it proves neither its cause nor a successful fix.
Sparse semantic repairs may omit an unchanged candidate array: the parent retains
its original proposals byte-for-byte, then repeats all ordinary validation. Explicit
malformed arrays still fail. This does not relax review bounds or remove candidates.

When retained records and proposed knowledge both fail review, the parent completes both reviews before its single bounded correction. Their names and held fields remain separate: unflagged original content is preserved, and the combined plan must pass full review before any write.

Semantic correction preserves every original citation while either claim field remains protected, and omits only new exact subquotes already contained at the same snapshot index and role. When complete review holds both body and description, their replacement uses its own citations at the unchanged bound; the rejected plan remains archived and the complete corrected plan requires fresh review. Unique indentation restoration is recorded separately from raw worker output. For new proposals only, a complete digest-bound review may supply its fully accepted description as a narrower replacement body when only the body was held; this derived candidate still requires full combined review and every mutation gate. Existing Memory rewrites never use this distillation.

Semantic review sends structured JSON state directly to Jev instead of embedding
serialized JSON inside another JSON string. Memory body and description questions
explicitly reference their candidate's shared exact citation table. The parent
preserves complete original source entries, citation order/roles/indexes, mutation
context and independent judgments, and checks every final encoded request before
transport. The 64,000-byte, batch/window/request and semantic thresholds remain
unchanged. A plan that still exceeds these bounds remains pending; reduced wire
overhead alone does not demonstrate correct knowledge or downstream task benefit.

For a verified Qwen3.8-Flash OpenAI-compatible gateway, set
`"plannerJsonOutput": true` in the agent's `continual-learning.json` to request
provider JSON Object output for isolated workers with no active tools. This is an
explicit gateway capability opt-in; confirm that the gateway forwards and supports
`response_format` before enabling it. Existing provider output constraints remain
authoritative. The parent still checks the unique plan, exact citations, semantics,
privacy and authorization. Valid JSON alone does not establish valid learning.
