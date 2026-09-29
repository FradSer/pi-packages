# pi-continual-learning

Learns durable Memory and scoped Harness rules from completed user tasks.
Model weights are out of scope.

- **Memory** supplies a bounded relevance index before generation. Full entries
  are read only when needed; omitted entries remain discoverable.
- **Harness** uses one flat `rules` list for new declarations: `skill` and `text`
  deliver scoped guidance, while `bash` supplies messages and optionally confirms
  or blocks a command before execution. Installed legacy policies retain their
  original protections through read-only compatibility.
- **AGENTS.md consolidation** keeps common project instructions small and moves
  detailed knowledge into Memory or skill rules, retaining conditional pointers
  when needed.

## Install and commands

Python 3 must be available as `python3` for the bundled Memory validator.

```bash
pi install npm:pi-continual-learning
```

| Command | Purpose |
| --- | --- |
| `/memory` | Manage model, instructions, memory folder, auto-memory, phase policies and history |
| `/memory policy [memory\|harness\|agents] [apply\|propose\|off]` | Inspect or set automatic learning policy for one phase |
| `/memory history [change-id]` | Inspect private project change history or a recorded proposal |
| `/memory undo <change-id> [--yes]` | Restore one applied change after preview and conflict checks; headless use requires `--yes` |
| `/memory evaluate <suite.json>` | Compare supplied baseline/candidate rules against independent cases, without model calls |
| `/consolidate` | Learn incrementally from the current completed Task Slice |
| `/consolidate full` | Explicit full-corpus maintenance |
| `/consolidate no-context` | Full Memory maintenance without task evidence; skips Harness and AGENTS.md |
| `/harness` | Show rules and configuration diagnostics |
| `/harness <request>` | Create or update a project-shared rule |
| `/harness --local <request>` | Explicit personal project configuration |
| `/harness --global <request>` | User-shared configuration |

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
2. `<project>/.pi/harness.json` — project shared and default authoring target.
3. `<project>/.pi/harness.local.json` — explicit personal choice.

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
Routine tasks launch no learning model. A metadata-only selector chooses the
minimum sufficient existing Memory and relevant phases for the current Task
Slice. Selected bodies and task evidence form one authoritative Learning Dossier.
Only explicit full maintenance explores the whole corpus.

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

An explicit `/consolidate` always reaches selection, including tasks without
automatic-screen keywords. Explicit continuation prompts retain the original
request and its evidence. Task slices preserve complete entries within their byte
budget, report omitted entries, and reject an oversized original request rather
than clipping evidence. A failed tool invocation followed by a successful check
is eligible for Memory review; the planner still must justify a durable lesson,
and a reviewed selector verdict is not overridden by that recovery alone.Harness evidence means Harness-owned transcript evidence: guardrail event
entries, Harness guidance delivery, and the notes Harness attaches to tool
results. Repository text that merely mentions policies or harness files is not
evidence, so it starts no planner.

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

Applied mutations and proposals are recorded privately under
`<agent-dir>/memory/history/<escaped-canonical-cwd>/`. History includes exact
before/after bytes, including indexes and mirror repairs. `/memory history`
lists the latest 50 records; passing an id shows a bounded preview. Proposal
records are inspection artifacts; running `/consolidate` creates a fresh plan
against current evidence instead of replaying a stale proposal.

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
snapshots, automatic learning disabled, and only the read tool. Authentication is
copied privately from the configured agent directory; the source is unchanged.
The report includes literal-answer success, regressions, latency and observed
token usage/cost; missing prices remain unavailable. Output files are private and
never overwritten. Without `--model`, the configured `memory.json` model is used.
The included synthetic example verifies retrieval plumbing; use representative
held-out tasks for your project. One paired sample per task does not establish
statistical improvement, and this experiment does not test Bash enforcement.

## Judgment shadow mode

Judgment is an optional decision surface that observes the selector's routing
and selection. It answers bounded questions with typed answers and
probabilities; it never authors Memory, Harness, or AGENTS.md content, and that
is structural rather than advisory — a decision answer has no representation for
a body of text.

It is **opt-in and off by default**. It activates only when an API key resolves
from the environment or from the persistent package configuration:

```bash
# environment
export TYPESAFE_API_KEY=...            # optional: TYPESAFE_MODEL, TYPESAFE_BASE_URL
```

```json
// ~/.pi/agent/continual-learning.json
{ "api": { "apiKey": "...", "model": "jev-1.13.0", "baseUrl": "https://api.typesafe.ai" } }
```

The environment takes precedence, so one run can be pointed elsewhere without
editing persisted state. An unreadable file, malformed JSON, an unsupported
field, or a configuration without a key all fail closed to inactive: a
configuration fault never changes what a run produces. The model is pinned to a
versioned id rather than a moving alias, and the version that answered is
recorded, so a threshold tuned against one release is not silently applied to
another.

**In shadow mode Judgment changes nothing.** The selector's selection is the one
that reaches the parent, always. Every run appends one observation record
holding the run's context digest, each verdict and its confidence, the selector's
own answer, and whether the two agreed. Refused connections, throttling,
malformed answers, and cancellation are recorded and otherwise inert: an
observer failing must not stop the observed work.

An observation is a judgment record, not a content record. It carries no
request text and no tool output. It is written beneath the private agent directory, per
project, and **outside both Memory roots** — a Memory root admits only regular
`.md` children, so a sibling log there fails consolidation's privacy validation
and aborts learning. The log is capped and rotated, dropping the oldest
records.

Judgment receives a bounded, code-derived projection — clipped request text, the
regex-classified harness event summaries, repository-relative touched paths,
registered skills, and Memory metadata. Raw tool-result content is never sent.
Candidates carry opaque index-derived identifiers, so an answer can never name
a Memory file: invalid names, wrong casing, and duplicates leave parent-side
validation rather than gaining checks.

**Memory proposals are judged too.** When a validated Memory plan is about to be
applied, Judgment is asked whether each proposal is durable, how far it
generalizes, and which indexed entry it restates if any. **The parent still
applies every proposal exactly as it does today** — nothing is dropped, narrowed,
or reordered. What is recorded is the baseline: how good is a *single* proposal?
That question has to have an answer before anyone can ask whether a planner
should produce several candidates and pick one.

These questions deliberately mix primitives. `noul` alone would leave every
answer without a confidence, and the confidence axis of the observation record is
what distinguishes a settled judgment from a coin flip — so generality is a
`score` and duplication is a `choice`, both of which carry one. Measured against
the live service, a reusable build-command lesson scores 0.62 durable / 1.26
general, a one-off CI flake scores 0.19 / 0.09 at **0.91 confidence**, and a
proposal restating an indexed entry is matched to it with 1.00 confidence.

**One generative model, one judgment model.** Every generative phase — the
Memory planner, the Harness planner, and the AGENTS.md extractor — runs on the
model selected in `memory.json` (`provider/model`). Judgment resolves its own
model separately (`TYPESAFE_MODEL`, or the `api.model` block), so configuring
one never silently substitutes the other. Judgment cannot generate: its request
builder admits only `noul`, `choice`, and `score` questions, so a generative
answer is unrepresentable rather than discouraged, and nothing it returns is
ever passed to an apply or write path.

**Promotion is configuration, not code.** Judgment is shadow-only by default
and stays that way until a surface is named in the configuration:

```json
{
  "api": { "apiKey": "...", "model": "jev-1.13.0" },
  "judgment": {
    "surfaces": { "proposals": "authoritative" },
    "thresholds": { "durability": 0.5, "generality": 1 }
  }
}
```

A threshold compiled into the package would mean turning authority on required a
release and turning it off required a second one — a rollback cost high enough
that nobody would start. Only `proposals` can be turned on, because it is the
only surface whose authoritative behavior is implemented; asking for another is
refused rather than silently accepted, because a switch that changes nothing
would read as authoritative while doing exactly what shadow mode did.

When it is on, Judgment's verdict arrives **before** the parent's validator, and
it can only narrow: the names the parent applies always come from the plan, never
from the model. A failed, throttled, or unanswered judgment **drops nothing** —
a service outage must not become a reason to discard real knowledge. Durability
is a probability (0..1) and generality is a score level (0..3); they are
validated on their own scales.

The receipt's `gate` clause reports what shadow mode has measured, per surface,
and proposes no threshold. The number that matters is not accuracy but how much
real knowledge a wrong judgment would cost: the share of parent-applied
proposals Judgment would have dropped.

**Reading the measurement.** `/consolidate` already reports what a run did, so
the shadow measurement rides that same receipt rather than a second command:

```text
Learning 2 memories applied · input 4415 · cost unavailable
  · shadow judgment jev-1.13.0 · 42 observations · agreement 78%
  · proposals 9 reusable / 3 one-off · surfaces harness-operations
```

An unmeasured rate reads as *agreement not yet measured*, never as `0%` — a zero
would claim the two surfaces never agree, which is a claim nobody has evidence
for. Proposals are reported as a **distribution** (reusable versus a record of
one occurrence) rather than a single verdict, so no one threshold can imply more
than the data supports. A user who has not configured Judgment sees exactly the
line they see today.

Promotion out of shadow mode is measured, not assumed. Committed adversarial and
agreement fixtures gate the package tests, and promotion additionally requires
an agreement rate and an injection-resistance rate read from observations. The
report proposes no threshold; choosing one stays a human decision.

See `docs/adr/0006-judgment-shadow-mode-and-projection.md` in the source
repository for why this observes first and receives a projection.

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

The default injection budget is 6,000 characters. Entry bodies are not injected.
Each body root is declared once and every entry row names its filename, so the
budget reaches relevance metadata instead of repeating an absolute read path per
entry. Descriptions should begin with when the entry is relevant and fit one line
of at most 120 characters; detail belongs in the body. Existing longer descriptions
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
python3 packages/continual-learning/tests/live_smoke.py
python3 packages/continual-learning/tests/live_upgrade_smoke.py
```

The display smoke runs real Pi print and interactive sessions with an offline
scripted provider and disposable roots, without user credentials or network
requests. It verifies Ctrl+O, narrow-terminal wrapping and complete guidance
readback. The live scripts are not collected by pytest.

The learning smoke reuses configured model/auth in disposable project and agent
roots, requires actual learned project rules and receipts, and separately verifies
scoped guidance with a harmless Bash command.
It never replaces failed learning with fixtures or edits real user configuration.
The separate upgrade smoke starts a real Pi process with a disposable old-format
configuration, confirms harmless Bash and unrelated writes execute, and confirms
protected write/batched-edit calls remain blocked while configuration bytes stay
unchanged. The learning and upgrade scripts copy provider credentials into
private temporary roots rather than link to writable user files.

## License

MIT
