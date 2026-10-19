# Continual-learning development

`pi-continual-learning` is a native extension, not a skill. `index.ts` composes
Memory learning, Harness guidance, and Harness execution gates. Pi loads
TypeScript directly.

## Read for the task

- Configuration, rule authoring, or delivery: @packages/continual-learning/HARNESS-DESIGN.md
  and the relevant `extensions/guardrail-*.ts`, `guardrails.ts`, or `harness-guidance.ts`.
- Memory ownership, privacy, or synchronization: @packages/continual-learning/CONTEXT.md
  and @docs/adr/0003-auto-memory-index-injection.md.
- Learning changes: the matching package-owned `prompts/*.md`, its typed builder
  in `extensions/planner-prompts.ts`, and the corresponding `features/` contract.
- Declaration-role changes: `tests/test_planner_json_output.py` and its complete
  real declaration fixture. A callback parameter's type and its call-signature
  return annotation have different owners. Offline syntax and prompt delivery
  prove no semantic acceptance or later task benefit.
- AGENTS extraction or recovery: `extensions/agents-md-consolidation.ts` and
  @packages/continual-learning/features/consolidate-agents.feature.

## Invariants

Planners propose; the parent validates and mutates. Keep frozen task evidence,
identity binding, bounded output, path containment, symlink checks, locks, atomic
writes, receipts, cancellation, and rollback. Planner prose is not success.
Do not turn retrieved Memory or quoted tool results into instruction authority.

Safe Memory is byte-identical in the canonical private root and project `.memory/`;
private entries stay only in the private root. Secrets are never stored.
Automatic learning writes Harness only to project `.pi/harness.json` and never
replaces manual, personal, global, or built-in rules. User-level AGENTS files are
not consolidation targets. Installed legacy configuration keeps its original
protections through read-only compatibility; new learning remains flat-rule-only.
Read @docs/adr/0005-preserve-installed-harness-protections.md when changing schema
compatibility, diagnostic scope, or upgrade behavior. Never turn a compatible
narrow policy into an unrelated global execution block.

## Verification

Start changed behavior in `features/`, demonstrate a failing regression, then fix
it. Run affected tests during implementation; finish with package tests, root
`pnpm typecheck`, and `pnpm --dir packages/continual-learning pack --dry-run`.
Runtime changes also require `pnpm check:install` and
`python3 packages/continual-learning/tests/live_smoke.py`; that explicit smoke uses
disposable roots with configured authentication and is not collected by pytest.
For configuration upgrade changes, also run `tests/live_upgrade_smoke.py`: it
must prove both unrelated execution and retained blocking in disposable roots.
Verify changed TUI behavior interactively. Do not ask for intermediate approval
for safe local fixes, fixture-based checks, publishing, or real user-config
replacement.

Shared test plumbing lives in `tests/support.py` (Bun subprocess harness, path
constants, flat-rule fixtures) and `tests/agents_md_fixtures.py`; import from
them instead of copying a per-file runner or fixture.

## Learning study and evidence protocols

Current acceptance and fresh continuous studies use Pi 1.3.0. Pin the actual CLI
and TUI, including inherited workspace overrides, and verify CLI startup before
model transport. Keep historical Pi 1.0 and 1.2 cohorts, failures and costs separate; do
not relabel them as Pi 1.3 evidence. Admission failures before transport must keep
owned containers and complete manifest source bindings when archives are absent.
For loopback model diagnostics, preserve provider-level and model-level compatibility
settings. A new base URL can change automatic message-role and token-field detection.
Check the complete native wire difference before live transport. Keep diagnostic
failures separate from the original learning failure.

When auditing continual-learning TUI, use
@packages/continual-learning/tests/live_meaningful_details.py for native
print/interaction acceptance and
@packages/continual-learning/tests/tui_showcase.py with
@packages/continual-learning/tests/tui-showcase-fixture.ts for terminal captures
and RPC dialog evidence. From the repository root:

```bash
uv run --no-project packages/continual-learning/tests/live_meaningful_details.py
uv run --no-project --with pyte --with pillow python packages/continual-learning/tests/tui_showcase.py /tmp/continual-learning-tui-cases
```

Inspect the showcase `manifest.json`, PNGs, `.txt`, `.ansi`, `events.jsonl` and
`rpc-dialogs.json`. The showcase uses actual product components with isolated
fixture data; it does not perform real undo, policy writes or remote learning.
After a user reloads Pi, also reproduce the reported case in that reloaded
session; an isolated process is not evidence that their session loaded the fix.

For first-use Harness authoring, run
@packages/continual-learning/tests/live_harness_first_run.py with a disposable output
parent. The offline provider exercises rejected preview, corrected preview, one
complete write, readback and fresh-session revision delivery. `--real-model`
repeats the original `/harness 避免后续 D0 的流量被打爆` request with the configured
provider and records every call and reported cost without accessing D0. Admit
`harness_preview` explicitly when using a CLI tool allowlist; the command activates
this read-only tool and authoring completion removes it. Keep plain positive,
unrelated-action, same-action/different-resource and near-name negatives. A
syntax-valid selector, saved file or delivered guidance alone does not establish
scope correctness or enforced traffic limits. Preserve failed runs, including
acceptance withdrawn after stronger counterexamples; never broaden the filesystem
allowlist or remove failing cases to manufacture a pass.

For Harness extraction failures, retain the fixed parent category and private run-bound
`harness-initial-output.json` / `harness-repair-output.json`. Sensitive or deeply
encoded credentials require hash-only retention; a missing archive is missing evidence,
not permission to infer the error or regenerate a held plan. Archive failures must
not erase the rejected attempt or its usage.

For intermittent AGENTS learning failures, use
@packages/continual-learning/tests/live_agents_reliability.py with `--full-pipeline`.
Retain actual planner-child transport, receipts and before/after documents in
disposable roots. A successful retry does not identify an earlier failure's
cause. Check that every required dossier read is actually authorized, rather
than inferring it from a final applied outcome. Receipt diagnostics must use
parent-controlled categories, never arbitrary child stderr or model output.
For large repair contexts, also run
@packages/kit/tests/test_large_worker_prompt.py. Native Pi stdin trims boundary
whitespace; prove exact prompt delivery through the actual CLI, not only a fake
stdin reader. Reproduce Linux argument-limit failures with the original frozen
evidence before changing transport; reducing evidence is not a transport fix.

For downstream Memory claims, use
@packages/continual-learning/tests/live_real_project_memory.py and its frozen
@packages/continual-learning/tests/real_project_tasks.py protocol. Run
`--preflight-only` before real calls. This Docker study enables Jev only in its
isolated configuration, learns from real source work, and starts fresh sessions
with identical post-training code. Hidden checks enter containers after model
execution. Preserve failures and ties; invalid training must stop downstream
tasks. Small authored feature tasks on previously used public projects do not
establish broad model capability or production benefit.
After a confirmed learning runtime fix, `--resume-from <prior-cohort>` may reuse
verified real source observations instead of repeating the audit. Keep the
original project/model/protocol and source hashes, use the existing `continue`
contract. For a summary-only continuation, replace the parent tool allowlist with
`--no-tools`; a prompt-only ban can loop, and combining it with `--tools` reopens
those tools. Independent learning workers keep their own explicit authorization.
Require `originalObservationsPreserved=true` in the actual learning
dossier. A new substantive summary request starts a new task slice and is not
proof that old tool evidence was reviewed. Record failed cohorts, cumulative
resumed usage and the changed protocol; never seed Memory or future answers.
For citation failures, compare raw dossier entries with the frozen snapshot before
assuming an offset bug. Incremental Memory model inputs label each unchanged entry
with its original `snapshotIndex`; validate against raw evidence, not the display
projection. For long encoded verifier-line citation changes, also run
`uv run --no-project packages/continual-learning/tests/live_memory_citations.py`.
It drives actual Pi 1.2 scoped reads with a deterministic local provider and
checks complete chunk reconstruction, exact parent extraction and unchanged
source. This proves the citation interface only, not model selection or learning
effectiveness; keep failed whole-line/partial-quote plans rejected.
For metadata-only Memory failures, retain the original plan and use
@packages/continual-learning/tests/test_memory_required_body.py. Reject empty
knowledge bodies before semantic review for creates and rewrites, while preserving
legacy non-empty records and the existing single structural correction slot.
Metadata is discovery, never a substitute for source-grounded knowledge.
For missing Memory use, distinguish session sections from actual completions wire
with @packages/continual-learning/tests/live_memory_reference_reuse.py. Record
system/developer marker presence and hashes, never private text. Wire discovery
proves delivery only; require successful full revision reads and later behavior
for consumption and benefit. Do not force reads or inject bodies for coverage.
For initial Memory JSON serialization failures, run
@packages/continual-learning/tests/test_memory_generation_whitespace.py. It replays
an actual strict-schema response through native Pi and the complete parent
transport extractor. Recovery preserves exact string values and rejects multiple
drafts, output limits, truncation, failed termination and foreign identity. A
successful native retry requires its complete explicit lifecycle proof; prior
errors and usage remain retained, and recovery adds no retry. The
fixture is format evidence only; never seed it into a learning arm or infer
semantic acceptance or downstream benefit from successful parsing.
For producer schema size, run
@packages/continual-learning/tests/test_memory_schema_references.py. Local
references may share the complete citation catalog only when expansion retains
every original constraint and choice. Measure the complete encoded request;
smaller encoding does not prove service reliability or learning benefit.
For Jev bounds, measure the fully encoded wire request, retain the
rejection, and never trim original evidence or lower thresholds to manufacture
a valid experimental arm.
For large selector failures, also run
@packages/continual-learning/tests/test_jev_selection_windows.py. Selection windows
preserve every complete original entry in order, including final revocations;
window unions only nominate later full review and never authorize mutations.
A failed, cancelled, uncertain or unreviewed window keeps fallback. Screen all
original evidence for privacy before the first window request, stop transport
failure from spending later windows, and retain partial usage and unknown prices.
A preferred byte window is not proof of token capacity or a historical HTTP400
cause; bind a reconstruction to the actual wire hash before attributing that cause.
For semantic transport resets, retain fixed TCP/TLS/response progress and byte
counts from @packages/continual-learning/tests/jev-https-forward.mjs and verify
@packages/continual-learning/tests/test_jev_transport_phases.py. A successful
current handshake, a later successful identical request, and a prior connection
reset are separate observations. Never infer a historical TLS or billing cause,
change trust/routing, or add retries merely to turn the experiment green.
For a source review recovered by its existing bounded transport retry, run
@packages/continual-learning/tests/test_jev_transport_recovery.py. Failed attempts
remain counted and may have unknown costs; complete logical requests still need
every original window and exact checklist. A successful retry must not suppress
the separate independent body review, and a missing answer or uncertain verdict
must never acquire completion or mutation authority.
For the privacy preflight, run @tests/test_jev_learning.py,
@tests/test_learning_controls.py (TypeScript guard and packed validator pinned
against the shared corpus) and
@tests/preflight-false-positive-verification-2026-10-19.json. Documentation
placeholders are exempt in text only: the Memory guard and the Jev preflight must
classify the same text identically, a credential-named structured object key stays
strict, and a quoted value containing punctuation such as `,`, `;`, `?` or `//` is
refused. Never add a placeholder allowlist entry, widen a pattern class or relax a
class rule to obtain a write. Re-measure over retained dossiers before claiming a
false-positive rate.

For isolated semantic-service TLS failures, exercise
@packages/continual-learning/tests/jev-https-forward.mjs with
@packages/continual-learning/tests/test_jev_https_forward.py before paid calls.
The optional Node study transport retains the original URL/Host/SNI, strict
certificate-chain and hostname verification, and routes only via lookup. Parent
validation admits public IPs only; forwarder environment must exclude TLS/CA,
proxy and Node option overrides. Keep one attempt, no redirects or retry, the
30-second absolute deadline and 35-second process bound. Preserve the old Bun
cohorts, exact request hashes, fixed TLS failure codes and all costs. Record the
actual selected transport in protocol evidence and freeze its complete sources.
Local trusted/wrong-host/untrusted/hanging TLS proof does not identify the remote
certificate failure's cause or establish learning benefit.
Before settling any paid study, close admission atomically and wait for every
counted forwarder, including its usage accounting, to reach quiescence. A stopped
accept thread is insufficient. If quiescence cannot be confirmed within the
existing process bound, retain the exclusive reservation and write the partial
failure/cost evidence; never release it based only on daemon-thread shutdown.

For opt-in public-study Jev envelope evidence, use `--capture-jev-envelopes` in
@tests/live_continuous_project_learning.py and exercise @tests/test_docker_experiment.py.
Capture admitted request bodies and safe typed response buffers without headers.
Keep the existing privacy authorization and full sensitive-data screen; checking
known transport credentials is not a general secret detector. Bound capture
memory separately from wire capacity and write 0600 files in a fresh 0700
directory after quiescence. Missing, unsafe, partial, oversized or unwritten
buffers remain unavailable, without changing transport, retries, deadlines,
counting or costs. These are UTF-8 proxy buffers, not arbitrary upstream TLS
octets. Captured encodings or answers alone do not establish learning benefit.

For ordinary study Bash authentication isolation, use
@tests/test_continuous_tool_budget.py and @tests/continuous-bash-environment.ts.
Keep the parent Jev credential available to the SDK; omit it only from native
Bash child environments in both arms. Keep tool schemas, commands and session
metadata unchanged. Verifier-only reads gain no Bash tool. This is not a
filesystem sandbox or a general secret filter. Original sensitive evidence
still blocks learning. Keep a fixed setup diagnostic and zero generation calls
in that failed receipt; exercise @tests/test_manual_memory_request.py. Never
weaken privacy or scrub original evidence to obtain a write. Exported archives
can redact transport credentials; compare their hashes with original manifests
before calling them exact-input replays. The V69 controlled replacement proves
the refusal path only; it is not an exact reconstruction or learning benefit.


For private Memory maintenance, run
@packages/continual-learning/tests/live_private_memory_consent.py with a disposable
output parent. It exercises actual workspace Pi `/memory 整理记忆` through native
PTY cancellation and an id-bound RPC refusal, with external requests forbidden.
Require zero planner runs, unchanged Memory and unchanged privacy configuration.
Controlled consent/write tests establish authorization wiring only. Never reuse
public-project experiment consent for a different private project.

For explicit maintenance source collection, parent-provided complete old bodies
are untrusted verification questions, never independently observed facts. Keep
them out of appended source evidence and the collector's source read scope. Bind
their safe revisions before writes; source-only post-apply checks must permit
the plugin's own authorized corrections.

For Memory maintenance bounds, replay the actual rewrite/delete mixed plan and
its frozen selected predecessor bodies; a create-only test does not cover this
path. Verify every original entry is reviewed, including final revocations.
Normal project learning delegates request capacity
to the configured service without a local request-byte cap. Historical bounded
studies must explicitly retain their original `maxRequestBytes` and transport
bound; record an authorized protocol change separately, preserving prior failures
and costs. Removing a local capacity gate does not establish semantic acceptance
or learning benefit. Preserve each historical study's count limits. Normal mutation
review explicitly uses at most 32 candidates, 16 complete windows and 576
prepared requests. The total includes independent body-only consistency, support
and novelty jobs; the joint maxima need not fit together. Reject excess work
before transport. Record this separately from the old 68-request bound. Keep deadlines and 0.9/0.8 thresholds unchanged.
Mutation reviews require operation/preservation intent,
exact old bodies and same-plan replacement bodies; none of that state authorizes
the mutation. An all-positive offline judge proves framing and coverage only.

For initial-generation raw JSON string regressions, the same native full-path
runner accepts `--raw-memory-json` in offline mode only. Require its
`generationSerializationRecovery` report, complete safe original transport, no
extra repair call, applied receipt and exact undo restoration. This is mechanics
evidence, never real-model or semantic learning evidence.

For a learning/history/undo acceptance request, also run
@packages/continual-learning/tests/live_learning_history_undo.py:

```bash
uv run --no-project --with pyte --with pillow python packages/continual-learning/tests/live_learning_history_undo.py /tmp/continual-learning-full-path
```

This drives the real Pi CLI, planner children, parent validation and file writes,
then native history/detail menus and undo confirmation in one disposable project.
Each invocation creates a new private run directory under the supplied output
parent and prints its `outputDir`. Inspect that directory, not an older sibling.
The runner uses the installed workspace Pi CLI and records its version, so a
global CLI upgrade cannot silently change the compatibility baseline. It checks
isolation before spawning Pi, snapshots source hashes at startup,
refuses a pass after source drift, and automatically writes a manifest, run log
and gallery on success or failure. Freeze implementation before the final run;
stabilize deterministic acceptance and obtain required independent review before
calling a real provider. Re-run checks only for affected changes or unresolved
failures. Dialog evidence must match the current dialog id and event offset.
It also resizes the same history list between 120 and 48 columns and checks that
applied and undone statuses remain readable.
Its loopback provider is deterministic; explicitly disable Jev in the disposable
agent configuration and whitelist inherited environment variables to keep remote
services out of this offline run. Verify rendered results against receipts,
history targets and actual bytes. Bind cancellation evidence to the current
dialog; undo every applied record in reverse order, including index bootstrap
records. Compare predecessor bytes, permissions and missing files, retain undone
history and the original receipt, and preserve unrelated files. Inspect
`manifest.json`, `snapshots.json`, `receipt.json`, both history JSON files,
`events.jsonl`, raw terminal bytes and reconstructed images. This proves the
learning/undo mechanics with controlled plans; report real-model learning and
remote semantic review separately.
The optional `--real-model` flag runs the same native path with the configured
real provider for Memory only, copying auth into the disposable agent directory
with private permissions. Use it for real-service verification; it may incur
model usage. It retains synthetic receipts and terminal evidence,
never credentials. Jev remains disabled, so this does not verify remote semantic
review. A failed real-model receipt remains a failure, separate from loopback
acceptance.

For continuous-learning effectiveness, use
@packages/continual-learning/tests/live_continuous_project_learning.py and the frozen
@packages/continual-learning/tests/continuous_project_tasks.py protocol. Run
`--preflight-only` first. It resets disposable project/agent state, never seeds
Memory or Harness, converges source bytes before each paired fresh-session task,
and preserves actual learned state only in the learning arm. Hidden probes enter
after model exit and are removed before the next task. Source convergence is an
experimental intervention, not independent project evolution. The standalone version-execution instruction belongs only in correction and retirement
tasks; a conditional shared instruction caused both orientation models to execute it
prematurely and is retained in the earlier cohort. Record invalid
learning, task failures, explicit recovery, all known leader/learning/Jev usage and
unknown interrupted costs; never turn one sequence into a broad capability claim.
Freeze implementation and obtain required independent review before paid calls.
When other tasks share the checkout, use a byte-verified, read-only copy of the
complete runtime and study sources for both imports and runtime image creation.
Run preflight against that same copy and retain its source hashes; do not waive
source-drift failures or treat them as evidence of a learning benefit.
Bind paid admission to the exact preflight run and wrapper digest. A no-call
preflight must enforce a zero transport budget. Acquire exclusive budget
ownership before reading the cumulative ledger, and preserve reservations on
uncertain interruption rather than reusing unaccounted requests.
For recovery file identities, run @tests/test_recovery_integrity.py. Fresh live
captures retain the native history's complete physical revision and compare it
at every link and endpoint. Archive bytes bind to live digest, mode and size;
tar does not prove inode identity. Keep historical snapshots and failed outcomes
unchanged; never strip revision fields or infer missing historical identities.
The continuous protocol permits one bounded explicit backfill after initial learning
if pending, retaining the original failures and recovery cost; invalid learning
then stops dependent tasks. Read actual backlog status rather than inferring pending
work from attempt files. On interruption retain sessions and ledgers before removing
owned containers; known summaries may be incomplete, and missing usage is unknown.

For a new prospective observed-failure study, `--verified-failure-learning` adds an
explicit version-2 path. It separates an original task failure from independently
validated learning after feedback. Keep the default successful-diagnosis path and
all historical outcomes unchanged. Require a normally settled original native
branch, safe unchanged source in both arms, a complete native feedback proof,
exact backlog acknowledgment, zero pending work, complete receipt-owned physical
history and substantive failure knowledge. Recompute source-extension proof from
the complete plan, snapshot, manifest, observations and bound usage ledgers before
semantic transport. Preserve individual 0.9/0.8 and conservative joint 0.9 gates,
all type/Harness/privacy checks, and the one-backfill limit. Invalid training still
stops later tasks. Never reinterpret a failed main as successful, import old learned
state, rejudge held plans for approval, or infer later use or benefit from admission.
Exercise `tests/test_continuous_project_protocol.py` and native offline evidence,
then freeze and independently review a fresh preflight before paid execution.
The revised study loads @packages/continual-learning/tests/continuous-tool-budget.ts
only in each arm's parent task process: eighteen admitted calls, then an empty
active tool set; excess in-flight calls are blocked and make the task fail. This
experimental resource intervention is identical in both arms, preserves original
observations in the same session, and does not constrain independent learning
workers or explicit backfill. Retain prior prompt-only-budget cohorts and disclose
the changed protocol. Verify the empty next-turn tool set through the actual Pi
CLI with @packages/continual-learning/tests/test_continuous_tool_budget.py before
paid calls; do not treat prompt wording alone as a hard budget.
For requested version-permission checks, match the standalone `npm --version`
call to a unique successful actual Bash result with a version. Attempts, assistant
claims and a later pure rule-engine probe cannot satisfy the task. Record the
complete common prompt and this stricter protocol separately from prior cohorts.

Continuous coverage version 2 adds a sixth real wrapper-maintenance task after
Memory correction. Actual failed verification is read once from a complete,
source/session-bound file through `continue` in the original session, with only
one read available in both arms; this is observed evidence, never seeded Memory
or user authorization. One explicit bounded backfill may process this failure,
retaining the failed task and all added costs. Require exact acknowledgment
SHA256 of JavaScript `JSON.stringify(receipt)`, the receipt's parent mutation batch
in applied history, and subsequent consumption of the changed knowledge. A
zero-operation acknowledgment proves processing only. Require independent Jev
old/new Memory versus complete current source auditing at unchanged thresholds
and later exact-revision delivery for correction coverage. Missing coverage is
`incomplete-coverage`, even if all task processes exit. The experimental audit is
read-only and its real service usage belongs in cumulative costs.

For Pi 1.2 retry-session replay, run
@packages/continual-learning/tests/test_recent_learning_input.py with its real
`real-pi12-timeout-context-edit.json` fixture. Accept only exact null removals of
earlier empty assistant errors. Strip removed metadata before returning indexed
context, validate wrapper timestamps, and preserve the original source/task
hashes and evidence prefix. Refuse meaningful edits and projectionless readers.
This establishes replay safety only; keep original failures, costs and every
semantic learning gate.

For same-task failure feedback, inspect actual pending backlog ranges and the
`input.backlogCoverage` of replay receipts. Only independently digest-verified,
byte-identical prefix extensions may share one learning call; a new substantive
task or changed source cannot be substituted. Preserve each original failure and
one cost-bearing receipt. Exercise acknowledgment crashes before any sibling,
between siblings, and before the receipt owner, plus recovery before older retry
selection. A truncated replay must retain omission metadata and its existing
proposals-only policy. Empty pending counts alone do not establish learned benefit.

For continuous-study failure feedback, the one admitted read must target the exact
source/session-bound verifier file without offset or limit. Enforce that boundary
in the parent tool handler; `--tools read` alone permits unrelated source reads.
Retain rejected calls and their costs, and stop repeated boundary violations.
Preserve earlier cohorts that lacked this enforcement as failed evidence.
The model-facing OpenAI-compatible read schema must advertise the same exact path
enum without pagination or additional properties in both arms. Preserve messages
and complete observations; never force a read or supply its result. Keep the
execution guard and independent max-one rejected-preread proof unchanged, and
retain broader-schema cohorts and all their failures/costs separately.

For interrupted semantic Memory repair, run
@packages/continual-learning/tests/test_memory_repair_deadline.py. It drives the
actual workspace Pi 1.2 child against a loopback provider and accelerates only
the parent deadline after the provider receives the request. This proves child
termination and cancellation ownership, not remote learning. Repair uses the
recorded `MEMORY_CORRECTION_WORKER_DEADLINE_MS` budget (600 seconds,
@docs/adr/0009-record-the-memory-correction-worker-budget.md); the Harness
correction path keeps its own 230-second bound. It must retain parent-controlled
started/closed markers and known partial usage without admitting held proposals
or adding retries. First cancellation reason wins during process cleanup.
For interrupted study costs, reconcile only parent-owned run receipts, named
worker ledgers and replay attempt receipts using
@packages/continual-learning/tests/continuous_failure_retention.py. Project,
session, snapshot and model-plan JSON cannot supply accounting receipts. Include
body and source audit ledgers, reject conflicting or duplicate call identities,
retain unknown interrupted costs and preserve the original failed report.

A failed feedback summary is still a failed task; it need not invalidate an
already complete, safely observed failure. Before independent backfill, use
@packages/continual-learning/tests/failure-observation-proof.ts to verify the
actual full read, immutable session prefix, source/log bindings, rejected-tool
results and complete pending slice. A retained zero-tool diagnostic must remain
in the longer slice; do not rewind to omit it or retry the parent summary.
For standalone recovery, use
@packages/continual-learning/tests/recovery_integrity.py: claim the exact failed
slice once with an immutable exclusive parent marker before paid calls, keeping
that claim on failure/interruption. Verify every owner history chain and actual
endpoint across private/public/project roots, including permissions and changes
that return to their original bytes. These checks admit evidence only; task
success, valid learned changes and downstream benefit remain separate claims.


Continuous coverage version 3 uses index-only Memory discovery and permits both
arms to read only Memory paths declared by the plugin. Record actual unique,
successful read calls and result hashes; require equality with retained learned
file revisions for Memory exposure and correction coverage. Partial reads,
truncation notices, index rows, and legacy injected bodies do not satisfy this
version. Read exposure is not adoption or task benefit; keep the hidden behavioral
outcomes and cumulative costs separate. Preserve older version 2 cohorts and
disclose this protocol change before new real calls.

Complete manual `/consolidate backfill` also collects fresh source for the
original task's paths before Memory selection. Keep all original entries and
indexes, bind the actual source reads through review and writes, and account for
collector failures and usage. The replay collector receives no stored Memory
bodies or indexes; path hints only narrow the existing regular-file discovery
scope. Automatic or truncated replay keeps its prior behavior. Preserve cohorts
without this source-refresh phase separately. Fresh observations alone do not
prove a repair or downstream benefit.

For isolated Jev transport diagnosis, keep model judgments separate from connectivity.
An explicit study-only public IPv4 route may bypass a failing local DNS path only
with the original service Host/SNI and normal certificate verification; never
disable TLS checks, follow redirects, retry held judgments, or reuse diagnostic
answers as semantic admission. Retain the selected address/DNS observation,
complete failed-wire hashes, changed transport protocol, requests and unknown costs.
A successful HEAD or replay does not establish a stable network fix or learning benefit.

For persisted Jev request-concurrency changes, run
@packages/continual-learning/tests/live_jev_concurrency.py. It uses actual Pi,
isolated HOME/agent roots and a loopback SDK endpoint, comparing disk-configured
4 versus 1 with identical complete wires/windows and a cancellation case. It
performs no external model requests and proves configuration wiring only. Record
a lower study concurrency as a protocol intervention; preserve per-request
deadlines, full evidence, request bounds, thresholds, failures and all costs.

For failure processing after source-audit append, use
@packages/continual-learning/tests/continuous-dossier-proof.mjs and
@packages/continual-learning/tests/test_continuous_dossier_prefix.py. Recompute
native JavaScript hashes from the complete parent-retained dossier. Bind the
exact original range and full prefix, the original verifier observation inside
that prefix, the complete review digest and the actual receipt acknowledgment.
Added source observations change the full digest; they must never replace any
original evidence. IDs alone or model-provided digest metadata prove nothing.
Keep the frozen verifier snapshot independent of later recovery check objects.
Processing proof does not change a failed task outcome or establish benefit.

Complete automatic current-session tasks with parent-observed successful `edit` or
`write` calls collect fresh source before Memory selection. This also applies
when semantic selection enables Memory after the initial heuristic screen.
Keep the complete original evidence prefix; the collector receives only original
path hints, never stored Memory bodies or indexes. Validate deep known paths
through the existing root-scoped regular-file reader before granting exact-file
access; bounded directory discovery is not a complete path inventory. Preserve
source-revision checks, collector failures and usage. Exercise the native
`tests/live_automatic_source_refresh.py` ordinary-edit, deep-path, source-race
and refused-read cases. Controlled judgments prove wiring only, never learning
benefit. Automatic backlog and truncated replay retain their prior behavior.

For failure-feedback proof after the study main deadline, retain the parent's
terminal lifecycle row after the assistant summary. Verify the complete
900-second started/settled pair and every suffix row's parent chain back to the
immutable original session; do not drop lifecycle rows to recover a pass. An
original session with deadline markers cannot fall back to the historical
marker-free protocol. Use `tests/test_failure_observation_proof.py` and its
frozen V30 `real-deadline-verifier-feedback.json`, including negative cases
that recompute backlog context, digest and identity after tampering. A proved
feedback read admits observed evidence only; the original failed source task,
summary failures, semantic review and all costs remain separate.

For failed-task feedback after automatic source refresh, preserve the complete raw
task as an unchanged prefix and bind the full reviewed snapshot to the original
run manifest and its source-audit receipt, matching usage ledger and complete
observation log. Exercise @packages/continual-learning/tests/test_replay_source_extension.py,
including rehashed tampering, missing/ambiguous evidence and symlinks. Historical
source rows only authenticate prior rejected correction questions; they are not
fresh replay source or mutation authority. Keep the separate current-source
collector and every semantic gate.

For normal unbounded Memory-review transport, use
@packages/continual-learning/tests/test_jev_inline_memory_review.py. Complete
knowledge bodies, predecessor bodies and cited quotes stay inline; description
judgments remain separate and the complete Markdown stays in mutation context.
Normal REWRITE source-support batches contain the complete new Markdown, cited
entries, bound current source and original user context. They do not use old
Memory or historical purpose as current source truth. Every counter, permission
and preservation window still receives complete old/new records and history.
Exercise this purpose boundary with @tests/test_memory_origin.py, including
privacy, changed-history and uncertain-source negatives. DELETE/retain and finite
historical wires keep their existing context. No gate or threshold changes.
Keep transport pointers only for explicitly byte-bounded historical studies and
require the frozen original request hash there. Controlled answers prove encoding
and unchanged gates only. An exact wire reconstruction does not establish why a
historical semantic verdict was uncertain or demonstrate learning benefit.

For missing semantic-repair envelopes, run @tests/test_memory_repair_envelope.py with the retained real response. Keep kind/version and every parent identity value mandatory at the top level; patch field restrictions apply inside replacements only. Never synthesize missing identity or treat a framing repair as semantic acceptance.

For corrective-generation effort changes, run @tests/test_memory_repair_effort.py. Exercise actual Pi wire delivery (DeepSeek uses thinking.type=disabled, not reasoning_effort=none), preserve held-body xhigh for source, permission and preservation holds even after consistency passed, and the recorded Memory correction worker budget (600 seconds, ADR 0009), and require fresh full reviews before writes. Serialization is not evidence of faster service or useful learning.

For preservation repair context, also run @tests/test_memory_semantic_amendment.py.
Keep complete old/new records and original evidence beside exact line-occurrence
comparisons. These comparisons locate changes only; they grant no preservation
or mutation authority. A description-only patch can correct a supported scope
condition, but does not by itself clear another held requirement. Never force a
body paraphrase or append history merely because a verdict is uncertain. Keep
empty corrections failed and retain all fresh review gates. V70's complete wire
did not establish a missing-source cause; new generation guidance needs a fresh
real cohort before any learning-benefit claim.

For Memory origin storage, run @tests/test_memory_origin.py and the applied case
of @tests/live_automatic_source_refresh.py. Capture the actual parent run, final
plan and exact creation set; never select a run by filename or matching body.
Keep complete artifact hashes and real bigint file revisions on both history
sides. Optional origin failures remain unavailable and cannot change mutation
outcomes after rollback has closed. Legacy records stay unbound; undo continues
to use bytes and mode. Exercise the read-only origin loader in the same tests:
require a complete bounded history inventory, a unique continuous revision
chain to creation, and all artifact bindings. Reject manual changes, ambiguous
records, incomplete chains, cancellation and post-read changes without partial
context. Recheck every inventoried record and artifact before use. Historical
context grants no current citations or authority; external use still requires
privacy checks. Normal Memory review and semantic repair may receive complete
historical tasks only after positive private authorization and full sensitive
screening. Keep `historicalMemoryOrigins` separate from current evidence, roles,
citations and read grants. Normal historical counter instructions must name the
actual `supportEvidence` and `reviewEvidence` fields; source-support instructions
use `frozenEvidence`. Check the captured native `origin-repair` requests and
@tests/test_memory_origin.py; preserve bounded historical wire hashes. This
field-binding proof does not establish a historical semantic cause or benefit.
Bind its digest to review and recheck it after awaits.
Before mutation, admit only the exact parent-written pending row; after mutation,
check old artifacts and use current receipts for changed target files. Retain
independent-subset audits in run artifacts before publishing their history rows
after origin guards settle. Exercise the origin cases in
@tests/live_automatic_source_refresh.py and the origin/subset combination in
@tests/test_independent_memory_parent_pipeline.py. Keep default CREATE-only
partition admission and finite historical wires unchanged. Controlled judgments
prove integration only.

For a mixed subset beside a held unchanged rewrite, run
@tests/test_independent_memory_partition.py, @tests/test_jev_memory_relations.py
and @tests/live_automatic_source_refresh.py with --case mixed-noop,
--case mixed-noop-uncertain and --case mixed-noop-source-race in separate
disposable output roots. Bind complete original mixed indexes, digests and
checklists. A unique same-classification, byte-identical frozen predecessor is
comparison-only and always held; it never becomes an eligible mutation. Require
complete direct independence against persisted no-ops, standalone and body
review for each eligible new fact. Standalone proof cannot override conflict,
dependency, duplicate or uncertainty against a record that remains stored.
Preserve old bytes, mirrors, ownership, pending review, source/privacy/transaction
guards and the Harness/AGENTS/backlog hold. Native controlled writes prove
partial persistence only, not semantic accuracy or downstream benefit.

For failure-label/state confusion, run @tests/test_source_comment_grounding.py
with @tests/fixtures/real-failure-label-state-conflict.json and
@tests/test_jev_citation_generation.py. Preserve the complete original snapshot
and rejected repair. A failure message establishes its observed wording, not
which callback or work remains unfinished. Trace actual awaits, completed
callbacks and unreleased work; retain unknown state rather than inventing a
mechanism. Do not repair the stored fixture or rejudge its historical verdict.
Prompt delivery and controlled native runs do not establish correct generation
or improvement on later real tasks.

For current-source comparison in normal Memory mutations, run
@tests/test_retained_source_context.py and @tests/test_jev_inline_memory_review.py.
Check complete parent-bound observations in every rewrite/delete counter window,
including paths nominated only by the predecessor. Keep all original entries,
late revocations and source binding negatives; filename matches never establish
support or authority. Explicitly bounded historical wire hashes must stay exact.
Coverage and a completed repair do not establish semantic acceptance or benefit.

For Memory that quotes source comments, run @tests/test_source_comment_grounding.py
and @tests/test_source_excerpt_memory.py. The retained V37 example contains an
observed comment conflicting with an original task requirement. Preserve the
original evidence and distinguish quoted wording from established behavior.
Prompt coverage is mechanics evidence only; require actual service acceptance,
safe writes and later consumption before claiming a useful correction. Keep
atomic submission and all original semantic gates.

For observed source-read ordering, run @tests/test_retained_source_context.py
and @tests/test_jev_inline_memory_review.py. Require successful uniquely paired
earlier reads, exact supplied path equality and already-bound later source reads.
The semantic correction worker receives the same validated index links without
duplicate source bodies; its complete original evidence stays unchanged. Invalid
bindings must stop before transport. Preserve the V50 stale-declaration repair
as rejected; provenance delivery does not prove that generation or learning improves.
Keep complete original observations, all windows and final conflicts. These are
provenance relationships only; do not label them verified semantic supersession
or mutation authority. Preserve exact bounded historical wire hashes and retain
the failed V37 backfill claim without another paid retry of that slice.

For early owned Harness correction, run @packages/continual-learning/tests/live_current_user_harness_correction.py with a disposable output parent. It uses actual workspace Pi and real planner children against a loopback provider and SDK wire, validating persisted correction/retirement before an actual standalone `npm --version`, uncertain zero-write blocking, and rejection of ordinary writes that alter auto-owned rules. Pi emits `before_agent_start` before appending the current user message: bind the actual interactive/RPC input event and require exact prompt equality, never an older session row. Keep one 230-second total bound, original-user-only frozen evidence, exact owned revisions, all semantic/fixture/transaction checks and separate unfinished-task accounting. This is controlled lifecycle evidence only, not real-model judgment or learning benefit; no external requests are permitted. Ordinary write protection is a tool boundary, not a shell/filesystem sandbox.

For service context overflow, run @tests/test_jev_long_context.py and @tests/test_jev_https_forward.py with @tests/test_docker_experiment.py. Preserve the V40 exact-wire failure and one read-only diagnostic; never rejudge its held plan for approval. Normal unbounded reviews request official long context before the first call, or honor `jev.longContext: false`; finite historical studies keep their original context. Every original entry, candidate, old body, source binding and .9/.8 gate remains required. Record the larger-context protocol and possible accuracy/latency cost separately; controlled capacity responses prove wiring and coverage only. Strict TLS, original Host/SNI, no redirects, existing retries/deadlines and complete accounting remain unchanged.

For mixed Memory creation and mutation reviews, run
@tests/test_memory_source_chronology.py with @tests/test_jev_preservation_closure.py.
A normal CREATE-only counter batch judges its own knowledge without predecessor
preservation obligations. Keep complete original windows, cited support and bound
current source. Rewrite/delete batches retain exact preservation dependencies,
including new same-plan targets. Atomic approval and all semantic gates remain.
Finite historical request encoding stays unchanged. Exact wire reconstruction
proves input shape only, not the cause of uncertainty or learning benefit.

For content-only semantic Memory amendments, run
@tests/test_memory_semantic_amendment.py and @tests/test_memory_output_schema.py.
Reuse original citations only with the exact original candidate ID, complete
snapshot hash/run/scope binding, valid original citations and a changed held
field. Keep locked metadata and retain the complete original worker response.
Explicit invalid evidence, missing identity, unchanged content and citation-only
omissions stay rejected. The inheritance receipt grants no semantic approval;
full fresh source, body, privacy and mutation checks still apply. Preserve V49
as failed; offline reconstruction and native framing do not prove learning benefit.
Reject an effective full-plan no-op after source materialization, citation
resolution and protected-field restoration, before another paid review. Compare
validated citation sets, including inferred roles, without changing the emitted
plan. Retain output, usage and the original hold; never force a paraphrase from
uncertainty. New source or content still requires every full review gate.

For the Memory prerequisite gate, run @tests/test_learning_controls.py,
@tests/test_harness_consolidation.py and @tests/test_automatic_source_refresh.py.
The native `held-later` case uses actual Pi1.2 and loopback judgments with zero
external calls. A saved held proposal or applied subset with pending records must
not start Harness/AGENTS planners. Preserve its exact outcomes and costs. Fully
reviewed repairs and intentional validated propose policies remain distinct.
Recheck ownership after asynchronous validation and proposal persistence before
changing a current gate; a cancelled predecessor cannot change its successor.

For semantic source selection, run @tests/test_memory_semantic_amendment.py,
@tests/test_source_excerpt_memory.py and @tests/test_memory_output_schema.py.
The worker must explicitly select a parent-enabled candidate ID and original
current-audit refs with non-empty evidence. Bind the complete snapshot/run/scope,
unique audit call/result and full current regular-file hash. Ordinary read/edit
excerpts remain available only to the existing initial-proposal interface, not
this correction alternative. Preserve locked metadata, complete predecessor
knowledge and every fresh semantic/body/privacy/transaction gate. The native
Pi1.2 loopback fixture proves extraction only; V50/V51 remain failed evidence.


For semantic candidate references, run @tests/test_memory_semantic_amendment.py
and @tests/test_memory_output_schema.py. Preserve the V52 response with its
61-character digest as rejected. Capture the complete original proposal digest
and exact reference map before generation; recheck that binding and the canonical
snapshot before resolving a short reference. Mixed selectors, duplicate targets,
proposal drift and citation-only references stay rejected. Keep full fresh review;
controlled and native Pi1.2 binding success is not learning benefit.

For Harness repair artifact grants, run @tests/test_harness_plan_repair.py and
the native `repair-read` case in @tests/live_current_user_harness_correction.py.
Both missing-output and semantic repairs must be able to read the exact original
snapshot and selector dossier required by their protocol, without granting an
agent-directory root. Preserve snapshot/dossier hashes and symlink refusal.
A corrected read grant does not establish the cause of an interrupted historical
worker; keep its partial usage, failure and unchanged total deadline.

For normal unbounded rewrite/delete review, run @tests/test_memory_source_chronology.py,
@tests/test_jev_preservation_closure.py and @tests/test_memory_delete_reconsideration.py.
Factual evidence, original user permission for the parent-owned Memory operation,
and predecessor preservation are separate required questions in every complete
original window. Facts include current user preferences and policy corrections;
write permission does not make a revoked preference valid. Each question retains
probability 0.9 and confidence 0.8. The parent also requires
max(0, evidenceProbability + permissionProbability + preservationProbability - 2)
to reach 0.9. This conservative score composition assumes no independence; it is
not proof of calibration or real-world accuracy. Missing answers remain invalid,
held dimensions stay diagnostic only, and finite historical wires stay unchanged.
Keep this changed question protocol separate from older cohorts. Controlled
answers do not prove semantic improvement or useful downstream learning.
Normal unbounded rewrite/delete support and counter requests retain complete
original user entries with their indexes and full snapshot binding after candidate
projection. Use the original role parser, never embedded or quoted roles. Preserve
all restrictions and revocations. User context adds no citation or proof of work;
CREATE-only, retention, Harness and finite historical wires remain unchanged.
Reject conflicting role wrappers before transport. Exercise the chronology,
preservation-closure and historical exact-wire tests.

Retain each candidate/field/dimension's first held location. Map held preservation
and permission checks to the candidate body in complete and incomplete repair
feedback; malformed and foreign keys cannot unlock fields. All other fields,
original citations, identity, privacy and full post-repair review remain required.

For exact source quote comparisons, run @tests/test_retained_source_context.py,
@tests/test_jev_inline_memory_review.py and @tests/test_jev_long_context.py.
Keep unique successful same-path read bindings, candidate-scoped facts and exact
single-text-block matching. A missing literal match does not establish file
absence; a present match grants no semantic approval. Preserve all original
windows, complete values, conflicts and thresholds. The historical reconstruction
must still match the original 132,837-byte request hash after restoring its old
question protocol. Controlled comparisons do not prove a historical service cause
or downstream learning benefit.

For exact Memory rewrite text comparisons, run @tests/test_jev_inline_memory_review.py
and @tests/test_jev_long_context.py. Preserve complete inline records and every
original review window. Line counts include duplicate occurrences and exact line
endings; they ignore order and never establish semantic preservation. Changed text
can be superseded or rephrased; unchanged text can change meaning in context.
Keep each semantic gate and historical bounded wire unchanged.

For plain and Markdown purpose labels, run `tests/test_memory_semantic_amendment.py`.
Preserve populated Why and How to apply sections during correction. Ignore quoted
labels and reject removal of their content. Native fixtures prove preservation
wiring only; retained V82 automatic failure is not a stored correction.

For optional new Memory refusal, run `tests/test_memory_semantic_amendment.py`,
`tests/test_jev_memory_relations.py`, `tests/test_planner_json_output.py` and
`tests/test_learning_efficiency.py`. Bind the complete original candidate review,
then review the exact declined set and effective remaining content together.
Preserve all user storage and existing correction obligations. Recheck absence
in both frozen and current roots before mutation. Only an explicit bound refusal
can finish an optional draft as not learned; empty, cancelled or uncertain
responses stay pending. Keep failures, usage and unknown costs. Controlled SDK
and native Pi fixtures prove wiring only, never learning benefit.

For body-consistency repair scope, run `tests/test_memory_body_consistency.py`
and `tests/test_memory_description_coherence.py`. Preserve V79's submitted and
parent-merged public descriptions: the old parent restored an ambiguous
description after body repair. A body coherence hold may permit a paired
description correction, but does not establish a description failure or source
truth. Keep other metadata locked and require every fresh review before writes.
Offline replay proves correction scope only, never real-model learning benefit.

For declaration-level Memory consistency, run `tests/test_memory_body_consistency.py`
with the retained public V81 candidate. Normal review distinguishes quoted source
or type declarations from endorsed runtime assertions. A quotation is no blanket
exemption: explicit runtime claims, conditions and consequences still need complete
comparison. Keep contradictory, unclear, missing and below-threshold results held,
all source/description/body gates, and finite historical wires unchanged. V81's
coherence hold does not establish why Jev was uncertain. Controlled answers prove
framing and gate wiring only; require a fresh real cohort for efficacy claims.

For absent project instruction documents, run `tests/test_agents_md_consolidation.py`
and `tests/test_learning_replay.py`. A missing project AGENTS.md is a no-op for
existing-document consolidation. Protected targets remain skipped and cannot
complete a screened phase. Use `tests/test_learning_controls.py` for actual FIFO
and regular-file replacement cases. Bounded readers must not wait on non-regular
files before their descriptor checks. Do not accept historical skipped receipts, missing
phases, proposals or pending operations as completed learning. This disposition
proves no learning benefit.

For revision-bound Harness execution observations, run
`tests/test_guardrails_extension.py` and the offline
`tests/live_current_user_harness_correction.py` native runner. Keep decision and
completion entries non-context and bind exact session, call and canonical rule
revisions. Hash rule and call IDs; never copy commands or result bodies into the
observation. Missing timing, reused IDs, incomplete coverage and changed sessions
remain unverified. Observer failure must not change execution; a stale native
confirmation must not authorize an old call. Positive handler timing proves
invocation only. Keep task outcome unverified and effect cannot-attribute until
separate task evidence supports a conclusion. This runner uses loopback services
only and proves lifecycle wiring, not real-model learning benefit.

For complete Memory-result observations, run `tests/test_observed_memory_reads.py`,
`tests/test_memory_index.py` and `tests/live_memory_reference_reuse.py` with a
fresh disposable output parent. Preserve explicit loader truncation and raw-byte
UTF-8 round-trip checks; a decoded prefix is not a complete file revision.
Require native handler evidence plus unique retained call/result rows and the
full branch to the original preparation. Observer failures must not affect tools
or learning. Keep preparation separate from actual model wire, and result
observation separate from attention, source truth and task benefit. The native
runner checks complete, partial and updated results against actual subsequent
requests using loopback only; it does not prove real-model learning.

For evidence-only retained Memory correction, run `tests/test_combined_memory_amendment.py`. Only a genuinely omitted rewrite body can reuse the unique parent-frozen predecessor with a complete bound snapshot, unchanged identity/context and no required text changes. Keep ordinary delta content mandatory, delete bodies absent, original privacy and all final structure, citation and semantic checks. The native Pi 1.3 loopback cases prove framing and exact-byte reuse only; retained evidence updates do not prove corrected knowledge or later task benefit.

For continuous-study cost accounting, run `tests/test_retained_learning_costs.py`
and `tests/test_continuous_project_protocol.py`. Count parent pipeline receipts
from early current-user Harness correction as well as replay jobs. Missing worker
ledgers do not erase receipt costs, failures, operations or unknown usage. Deduplicate
by exact batch and worker identities; conflicting snapshots stop accounting.
Never infer call identity from equal numeric totals or mark partial costs complete.
Validate totals with the parent's ordered JavaScript Number additions. Python's
compensated `sum` can differ by one ULP. Keep exact equality and reject even a
one-ULP alteration; do not add a tolerance or rewrite historical receipts.
