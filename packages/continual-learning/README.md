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
knowledge supplied as escaped data in a run-start section; it cannot enforce behavior. Harness is the
executable-validation surface: a rule can guide, confirm, or block only through
the parent-owned evaluator and its evidence-backed positive/negative cases.
`skill`/`text` rules and AGENTS.md are guidance for a bounded context, not proof
that the model complied. Manual, built-in, personal, disabled, invalid, and
legacy protections remain human-owned. A task may produce proposals for more
than one surface, but the same statement is not copied merely to increase
coverage.

## Install and commands

Python 3 must be available as `python3` for the bundled Memory validator.
Pi 1.2 structured prompt sections are required for run-start Memory and Harness delivery.
Unsupported runtimes report an error instead of silently losing guidance under `customPrompt`.

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

## Docker Isolation and Real Model Acceptance

`pi-continual-learning` supports containerized Docker verification with **Pi 1.4** and real model gateways such as **`(magpie) group/smart-split`**. 

End-to-end container acceptance establishes:
1. **Real Model Task Execution**: The agent processes project source files and instructions under Pi 1.4 with `group/smart-split`.
2. **Consolidation**: Executing `/consolidate full` prompts the model worker to extract durable project facts and safety rules, which are validated via `validate-consolidate.py`.
3. **Memory & Harness Persistence**: Safe memories are written to `.memory/` and refreshed in `MEMORY.md`, while executable validation rules are committed to `.pi/harness.json`.
4. **Subsequent Usability**: A fresh session in the same project automatically indexes and retrieves the learned memory and enforces the active harness rules.


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

If review holds existing Memory and the repair returns no correction, the receipt
says `Retained Memory review remains unresolved; no corrective operation was
proposed. No files changed.` The review remains incomplete; an empty response
does not prove that the records are correct or that protected intent changed.
Source evidence supporting the change is still required for a validated correction.

With Jev enabled, the parent can allow a semantic worker to decline an optional
new draft that has never been written. It checks the complete draft set against
user obligations, then checks the exact declined set and final remaining plan.
Both checks keep the original evidence and thresholds. Existing records and
required knowledge cannot use this path. The receipt says `not learned` and
counts no applied change for the draft. Original failures and costs remain.
An empty response, cancellation or uncertain review leaves the work pending.

Learning uses the current session model unless a separate provider/model pair
is configured. An explicit invalid or empty pair in `memory.json` is diagnosed
and prevents a worker from silently using a different model; `{}` retains the
session-model default. The metadata index is deterministic and bounded; it does
not rank entries against each new request. The complete indexes remain available
for discovery when the injected list omits entries.

The Harness panel lets the user choose the target layer before submitting a
rule request. Project shared configuration remains the default authoring target
for `/harness <request>`; personal and user-shared scopes require an explicit
choice in the panel. A missing target is a normal first-use state: a supported request creates one complete validated configuration without an empty placeholder. Broad operational safeguards can use scoped contextual guidance when no exact command gate is established; guidance does not enforce a traffic rate limit. Essential unknowns lead to an actionable clarification, not a missing-file dead end. Project tool access uses the relative target path. Authoring activates a read-only `harness_preview` tool: each changed enabled rule needs passing plain positive/negative fixtures before the exact candidate can be written. A preview is bound to predecessor bytes and consumed once; it never bypasses effective configuration or native replacement authorization. Verification never requires scratch files or a second write. The tool remains available for follow-up turns. A new request replaces its scope; session changes, branch switches and shutdown remove it. Every write still needs an exact, single-use preview. Pending authoring does not block ordinary source writes or grant authority over another Harness target.

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
change the selector, re-enable a rule, or weaken its Bash action outside the reviewed correction contract.

### Guidance scope and delivery

A skill read is not an invocation. Skill guidance names the applicable skill task
in model-visible text. Text guidance names its matching condition and does not
turn a historical mention into permission to apply it to unrelated work.

At `before_agent_start`, text matching scans the current prompt plus retained
branch conversation: user and assistant text, visible tool results and string
arguments, and retained summaries. Thinking, metadata, excluded shell output,
abandoned history, and Harness's own messages are not matching sources. Identified
configuration definitions are excluded; failed reads, native write outcomes,
mixed commands and ambiguous tool-call identities remain visible to matching.

Guidance contributes an additive structured section at `before_agent_start`.
It never returns a custom injection message or replaces the complete system prompt.
Non-context branch entries record scoped delivery revisions and sources. Unchanged
text guidance adds no duplicate row or ledger entry, while each matching run
still receives its structured section. A historical delivery alone does not
re-inject guidance after its ordinary matching text leaves the context.
An incomplete scan or configuration read retains complete prior scoped guidance from those entries.
The parent validates the saved scope header before delivery.
Unscoped historical guidance remains in history, with an explicit notice; it is not delivered.
Removed or changed rules retire through the same ledger; original history remains unchanged.
Legacy skill guidance uses this additive surface with the same skill-task boundary as flat guidance.
Saved configuration and execution gates remain unchanged.
Guidance delivery does not prove model compliance.

Bash evaluation also records non-context `harness-behavior-observation` session
entries. A decision binds its session, parent entry, input digest and exact
canonical rule revisions. Rule IDs, call IDs, commands and results are represented
by digests in these entries. At most 128 rules are listed; omitted rules, legacy
configuration or incomplete reads mark revision coverage incomplete. A matching
native completion links to the decision. The input digest covers this guardrail
stage; later extensions can still change arguments. Valid Pi timing proves that the handler
was invoked; it does not prove shell success or task correctness. Missing timing,
ambiguous or reused call IDs, changed sessions and exhausted tracking bounds
cannot establish execution. Observation failures do not change execution policy.
A confirmation from a closed or changed session cannot authorize an old call.
These records retain `taskOutcome: unverified` and `effect: cannot-attribute`.
They do not yet establish Memory consumption or paired task improvement.

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
Each learning batch retains its receipt under `runs/<project-scope>/receipts/<batch-id>/`.
The flat `learning-pipeline-receipt.json` is the latest-result compatibility view.
Later learning does not replace earlier batches. Cancellation updates the same
batch's terminal receipt. Cost collection deduplicates equal batch views and
rejects conflicting views; missing historical usage stays unknown.

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
After a complete ordinary task successfully edits or writes project source,
automatic Memory learning first collects fresh source within the existing
read-only scope. Original task observations remain intact. This extra collector
call and its failures appear in the receipt; a source read is not itself a
learned change. Existing citation, privacy, source-revision and semantic checks
still control every write.

For observed TypeScript declaration files, generation also receives a bounded
syntax view that locates direct function return types and their local declared
members. It uses the bundled parser without reading extra files or resolving
imports. The original evidence stays intact. These locations describe observed
syntax, not runtime behavior or accepted knowledge; the model still selects the
Memory content and every existing validation gate still applies.

New incremental project Memory also retains an exact observed-source block when a text unit
uses a citation that selects one eligible complete outer function declaration. This applies
only to successfully observed TypeScript declaration files. It preserves the
selected declaration's parameters as well as its return type, without expanding
the citation or inferring runtime behavior. Existing source units are not repeated.
The added blocks count toward the original unit and body limits and receive the
complete source, privacy and semantic review. They record an observation, including
when cited as older or contrary evidence; they do not establish current truth.
Existing entries, legacy formats and semantic corrections keep their contracts.
Unsupported syntax, oversized views and unproved source occurrences do not qualify.

For new project API knowledge, the parent also checks a narrowly proved source
relationship. A selected JavaScript wrapper call, its declaration and an observed
package export map must identify one local factory, named return type and direct
member. The original user's request must name the wrapper and member in one
visible sentence. Within a single source-cited knowledge unit, the related
statements may span sentences; separate units and descriptions are not combined.
Missing role citations go to the existing single structural correction;
the model must explicitly select and use them. For a draft rejected because
roles are missing, the parent retains that obligation through correction, so
dropping a trigger citation cannot erase it. Validated obligations remain bound to
the same run and snapshot through admitted atomic project BODY correction,
including exact-selected existing project rewrites. An initiating wrapper declaration
already explicitly selected, used and validated by the same AST proof remains a
separate source witness through structural and semantic correction; it is not a
fourth ownership role or an added reference. Legacy proofs without that witness
retain their original three roles. Both paths copy selected
source bytes and neutral declaration relations while preserving model text,
catalog entries and the prior frontmatter. Under the unique local direct-owner
AST proof, a selected complete factory signature can witness both its factory
and named owner roles; the direct member still needs its selected source span.
Generic, imported, indirect, inherited, merged or overloaded owners do not gain
this alternative. The original owner-heading selection remains valid. This does
not infer runtime behavior, add unselected evidence or bypass any source,
privacy, preservation or semantic check. Legacy formats retain compatibility.

Fresh project generation uses only `knowledge` with cited text units and one
source catalog. It does not ask the model to repeat factory/owner/member objects.
The existing source-relationship check proves complete roles from original
catalog citations already selected and used by text units, then retains only
that observed syntax through the same bounded source materializer. It adds no
missing role or unselected reference and preserves every original text/catalog
entry. Correct older atomic relation inputs remain readable.
Before current-file reads, snapshot-only validation collects metadata, catalog
and unit counts, quote bounds and missing source roles into the existing single
structural correction. The parent retains bound closure obligations across that
correction. Description errors identify the exact 120 UTF-16 code-unit limit;
JSON Schema's character bounds do not replace the parent check. Source, privacy,
current-file binding and complete semantic validation remain mandatory.
Already materialized, legacy and semantic-correction formats keep their contracts.

An empty Memory index plus explicit human facts or preferences lets automatic
learning route its already evidenced phases locally, without a selector model
call. An initial `/memory <request>` likewise goes straight to Memory planning.
The receipt marks this parent routing; planners and all validation still run.
Nonempty indexes and ambiguous inputs retain the metadata selector, and ordinary
manual `/consolidate` retains its reviewed routing.
With Jev enabled, normal parent Memory application requires a separate knowledge
coverage review. New parent-selected question contract 2 separates each record's
own completeness criteria from the unchanged whole-plan criteria. A local pass
cannot override a missing global goal. Historical feedback keeps its exact
original questions; a changed contract invalidates its binding. A coverage request
without the complete cited review path is rejected before transport.
It checks the complete plan, including an empty plan, every
actual record and each named missing condition from the current or rejected
version. Original source text is not a stored Memory location. Removed or
replaced records cannot act as retained witnesses. Optional automatic nominations
do not become mandatory storage goals.
The coverage scores join the existing source, permission, preservation and
consistency requirements at the original thresholds. A missing SDK, unavailable
response or malformed proof cannot satisfy this required stage. A supported but
incomplete body can use the existing bounded repair slot; its corrected actual
plan receives every full review again. Each numeric decision and exact plan
binding remains in the private run artifacts. These mechanisms do not establish
that a model learned correctly or improved a later task.
A complete, safe, retained coverage response can still fail account binding.
That response stays invalid. The parent can continue its independent source and
body checks once. Only an actual hold from those checks can use the existing
single plan repair. A bad account alone cannot retry or write. A corrected plan
still needs every fresh review. The parent saves the original source diagnostic
and rejected-response binding without creating a coverage proof.

A proof for a complete plan cannot authorize a changed subset. The new coverage
protocol holds such partial application until an exact subset obligation proof
exists. Explicitly bounded historical studies retain their original independent
subset protocol and wire format. Held work remains pending and cannot start
later Harness or AGENTS phases.
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
receipt. Harness and AGENTS planning can overlap after the Memory gate; mutation
remains sequential. Saving a semantically held Memory proposal, including a partial
application with pending records, does not unlock those later planners. A fully
reviewed repair or an intentional validated proposal policy can pass the gate.
A later phase failure does not undo an earlier verified phase.

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
For new coverage-reviewed rejections, backfill retains the exact historical
questions, every occurrence, and the original answer distributions. The original
receipt binds each private review artifact to its run, source, plan and bodies.
Changed, missing, ambiguous, unsafe or oversized diagnostics stop replay. Legacy
rejections without these fields keep their existing behavior. These diagnostics
are questions to investigate, not source facts, required answers or write approval.
Current source collection and every fresh review remain required.
Pi 1.2 can remove an empty assistant error during retry. Exact replay accepts
only this content-free null removal, strips the removed error metadata, and keeps
the original source hash, task digest and evidence positions. Meaningful
redactions remain refused. Replay eligibility does not clear the original task
failure or authorize a Memory or Harness change.
A latest phase with pending candidates cannot acknowledge its task as learned,
even if other candidates applied or that phase returned noop. Summaries warn and
show the latest unresolved count; a later completed phase supersedes its earlier
pending disposition. Source-verified backfill with an empty index uses the same
parent routing for explicit durable evidence as automatic learning, preserving all
mutation validation and semantic review.

Fresh tasks receive a compact index of deduplicated Memory filenames and
one-line descriptions. An unchanged index stays in place across user turns;
changed indexes replace stale references and missing context restores discovery.
Entry bodies are read on demand, never automatically injected. Metadata exposure
is not proof of use or benefit; current evidence and instructions take precedence.
Use the native `read` tool to consult relevant entries. Automatic correction revisits Memory actually read through unique successful read calls; failed or ambiguous reads do not nominate entries. Revisit is not factual evidence or permission to mutate. Explicit `/memory` requests retain their selected maintenance scope.

Local non-context `memory-use-observation` entries distinguish section preparation
from a complete body result. Complete file revisions come from the existing
bounded loader's raw bytes only when UTF-8 decoding round-trips exactly. At task
settlement, a full-body observation requires matching native handler timing and
content, a start-time session binding, one retained call/result pair, and an intact
branch back to preparation. Equal bodies in multiple snapshots remain ambiguous.
Partial, changed, failed, duplicate or foreign results establish no complete read.
Only hashes and native entry IDs are recorded; bodies remain on demand.
Observation is limited to 128 snapshots, 256 pending results, 4,096 seen call IDs,
64,000 body characters and 10,000 branch entries. The loader may retain a shorter
prefix; that entry has no complete snapshot. Exceeding a bound leaves proof
unavailable and does not change learning or execution. Preparation does not prove
wire delivery. A complete result does not prove physical file origin, model
attention, correct knowledge or task benefit; those fields remain unverified.
The native acceptance runner separately checks actual next-request content.

An automatically learned project Harness rule may be revised or retired only with
an exact predecessor revision, current user correction, positive/negative fixtures
and approval of the exact replacement by semantic review. A retired rule remains
as a disabled revision and in history. Manual or changed rules remain protected.
With automatic Harness application and semantic review enabled, an explicit lasting
correction in the current original user input is reviewed before task execution,
so the persisted correction can govern that task. This conservative nomination
requires the original input event to match the run prompt exactly; it grants no
authority by itself. Only exact auto-owned revisions can be updated, under one
230-second total deadline and the same complete semantic/fixture/transaction
checks. A held or failed review preserves the old policy and every cost; it never
acknowledges the unfinished task. Ordinary task `write` calls must preserve
owned declarations and markers; explicit previewed `/harness` authoring remains
available. This is a tool boundary, not a shell or filesystem sandbox.

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
All original final validation and mutation gates remain mandatory. Citation-location rejection supplies up to eight parent-controlled candidate/citation positions and reasons to that same correction, including range and extracted-quote bounds; it never includes source text in diagnostics or raises the 2,000-character quote limit. Long encoded source lines are shown as complete numbered chunks; explicit offsets inside one line let the parent extract original characters without model transcription or decoding.

For a held private project body, the semantic worker can select `sourceExcerpt`
instead of generating `content` when the parent explicitly enables that candidate.
The selection requires explicit original citations from the bound current-source
audit. The parent checks the complete source hash and regular-file identity, then
copies the selected bytes into a neutral excerpt. Locked metadata stays unchanged.
This alternative uses the existing correction attempt. It grants no approval:
complete predecessor preservation, body, source, privacy and transaction checks
still govern writes. Ordinary historical reads cannot supply this correction.

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

New applied Memory history can retain a parent-observed origin binding. It links
the complete frozen task, plan, manifests and receipts by their exact hashes and
records the file revisions before and after the mutation. This metadata stays in
private history. Missing or inconsistent artifacts mark origin unavailable;
legacy records gain no inferred origin. Undo still compares bytes and mode.
A read-only local interface can recover the complete creation and rewrite tasks
only through an unbroken, unique file-revision chain. It refuses incomplete or
changed evidence, cancellation, and configured bounds instead of returning a
partial history. It checks the complete captured inventory again before reuse.
With explicit private review authorization, normal Memory review and its bounded
correction worker receive complete relevant historical tasks in a separate
`historicalMemoryOrigins` field. The parent screens the full history for sensitive
data before projection and checks its binding again after asynchronous work.
History explains predecessor purpose and conditions; it does not establish current
facts, support citations, read access, permission to rewrite knowledge, or learning
benefit. Current evidence and every semantic gate remain required. Legacy gaps
gain no inferred context. Initial planning, CREATE-only review and historical
byte-bounded requests do not acquire this context.

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

The default index injection budget is 6,000 characters. Entries list only a
filename and description, without per-entry source suffixes. Case-insensitive
filename deduplication prefers the private copy across locations. A compact root
list supplies read routing; omission counts and complete-index pointers appear
only when entries are omitted. Relevant bodies require explicit bounded reads.

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

After parent structure, identity and frozen-quote validation, another batch checks candidate support using the knowledge body or rule rather than administrative frontmatter/evidence bookkeeping (while scanning the full original candidate for credentials). For fully cited new Memory, the support question includes only the complete knowledge body; filenames and write/storage metadata cannot become claims requiring user evidence. Rewrite/delete/mixed batches retain the complete preservation context. This batch also checks Memory grounding and relationships against already-read bodies (Choice), and general Harness scope (Choice). For an absolute-end anchored literal block or confirmation rule, parent code proves the exact command matcher and Jev separately checks lasting user authorization and message fidelity. A confirmation rule requires the real native Allow once or Block decision for each invocation; a one-time grant cannot revoke future confirmation, and confirmation cannot weaken an unconditional ban. Plain `$`, whitespace classes and operators never qualify for that proof. Duplicates, conflicts, unsupported or uncertain candidates become proposals; an unavailable candidate judge also produces proposals. For a proved literal/family rule whose message is byte-identical to its validated original user quote, code proves wording equality and omits only the paraphrase judgment. Authorization, matcher scope, complete counterevidence and parent write checks remain mandatory; changed messages still require semantic verification. In the proved ASCII command-family grammar, literal TAB and its regex escape have identical meaning. Counterevidence review receives the exact code-proved command range, block action and original explanation; unproved regexes retain full matching review. Generated fixtures and rule identifiers do not establish user permission. No Jev answer permits a write by itself or disables existing Harness rules. Normal requests have at most 32 questions and four concurrent requests; byte capacity is delegated to the configured service. Explicit historical experiments can retain a 64,000-byte bound. For quoted new Memory candidates and parent-validated Harness citations, support uses the complete cited entries and existing bodies; a separate counterevidence review covers **every** indexed original entry. Normal requests preserve preferred 20,000-byte whole-entry windows without a local request-byte cap; explicitly bounded experiments additionally preflight every encoded request. The configured service token limits still apply. Entries are never truncated or summarized. Every review also receives the original cited support to interpret meaning and scope; later corrections still override that support. There are at most sixteen windows. The legacy and non-mutation path has at most 68 prepared logical requests, including split support requests (up to four batches per job); normal mutation review has the separate 576-request bound described below. Coverage jobs fit the applicable existing prepared bound before any transport; the existing connection-only retry permits at most 136 transport attempts. Windows are never merged based only on raw entry bytes. If a cited support entry is also in the current review window, supportEvidence.reviewEntryIndexes points to that exact original entry instead of transmitting it twice; the complete cited context remains present across both fields. All original evidence and all planned requests are checked for sensitive material and bounds and copied before the first transport. Only fully successful windows count toward coverage, and any failed, uncertain or conflicting judgment holds the entire plan. Rewrite/delete/mixed Memory plans and uncited legacy inputs retain full-evidence transport with at most four batches. Any explicit experimental wire-byte cap is not a token count; API context failures remain proposals rather than discarding possible later contradictions. A batch is atomic for this policy: one questionable candidate holds the whole plan for review. Supported supplements can be applied only under the existing apply policy. Full maintenance also checks its validated candidates; too much evidence falls back to proposals.

Normal project requests use the configured service capacity without a local byte cap and retain 32 questions per request; explicit historical experiments may still set `maxRequestBytes: 64000`; cited evidence windows prefer 20,000 bytes. Oversized evidence is not silently truncated: selection falls back, candidates become proposals. Requests default to a 15-second timeout, honor explicit shorter deadlines, use zero SDK retries and at most one connection-only retry, propagate cancellation and disable SDK body logging. That single retry waits a bounded 500 ms backoff before re-issuing the same frozen request, and an abort during the wait is honoured immediately; the retry count, request bounds and per-request deadline are unchanged. A failed request group stops later groups of the same review, so an already-unusable review spends no further requests. Starting thresholds are Noul ≤0.1 / ≥0.9. Memory relation acceptance uses P(unrelated or supplement) ≥0.9; general Harness scope uses P(same or narrower) ≥0.9. Ambiguity between these compatible classes is acceptable; this does not require high confidence in one class. Memory grounding, literal-command authorization and message fidelity require confidence ≥0.8 and winning probability ≥0.9. Harness review includes parent-validated blocked/allowed examples, with frozen evidence remaining the sole source of authorization. Metadata uses P(level 2 or 3) ≥0.9 to select and ≤0.1 to omit on a 0–3 rubric; intermediate probability falls back. These are conservative policy parameters, **not calibrated accuracy claims**. Validate them on your workload before relying on the integration, especially for Chinese.

For an apply-policy Harness plan, an unsupported or uncertain semantic hold may use its existing single read-only repair slot shared with structural repair. Incremental Memory permits one structural correction followed by at most one separate semantic correction, without retrying either phase or replanning. With Jev enabled, the first incremental Memory structural repair also receives the original hash-checked snapshot and selected Memory dossier; it must not turn one-task instructions into lasting preferences. Both files are rechecked after repair, valid original privacy classifications must remain unchanged, and a rejected completed call still retains its usage. These existing phase budgets do not relax subsequent validation. Memory correction uses frozen evidence and already-read bodies, preserves names, intents and privacy classifications, and retains the original proposal if correction remains held. Duplicate, conflict and service failure do not trigger another correction. A semantic Harness repair may omit unsupported operations, but their exact original evidence is reindexed and saved as private pending proposals. Semantic repair receives an explicit table of the original operation kind, rule identity and complete evidence objects. Retained rule identities and all citation properties must stay unchanged apart from operation indexes; an empty or replacement repair retains the original proposal. Repaired candidates repeat parent validation and Jev judgment; service failures do not cause retries, and unresolved candidates remain proposals. Frozen evidence is checked after each judgment and again in the mutation queue before writing. A direct apply cannot bypass a semantic proposal. Memory index descriptions receive independent support, existing-Memory relationship and full-evidence checks alongside the original body checks. A duplicate description can accompany a body that adds supported knowledge; duplicate bodies and conflicting descriptions remain proposals. All additional questions fit the existing request limits before any call; budget exhaustion retains a proposal.

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

Normal unbounded Memory rewrites and deletions use separate required questions
for factual evidence, permission for the parent-owned Memory operation, and
predecessor preservation. Factual review includes original user preferences and
policy corrections even when writing remains permitted. Source changes cannot
grant permission or revoke those preferences. Every original window retains
complete old and proposed knowledge, source observations and separate description
review. Each component requires probability 0.9 and confidence 0.8. The parent also
requires `max(0, pEvidence + pPermission + pPreservation - 2)` to
reach 0.9. Missing, uncertain or conflicting checks hold the mutation. This changes
the question protocol; it does not demonstrate calibrated joint reliability or
learning benefit. Finite historical studies keep their original questions.
Each normal rewrite/delete support and counter request also receives the complete
original user statements, with original indexes and snapshot identity. This keeps
scope, temporary-only requests, privacy limits and later revocations available
when citations name only tool results. The parent derives this context from the
original snapshot, after privacy screening; quoted user text in tools, assistant
output, source and Memory cannot enter it. This context adds no support citation
and proves no completed work. CREATE-only, retention and finite historical
requests keep their existing context. Complete windows and all gates still apply.
The context is copied once. If evidence, predecessor records or candidates change
during service work, review stays proposed with an invalid-response diagnostic.
Known usage remains available; changed inputs receive no complete or partial proof.
Normal mutation diagnostics retain the first held location for each candidate,
field and dimension. A held preservation or permission check can nominate its
body for the one bounded amendment. All other fields remain locked, and the
amended plan must pass fresh complete review before any write.

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

Learning workers use only the package's parent-scoped `learning_read` tool, not native read/grep/find/ls or shell tools. Incremental Memory is dossier-only; broader maintenance still checks project containment, symlinks, sensitive paths/content and read bounds. Variable Memory metadata occupies a replaceable, escaped structured prompt section beside fixed retrieval instructions. No reference message is appended for each user turn.

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

The study requires Docker and an isolated Pi 1.3.0 runtime. The historical cache image
`cl-real-project-runtime:20261010-base` is upgraded before fresh study admission. Use pinned local source checkouts matching
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
four, each request stays within 32 questions and the configured service capacity, and every
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

The opt-in `--explicit-command-initialization` protocol separates source work,
Memory maintenance and automatic rule creation. It requires
`--observed-idle-failure` and `--unlimited-budget`; it cannot be combined with
`--verified-failure-learning`. Both arms first inspect the same source with
automatic learning off. The learner then runs the actual same-session
`/memory 整理记忆` command and at most one processing-only source closure.
Both arms receive the same separate policy task with native tools disabled.
Only the learner can create an automatically owned Harness rule. The original
task failures remain failures. All added calls, time and costs remain counted.
Complete source inventories and physical history link the Memory endpoint to
the rule's birth and later correction. This is a separate treatment, not an
unchanged comparison with historical automatic cohorts or an equal-total-compute
claim. The five later tasks and all semantic thresholds stay unchanged. Fresh
frozen-source preflight and independent admission are required before paid use;
controlled tests do not establish learning benefit.

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

Semantic correction preserves every original citation while either claim field remains protected, and omits only new exact subquotes already contained at the same snapshot index and role. When complete review holds both body and description, their replacement uses its own citations at the unchanged bound; the rejected plan remains archived and the complete corrected plan requires fresh review. Unique indentation restoration is recorded separately from raw worker output. For new preference proposals only, a complete digest-bound review may supply its fully accepted description as a narrower replacement body when only the body was held; this derived candidate still requires full combined review and every mutation gate. Project knowledge and existing Memory rewrites never use this distillation: an index description must not replace a complete technical contract. A held project body requires full-body correction or backfill. Quoted descriptions are copied verbatim, without interpreting escapes. An unchanged proposal may use its original complete checklist; a corrected proposal must use its own fresh digest-bound checklist. At most one deterministic narrowing follows correction, with another complete plan/body/source review before any write. Repair feedback includes independent body and description holds; a first body failure cannot imply that the description passed.

Semantic review sends structured JSON state directly to Jev instead of embedding
serialized JSON inside another JSON string. Memory body and description questions
explicitly reference their candidate's shared exact citation table. The parent
preserves complete original source entries, citation order/roles/indexes, mutation
context and independent judgments, and checks every final encoded request before
transport. The 64,000-byte, batch/window/request and semantic thresholds remain
unchanged. A plan that still exceeds these bounds remains pending; reduced wire
overhead alone does not demonstrate correct knowledge or downstream task benefit.

For a verified Qwen3.8-Flash or DeepSeek OpenAI-compatible gateway, set
`"plannerJsonOutput": true` in the agent's `continual-learning.json` to request
provider JSON Object output for isolated workers with no active tools. This is an
explicit gateway capability opt-in; confirm that the gateway forwards and supports
`response_format` before enabling it. Existing provider output constraints remain
authoritative. The parent still checks the unique plan, exact citations, semantics,
privacy and authorization. Valid JSON alone does not establish valid learning.
Supported DeepSeek IDs are `deepseek-flash`, `deepseek-v4-pro`, and the
`deepseek-v4.1-flash` gateway alias, including provider prefixes. DeepSeek uses
JSON Object only. The separate strict-schema switch does not enable it or send
a Qwen schema. Empty, incomplete or invalid responses remain rejected.

For a Qwen gateway separately verified to support strict JSON Schema output, set
`"plannerStructuredOutput": true`. The isolated metadata selector then requests
its exact position/phase schema. Incremental Memory workers request the complete
delta schema; candidate-bound semantic repairs request the amendment schema.
These require non-empty citations but never choose source positions or establish
facts. When frozen evidence is available, the parent also supplies its complete
eligible index/reference catalog: old Memory readbacks remain context but cannot
be selected as original sources. An oversized catalog refuses strict generation
without trimming or downgrading; unsupported models remain unaffected. With no
eligible source positions, only an empty plan is permitted and it does not count
as learned correction. Full-corpus and unrelated workers keep their existing output behavior.
This capability is separate from JSON syntax support and excludes unknown models. The parent still rejects
out-of-range or duplicate positions and invalid decisions; schema conformance
cannot authorize learning or establish semantic correctness. A service refusal
remains a failure, with no silent downgrade or synthesized phase defaults.
The same explicit opt-in permits `gpt-6-luna` on Responses to use a narrow native
strict schema for parent-admitted candidate-bound atomic body repairs. It binds
all supplied `requiredTopLevelValues` and the candidate-reference domain exactly;
body text and citations remain one `knowledge` catalog/unit value, with description
changes offered only for admitted candidates. A new project proposal or a rewrite of an exactly selected predecessor with known
project type must include its description when the complete bound independent description checks actually
hold it below the original thresholds; paired permission alone does not require
a change. Original ordered questions, distributions and evidence windows travel
as complete bound repair data, replacing representative-only feedback. Overflow
refuses the task without clipping the checklist. Complete source catalogs stay in
task data and every parent source, identity, privacy and semantic check still runs.
The same opt-in binds fresh empty-selection plans and their sole structural
correction to the exact parent kind/version/schemaVersion and five identity
values, empty operations, and bounded project text/catalog or preference output.
Optional citation roles and ranges remain explicit alternatives. Other models,
selected-record plans and repair modes outside these profiles keep their contracts. Controlled wire tests do not prove gateway acceptance; an
actual service refusal remains a recorded failure, without a fallback or retry.

When an explicit `/memory <request>` encounters private Memory and Jev review
is enabled, Pi asks permission to send the relevant private bodies and task
evidence to TypeSafe Jev for that run. Confirmation happens before source auditing
and selection when private entries are already known, or before semantic review
for a newly proposed private entry. Declining or cancelling preserves knowledge;
headless runs cannot grant permission. A preflight refusal starts no planner and
reports zero added calls/cost, with learning still incomplete. Permission does
not change configuration, carry into another run, or bypass validation.

Mutation counterreviews deduplicate an exact complete predecessor only when that
body already occurs verbatim in an original review text block. The predecessor
then carries an in-state path, UTF-16 range and SHA256; every affected question
requires reading that complete body. Original evidence is unchanged. Partial or
unmatched bodies stay inline, and oversized requests still fail before sending.
This lossless transport change does not establish semantic preservation or learning
benefit; real judgments and later task outcomes remain separate acceptance gates.

Explicit Memory maintenance passes the existing scoped name/description/type/privacy
index into read-only source collection as untrusted discovery context. This saves
rediscovery reads; it neither exposes complete bodies in the index nor turns old
metadata into evidence. Only independently rechecked current-source reads enter
the task slice, with the original eighteen-read limit and semantic gates.

Maintenance source collection also receives a parent-generated bounded regular-file
path inventory (at most 512 paths, 2,048 visited entries, 128 directories and four
levels). It is discovery metadata with explicit truncation, never source evidence.
The maintenance reader accepts regular files only; ordinary planner directory
listing remains unchanged. Known in-scope files omitted from the bounded inventory
remain readable. Source bodies still require actual bounded reads and revision checks.

Maintenance delivery proofs bind each complete current assistant message and its
exact tool results, excluding unused cumulative SDK turn context. Repeated history
is not a new observation. The same two-MiB proof bound, nonce/scope/digest checks,
terminal-stop proof and exact read-delivery checks still apply; oversized required
delivery data remain refused. Older rejected proofs are preserved as failures.

Explicit Memory maintenance uses a source-only collector: Memory names and descriptions identify audit topics, while its read scope excludes managed Memory bodies and indexes. Complete selected predecessors remain in later planning and semantic review. The eighteen-read budget, original task evidence, citation gates and semantic thresholds remain unchanged.

A parent-classified citation failure consumes the existing single structural correction slot with a citation-only amendment. The model selects source refs by complete-candidate-bound ID; the parent preserves every body and non-evidence field. This can repair provenance without claiming the original knowledge is correct: full independent semantic review still precedes any write.

Memory counterevidence windows include the exact unique earlier invocation for their tool results, including results the candidate did not cite. This lets review distinguish execution scope and probe arguments when the invocation falls in another window. Arguments establish an attempt, not its outcome or permission; duplicate call IDs and mismatched tool names supply no provenance. Complete encoded requests still pass the same size and review limits before any service call.

Memory semantic-review transport keeps complete original entries. Duplicate long support quotations may use same-state UTF-16 references with SHA256; a cited entry already present in a counterevidence window is referenced at its original index. Preferred adjacent windows may merge only after full encoded-request checks. Normal project requests have no artificial byte cap; sixteen-window, batch, total-request and semantic thresholds remain unchanged; failure to fit retains proposals without applying Memory.

Memory internal consistency is reviewed separately from source support. An isolated
no-tool worker uses the configured learning model with requested `xhigh` thinking
(Pi adapts this to the model's supported levels). Complete bodies split only between
targets only when an explicit experimental byte bound is supplied. Normal project
requests use service capacity; service rejections hold the plan without trimming.
The parent binds every response to exact body hashes and conflicting text spans.
A held body can consume the existing single semantic correction opportunity; the
replacement must pass both fresh body review and complete Jev source review at
unchanged thresholds before application. Every body-review call adds separately
reported usage, including interrupted and invalid responses. Optional Jev that
cannot start retains its existing explicitly reported mechanical-validation path;
this does not claim semantic review or learning effectiveness.
Body reviewers select request-local integer target slots; they do not transcribe
hashes or durable identifiers. The parent restores both from the immutable complete
request and still rejects missing/duplicate targets and invented conflict spans.
Explicitly opted-in Qwen structured output also covers these independent workers:
one required judgment property per complete target slot prevents repeated or omitted
slots on the service wire. Legacy array responses still require exact coverage;
neither contract establishes source truth or authorizes a mutation.

Literal command-family review can prove optional leading ASCII spaces/tabs and
an exact final command-separator class without asking Jev to interpret regex.
A newline between `git` and `push` differs from a newline after `npm`: the latter
still follows an npm invocation. Authorization and every counterevidence window
remain mandatory. This prefix grammar does not cover all Bash syntax, and legacy
stored rules are not rewritten automatically.
Private response artifacts retain non-sensitive complete bounded output to separate
framing/selection failures from wrong semantic judgments. A correctly bound model
answer alone is not evidence that the knowledge is correct or useful.

The request-capacity protocol changed by explicit user instruction: normal project
learning no longer imposes the historical 64,000-byte wire/prompt cap. Earlier
bounded failures and costs remain valid evidence of those earlier protocols.
Count limits, complete evidence, privacy checks, timeouts, 0.9/0.8 thresholds and
fail-closed service handling remain in force. Removing a capacity gate is not
learning success.

Selector responses with observed positional aliases, a well-formed rationale and
the exact current digest may request one fresh structural answer. Aliases never
become routing decisions; stale identity, invalid positions and repeated malformed
responses remain failures with their costs. Native maintenance reports separate
model and Jev requests from the inclusive transport total.

Retention reviews carry each complete old body in its own question, rather than
duplicating the entire retained corpus in shared request state. Complete original
evidence remains windowed and reviewed; mutation preservation still receives all
required old and replacement bodies. This avoids redundant context that caused
actual Jev `max_tokens_exceeded` failures without weakening semantic admission.

When a mixed plan fails citation resolution before deletion preservation can be
checked, semantic-review-enabled deletion proposals use the existing structural correction
slot with candidate-bound amendments. Only an original selected deletion may
supply a complete replacement body; unaffected candidates remain byte-identical.
Evidence-only amendments must not lock an unvalidated deletion into place. The only reconsideration remains delete to same-name rewrite;
parent privacy, source citations and complete preservation review still apply.

A successful planner process that returns only bounded empty provider tool
delimiters can use the existing single structural correction slot for one fresh
frozen-scope answer. Delimiters never establish a tool action or mutation intent;
new proposals remain private, and ordinary citations, scope, privacy and semantic
validation still apply. Other prose, commands, multiple plans and transport errors
do not enter this recovery path.

Normal-project Memory mutation counterreviews review one candidate per
request, while retaining each candidate's complete cited source entries, exact
predecessor/replacement bodies and transitive preservation dependencies. Every
candidate still receives every original evidence window. Explicit finite-byte
historical replays retain their earlier grouping. Smaller requests increase call
counts; normal mutations admit at most 32 candidates and preflight their complete matrix
(at most 32 × (16 windows + support + novelty) = 576 prepared requests; historical
and other modes retain 68), which can still reject a complete plan, and
service token limits can still reject an individual request. This transport
partition does not establish learning effectiveness or relax semantic admission.

General Memory organization requests target source-backed corrections, rather than
rewriting every selected record into a shorter summary. The planner must identify
the particular incorrect claim, preserve unrelated knowledge and conditions, and
cite necessary original sources. Complete evidence review and semantic gates are
unchanged; this prompt contract alone is not evidence of useful learning. When original task scope and successful paired source reads support it, the existing
semantic repair may distinguish the current observation from a short earlier
observation. It must cite both original sources, retain material conditions, and
respect revocations, privacy and temporary restrictions. This optional wording
adds no repair attempt or approval; uncertain records remain held.

Citation generation preserves empty/whitespace source text and positions without
offering those fragments as selectable evidence. Meaningful ranges retain their
intervening whitespace; older non-empty ranges with whitespace endpoints remain
compatible with the unchanged parent quote and semantic gates.

When a later Jev request fails, completed requests can still supply held-field
feedback bound to the exact frozen evidence, predecessor bodies and candidate
plan. This uses the existing single semantic correction slot. The original
transport failure and incomplete costs remain visible; no passed fields or
partial admission are inferred. The entire corrected plan must pass fresh
complete source and body review before application.

Combined correction must explicitly cover both held proposals and held retained
records. A contradiction confirmed at the original 0.9 probability and 0.8 confidence
thresholds requires a source-backed text change; repeating the same inconsistent text with different citations remains a
failed correction. Support-only review may still accept unchanged correct text
with better original citations after full review. These requirements reach both
sparse and combined correction workers, and do not establish learning benefit.

Explicit maintenance gives the source collector complete, revision-bound old
Memory claims as untrusted questions, so its source reads can investigate actual
claims rather than filenames and descriptions alone. These bodies never enter
observed evidence. Sensitive files, symlinks, invalid UTF-8 and oversized entries
stop collection before external work. Claims are rechecked before writes;
source-only post-apply checks allow the plugin's own validated correction.
The source tool scope and eighteen-read budget stay unchanged.

Mixed semantic correction uses candidate-bound amendment patches for proposed
rewrites and new entries, plus separately scoped operations for held retained
records. The parent restores proposal names, kinds, privacy and ordering. Opted-in
structured workers receive the complete candidate-ID domain as an enum; duplicate,
stale or foreign patches and proposed records placed in retained operations fail.
Legacy full-plan replies keep their original validation, including rejection of
new proposals regenerated as existing rewrites. Full semantic review still follows.

Semantic workers can select an exact short `candidateRef` when the parent provides
one. Before generation, the parent captures the complete proposal SHA256 and its
reference-to-full-ID map. It checks that binding and the complete frozen snapshot
again before resolving a reference. Mixed selectors, duplicate targets, changed
proposals and foreign references fail. Full `candidateId` values remain exact;
the parent never guesses a malformed ID. Citation-only workers cannot use these
references. This interface avoids asking a knowledge correction worker to copy
long digests; it does not approve the resulting claims.

A low-confidence coherence judgment is uncertainty, even when its preferred label
is contradictory. It cannot force changes to possibly correct knowledge. Such
fields remain held and receive the same complete review before any application;
removing an unjustified change requirement grants no semantic approval.

For parent-proved literal command-family prohibitions, each complete counterevidence
window receives two mandatory judgments: changes to permission in original user
messages, and factual contradictions in the complete rule explanation. Both must
pass the unchanged probability/confidence gates. Tool results and assistant text
cannot grant permission; verified observations can still refute factual claims.
Other regexes and correction candidates retain their existing review.

Independent Memory consistency review explicitly compares the separately retrieved
frontmatter description with the complete record, including declarations. A
whole-record hold cannot certify an unquoted description as passed: the existing
single correction may reconsider body and description, while names, privacy,
observations and fresh source/citation/semantic gates remain bound. It may select
new citations from the same complete frozen evidence. Prefer a complete supported
body sentence for index descriptions to avoid introducing facts through compression.

For durable source contracts, generation guidance favors the exact inspected
declaration with brief attribution over multiple prose restatements. The index
can identify the declared API and source file while the body preserves its full
type structure. This changes generation guidance, not evidence or semantic gates.


Legacy private project proposals retain `sourceExcerpt: {ref, endRef?}`
compatibility. The parent requires a successful original project `read` or
complete added lines from a uniquely bound successful `edit`, matching candidate
evidence and unchanged current source bytes. It copies the exact excerpt and
supplies a neutral file description before complete-record and semantic/privacy
review. Protected directories, symlinks, stale excerpts and source changes around
application remain rejected. Parent-enabled semantic correction of a held private
body also retains its separate `sourceExcerpt` alternative described above.
Fresh project generation uses `knowledge` and the source-selection contract above,
for both safe and private records. Supported maintenance purpose and applicability
conditions use cited text units with concise **Why** and **How to apply** context.
Preferences keep their current representation. Do not invent a purpose,
currentness guarantee or runtime behavior. This generation policy does not migrate
old records or establish learning benefit.


Operators may set `plannerThinkingLevel` in the agent's `continual-learning.json`
to a Pi thinking level (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`).
This explicit generation setting applies to isolated learning planners and repairs;
absent configuration preserves the model default. Independent complete-record
review retains its existing reasoning and deadlines, including an accuracy-focused
contradiction repair override. Invalid or unsafe configuration refuses worker
startup. A lower generation setting may reduce latency/cost but must still pass
all source, privacy and semantic validation; it does not establish learning benefit.

Memory source review distinguishes earlier inspected source from a later successful source edit, and still checks later reverts and failed edits. A failed compound command may contain individually evidenced configuration or lint observations; these never establish overall command success, a successful fix, or verified runtime behavior. These are review questions, not parent-granted semantic acceptance.

For compatible legacy private project proposals, `sourceExcerpt` also accepts complete contiguous added lines from an original successful `edit` patch. The parent checks its unique invocation, matching `newText` and current regular source file before removing `+` markers for the body; original patch evidence stays unchanged. Removed lines, headers, partial-line references, failed edits and source drift are rejected. This supplies a candidate only and retains every existing semantic and mutation gate.

Complete manual `/consolidate backfill` now refreshes source observations for
paths from the original task before Memory selection. This addresses tasks whose
last complete source read preceded later edits. The collector is read-only,
cannot read stored Memory or unrelated task files, and adds actual verified reads
without replacing any original evidence. Collection failures remain failures;
all source bindings, privacy and semantic gates still apply. Automatic and
truncated replay retain their existing behavior. Additional collector usage is
included in receipts, and successful collection does not establish a learned fix
or better subsequent tasks.

`jev.requestConcurrency` optionally limits each semantic-review batch to 1–4 concurrent requests (default 4). Use a lower value for a constrained service or unreliable concurrent transport; it does not drop source windows, lower probability gates, increase request bounds, or change per-request deadlines. Lower concurrency may increase total review time and does not by itself prove a transport fix or learning benefit.

Normal coverage-enabled body correction uses `knowledge.sourceCitations` and ordered `knowledge.units`. The parent derives the complete body and its citations together and preserves frontmatter. The final worker input retains the shared knowledge output contract once, including material dependencies, independent named-type requirements and the distinction between declarations and observed behavior. Atomic framing changes the output format, not that content contract. Units and matching citations do not prove that a correction is complete or useful; every fresh review gate still applies.

For non-atomic semantic Memory amendments, `content` is a complete replacement Markdown document, including name/description/type frontmatter and the full body. Its structured-output schema matches the parent document requirement; a body-only paragraph is not a complete amendment. Identity, protected metadata, source citations and fresh complete review remain mandatory. A content patch may omit unchanged evidence only when the parent explicitly grants original-source reuse for that candidate. The parent checks the exact candidate ID and frozen snapshot hash, run and scope, resolves the complete original citations again, and preserves locked fields. Explicit invalid evidence and an unchanged effective patch remain rejected. This supplies a candidate for fresh review, never a learned change or approval. Citation-only amendments still require evidence. When parent-bound source observations are available, correction generation receives the reviewer's validated same-path read-order links alongside the complete original evidence. The links establish provenance only. They do not establish semantic supersession, runtime success or user permission, and old Memory remains a correction target. Invalid source bindings stop generation before a model request. Fresh full review must still reject a repair that restores an obsolete declaration while citing newer source.

Semantic Memory repair and independent body review share the recorded
`MEMORY_CORRECTION_WORKER_DEADLINE_MS` budget of 600 seconds (ADR 0009), with
parent cancellation propagated to the child process group. The Harness
correction path keeps its own 230-second bound, and every semantic threshold,
request bound and retry policy is unchanged. Timeout retains the rejected
proposal, both parent-controlled lifecycle markers and partial usage; it does not
admit a mutation or trigger another planner retry. Failed
continuous studies reconcile retained receipts and worker ledgers by identity,
including body review and source collection. Known costs are lower bounds when
calls were interrupted; receipt processing and writes do not establish learning
benefit.

Normal project Memory semantic reviews send complete values directly: knowledge
bodies, exact predecessor bodies and original cited quotes remain inline, with
separate description checks and complete Markdown in mutation context. Historical
studies with an explicit request-byte bound retain their original lossless pointer
encoding. Source coverage, privacy, preservation, thresholds and deadlines remain
unchanged. This improves the review interface; a transport regression check does
not establish semantic accuracy or downstream learning benefit.

For normal unbounded Memory rewrites and deletions, every counterevidence window
also receives relevant complete parent-bound current-source observations and
their original invocations. Both predecessor and replacement text may nominate
source paths; that match supplies comparison context only, never support,
preservation or mutation authority. Retention already uses this comparison.
Explicitly byte-bounded historical requests keep their original encoding. A
coverage regression check does not explain an earlier uncertain judgment or
establish that the corrected knowledge improves a later task.

Normal rewrite/delete review also receives parent-computed exact quote comparisons
for uniquely paired successful reads with the same supplied path. Code reports
whether the full cited string occurs inside an individual original text block in
each observed version. A missing match does not prove absence from the file.
The facts stay scoped to the reviewed candidate; they do not establish source
identity, meaning, supersession, runtime behavior or permission. Every original
semantic gate remains required, even when the current quote matches exactly.
Separate blocks are never joined to manufacture an exact match. Finite historical
wires remain unchanged. This is comparison data, not demonstrated learning benefit.

Normal rewrite review also includes exact unmatched line occurrences from the
complete old and new Markdown. These comparisons count duplicate lines and keep
line endings. They ignore order. Review must still judge whether changed wording
is superseded or rephrased, and whether unchanged wording keeps its meaning in
context. Complete records, original evidence and every semantic gate remain
required. Historical byte-bounded requests keep their original wire.

Source excerpts and quotations do not make comments or documentation true.
Learning and correction compare that wording with current user requirements and
complete source observations. Declared API knowledge should retain the complete
supported declaration and its owning type without misleading commentary. A
material documentation mismatch may remain an explicitly unresolved observation
with its original evidence; it must not become a claim of verified behavior or
a successful fix. Atomic submission and semantic thresholds remain unchanged.

Normal source-comparison requests also name the original invocation/result indexes
of earlier successful reads and later parent-bound reads with the exact same
supplied path. The relationship records observed order only: it does not establish
file identity, semantic supersession, truth or permission. Failed, ambiguous and
different-path reads cannot supply this relationship. Complete original results,
every evidence window and later corrections remain required. Historical requests
with an explicit byte bound retain their original encoding.

Candidate-bound semantic repairs require the complete amendment envelope: kind, version and every exact parent identity value remain mandatory alongside replacements. Patch-only field restrictions apply inside replacements, not to that envelope. Missing identity stays rejected; the parent never infers or attaches it, and corrected content still requires full source and semantic validation.

Candidate-bound corrective generation disables extra reasoning only for known description-only patches after complete bodies passed independent consistency review. Body holds from source support, permission or predecessor preservation retain high reasoning even when internal consistency passed. Retained-record correction, unknown held fields and contradictory or uncertain bodies also retain high reasoning; structural planning keeps its configured setting. This changes generation effort, not validation: corrected documents still need fresh independent body review, full original-source semantic review and the same thresholds and deadline. Native wire delivery alone does not prove the service honored the setting or that learning improved.

An amendment that reconstructs the complete rejected proposal without an effective change remains unresolved. The parent checks this after source selection, citation resolution and protected-field restoration, before another semantic review. It preserves the repair output and usage. Changed source or citations still need fresh review; uncertainty does not require arbitrary paraphrasing.

Memory selection binds a canonical map of complete file hashes. Directory traversal order changes during mirror normalization do not invalidate unchanged files; changed, added or removed entries still reject the stale selection. Frozen dossier byte hashes remain exact.

Normal Jev review requests `TypeSafe-Danger-Zone-Long-Context: true` on the first call so complete original entries can use the configured service's supported larger context. Set `jev.longContext: false` in `continual-learning.json` to keep the service default. Explicitly finite-byte historical studies keep their original context mode. This adds no retry, evidence trimming, threshold change or mutation authority. TypeSafe documents a 262k-token long context, with possible latency and accuracy costs; service acceptance still needs full semantic/body review and later real-task verification. See [TypeSafe models](https://docs.typesafe.ai/models). The V40 exact 132,837-byte rejected request was reconstructed by hash and independently diagnosed as `max_tokens_exceeded`; its failed plan and unknown service cost remain retained.
