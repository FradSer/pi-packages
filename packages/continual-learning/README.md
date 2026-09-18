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
| `/memory` | Manage model, instructions, memory folder, and auto-memory |
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
preserve previous delivery state. Guidance is context, not a guarantee that the
model follows it.

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

The default injection budget is 8,000 characters. Entry bodies are not injected.
Descriptions should begin with when the entry is relevant and fit one line of
at most 120 characters; detail belongs in the body. Existing longer descriptions
are retained when they fit, or visibly shortened rather than silently losing a
late trigger.

The loader reports unique entry counts and file-read omissions; final formatting
reports budget omissions. Discovery pointers name `MEMORY.md` and exact roots
for bounded reads/listing. Indexes are discovery metadata and can be stale;
individual bounded files remain the authority. Parent rebuilds include descriptions
in complete indexes. Loading memory never writes indexes. All retrieved content
is explicitly untrusted reference data, not instructions.

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
