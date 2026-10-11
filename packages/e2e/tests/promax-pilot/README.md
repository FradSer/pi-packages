# ProMax pilot

Manual real-model experiment. Normal test runs exercise only the pure protocol
tests; they never launch Docker or inference.

Given an initial eight-task sample selected before inference (two repositories
each for Python, TypeScript, Go and Rust), with any substitutions selected only
from preflight environment failures before inference on the substituted task,
when the same Docker Pi and DeepSeek 4.1 Flash
solve them with and without E2E, then score captured source patches on pristine
task images using the untouched ProMax verifier. A task is eligible only if its
reference patch passes and its empty patch fails. Infrastructure failures remain
separate from incorrect solutions.

Both arms receive identical public requirements, acceptance feature and public
test command. Only the treatment loads the E2E extension. Pi-kit is a runtime
dependency, not an activated extension. Reference patches and hidden grading
tests are never mounted into the agent container. Git history is replaced by a
single baseline commit. Private model credentials stay on the host behind a
model-specific transport proxy.

Use fresh sessions, alternate arm order, and use equal limits of 20 minutes and
80 inference requests per attempt. Plugin verification time counts against the
same limit. The acceptance feature states only that the named public test command
succeeds; it does not claim that a green public suite proves every requirement.
This offline deterministic pilot tests the E2E workflow, not Jev judging quality.
On the emulated host, Ruff's whole-suite controls took 31–32 minutes; its public
command uses that suite but the adapter has a fixed eight-minute deadline.
Thus a correct solution may be unable to fulfill the public acceptance check.
Treat this as a verification-feasibility limitation, not evidence of model quality.

Eight tasks are an infrastructure and difficulty pilot, not evidence of a small
general correctness improvement. Freeze a separate evaluation sample afterwards.
The primary comparison is assignment to the loaded plugin. Report actual
`e2e_verify` invocations separately, including calls started before a timeout.
For the frozen 2026-10-09 package, an intent probe found that negative constraints
in the common coding prompt suppress its requested-verification checkpoint;
a positive control activates it. Preserve that receipt as a mechanism limitation.
These runs measure this packaged behavior, not a repaired checkpoint heuristic.

The host collector freezes existing sandbox processes, uses a separate Git
index, and diffs against a baseline commit recorded before inference. Early
2026-10-09 workers used the agent's HEAD and index instead. Their tool traces
were audited for commit/index-lock mutations, but the old collector did not
retain baseline IDs or successful collector stderr. Preserve this limitation
and the collector revision in the receipts; model inputs and plugin stay fixed.

Clear inherited external proxy variables so the internal `model-proxy` transport
is reachable. The Ruff image's defaults produced connection errors before any
host inference request. Retain those zero-request startups as invalid attempts,
and never grade or include them in the paired denominator.

If an image cannot be prepared before any inference on that task, replace it
using the same seed order within its language, excluding the blocked repository
and preferring a new repository. If none is available, allow a repeated repository
and disclose the reduced diversity. Record the original task and exact preflight
failure; never replace tasks based on model correctness outcomes.
Previously rejected task IDs are excluded from later substitutions. A reference
test with an observed timing failure or compiler crash may receive one unchanged preflight
rerun before inference; retain both control receipts and disclose instability.

## 2026-10-09 execution

All eight paired model attempts finished using Docker Pi 1.0.4 and
`cli-proxy/opencode/deepseek-v4.1-flash`, thinking `high`. Only E2E is
activated in treatment. Frozen packages and model were not changed after outcomes.
The initial sample is reconstructed from the frozen dataset and seed; final
sample v5 and all substitution receipts remain in the raw archive.

| Task | Baseline official strict grade | E2E official strict grade | E2E verification calls |
| --- | --- | --- | --- |
| DSPy 8105 | Pass | Pass | 2 |
| Transformers 38332 | Unscored: grader timeout | Fail | 0 |
| Ant Design 53739 | Fail | Pass | 0 |
| Ant Design 54813 | Fail | Fail | 1 |
| Lo 739 | Pass | Pass | 1 |
| Gitea 35775 | Fail | Fail | 0 |
| Qdrant 83bb3a3 | Pass | Pass | 0 |
| Ruff 19884 | Fail | Pass | 0 |

There are 7 scored pairs: baseline 3/7,
E2E 5/7. This is a small exploratory assignment
observation, not demonstrated general correctness improvement. DSPy and Lo
have fresh fulfilled verification evidence; report every actual call separately.
The Ant 53739 and Ruff treatment-only wins have zero verification calls.
Ant 54813 starts one verification with the configured offline runner; project
tests are still running when the attempt deadline arrives, so there is no
completion verdict or fresh verified-run proof. Three treatment arms start
verification; only two produce completed fresh proof. Its ordinary shell
self-checks pipe output without pipefail, so they are not robust acceptance
or typecheck evidence; the independent grader remains authoritative.

Transformers is excluded from the paired denominator: the same baseline patch
hit two 40-minute grading deadlines without terminal markers. An import error
appears in partial output, but the later hang's cause is unknown. Treatment has
a terminal failure. Completed model attempts were not rerun for better outcomes.
Gitea's first treatment grading hit an internal Go compiler deadlock; the same
patch then failed normally. Ant 53739 baseline grading was accidentally stopped
by the operator; the same patch was freshly regraded and failed an assertion.
Both retry receipts and patch hashes remain.

Both Ant 54813 arms pass 66 selected functional tests and 25 snapshots but
fail the official demo command because `components/button/demo/style-class.tsx`
is absent. The public statement does not explicitly require that named demo;
a fresh reviewer confirmed this public/hidden scope mismatch. Keep the declared
strict failure, report selected functional success separately, and do not claim
complete functional correctness. Hidden diagnostics were not sent to the model.

Environment preflight substitutions precede inference on each rejected task.
Angular 92c4123 was rejected by a conservative capacity budget, not an observed
pull failure or measured extraction peak. Compressed bytes plus gzip-modulo
size bounds and a chosen two-GiB reserve informed the decision. Final TypeScript
tasks repeat Ant Design because no unused eligible repository remained. This
reduces repository diversity and screens the sample for environment feasibility.
Do not resample after observing model results.

Recovery preserved invalid attempts: original Ant treatment lost its final
patch and event log after host ENOSPC/Docker stoppage; a later capacity startup
made one request and zero completed assistant messages. A subsequent worker and
temporary directory disappeared after turn interruption, cause unknown; its last
archived heartbeat has six requests and 1001.6 seconds but no final patch/trace.
Its archive contains explicitly labeled stale files from prior attempts due to
non-deleting sync; these are not its model evidence. Unknown call counts are not
zero. Two earlier Ruff proxy startups made zero requests and are also excluded.
Only incomplete invalid arms were retried. Final valid order is baseline then
E2E, deviating from initial alternation. Per-valid-attempt budgets are unchanged;
extra invalid attempts mean total inference consumption is unequal.

The user approved 122 unused, nonshared, immutable ordinary build-cache IDs.
Exact-ID pruning after fresh checks reported 4.319 GiB released. Frozen task and
runtime image IDs stayed unchanged; images, containers, volumes and cache mounts
were not deleted by that cache operation. Host free-space changes may also
include delayed filesystem reclamation.

The frozen prompt suppresses the plugin's requested-verification checkpoint in
a retained intent probe; this does not prove why a model omitted calls. Offline
deterministic judging does not test Jev. Public regression execution does not
establish full requirements coverage, and Ruff's public suite exceeds the
adapter's eight-minute deadline under amd64 emulation. Early collectors did not
retain baseline IDs or successful stderr; trace audits found no observed Git
commit/index mutations, which is weaker than full filesystem proof. Later
collectors use a host-recorded baseline and independent Git index.

[Compact results](results-2026-10-09.json) and
[raw receipts](runs/2026-10-09/) retain model events, captured patches, pristine
controls/grades, dataset/package/image hashes, invalid attempts and retry reasons.
[Verification](runs/2026-10-09/verification.json) records 130 passing E2E tests,
23 pilot tests, typecheck, packaging and syntax checks. These validate tooling,
not general model effectiveness. No TUI behavior was changed by this experiment.

## Post-draft paired follow-up

[Protocol](POSTFIX.md) uses the same eight original no-plugin drafts for
E2E verification then repair versus one same-model read-only review then repair.
Both stages share 20 minutes and 80 requests per workflow. No completed model
attempt is rerun. Image transport recovery does not reset inference budgets.

[Live local report](runs/postfix-20261009/REPORT.zh-CN.md) records patch scores,
phase costs, final response completion, incomplete usage and provenance.
This reused exploratory cohort cannot establish general effectiveness. A public
regression pass and a normally exited Pi process are each weaker evidence than
strict task completion and a completed repair response.
