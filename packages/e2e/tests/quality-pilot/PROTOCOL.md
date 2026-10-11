# E2E review controlled diagnostic study

Frozen before paid task inference. This is a synthetic diagnostic study, not
SWE-bench, a general coding leaderboard, or a guarantee of gains for SOTA models.
Prior ProMax evidence stays separate and is never a model input.

Four small dependency-free JavaScript projects cover asynchronous memoization,
incremental CSV parsing, reentrant event subscriptions, and atomic JSON Patch.
Each begins with a deliberately incomplete starter. DeepSeek v4.1 Flash high in
Docker Pi 1.0.4 repairs it. The resulting model draft is copied identically into
two fresh containers: same-model review then same-model fix; native E2E review
then same-model fix. Only the E2E review container activates E2E (pi-kit is a
dependency). Both arms can read and run the identical frozen public probe suite.
E2E does not receive extra tests, hidden grading data, or a reference solution.
Implementation and fix have the same tools and prompts in both groups. The
treatment exists only during review: this isolates review, not the entire
plugin-loaded product workflow. Shared draft costs are shown and split equally
for cost comparison, charged only once against actual experiment spend.

Given the same frozen model draft and public requirements, when review strategy
changes and the same model repairs, then independently grade initial and final
source using hidden assertions never visible to the models. Report strict task
pass, assertion pass fraction, rescue, regression, report completion, actual
native invocation/fresh proof/Jev success, requests, cost and elapsed time.
Public passes, plugin verdicts and final reports are never substitutes for grades.
The grader imports only solution.mjs in a separate offline container. Model-written
tests and package scripts do not influence the grader. Original failure/reference
success controls must pass for every project before paid task work.

Task order is memo, csv, emitter, patch. Alternate reviewer order by task index.
No replacing tasks, selecting drafts, retries or protocol edits after observing
outcomes. Four paired tasks, one model draft each, are the complete registered
sample. An all-correct initial sample is a ceiling result, not plugin uplift.
Both arms must run fix even when the reviewer failed to finish a report. A partial
report is labelled and forwarded as data. Read-only review must preserve source.
Use a fresh tool-free handoff if a stage exhausts its request allowance, reserving
one model request for that handoff. Never abort fix merely for missing review prose.

Per task: implementation 8 requests + optional one handoff; model review 5 + one
handoff; E2E review 5 + one handoff (including native semantic requests); each fix
8 + one handoff. Thus <=39 requests per paired task, <=156 task requests plus
mechanism preflight. Each phase has a 20-minute safety deadline; overtime is
allowed relative to earlier experiments, but deadlines are not correctness grades.
No silent retry of paid stages. Global cap 200 forwarded requests includes Jev,
errors and interrupted requests. Before forwarding, bodies >64KiB and completions
above 24576 tokens are rejected. Model metadata caps default output at 8192.
Configured rates are input $0.30/M, output $1.20/M; Jev $0.042/M input/output free.
Reserve $0.06 per forwarded request regardless of actual use and $7 for historical
experiments (retained unique completed-message estimate $2.973958 plus uncertainty).
Worst reserved cumulative total is $19. Actual billing is unavailable; this is a
conservative local budget at configured rates, not an invoice guarantee.

Before paid work: exact image, original/reference hidden controls, actual native
Pi loading and fresh semantic review, immutable inputs, no hidden files in image,
request limits, phase handoff, and fresh independent review of the controller.
Any failed preflight prevents task inference. Infrastructure errors stay unknown,
not code failures. Keep all failures and charged attempts. No cleanup of old
resources is undone. New experiment resources have quality-pilot names and are
removed on completion; retain evidence and source snapshots.

The fixed public probes and reference implementations are authored by Codex.
Their authoring effort is unpriced and affects external validity. Equal test access
controls this confound between arms, but the sample is too small to infer a general
benefit. A statistically weak/null result must be reported as such.
