# Real-run net-benefit report: Jev in continual-learning (2026-10-07)

Scope: the two untuned real-project pairs run under
@packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07.md and
@packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07-v2.md,
read together with the recorded DeepSeek cohort.
Net benefit is **not proven**. Composed and independent stay default-off in
production, and the goal stays open.

## The two pairs

| Measure | itsdangerous off | itsdangerous on | iniconfig off | iniconfig on |
| --- | --- | --- | --- | --- |
| Acceptance | passed, complete | failed, native-harness | passed, complete | failed, native-harness |
| Memory items written | 2 | 0 | 2 | 0 |
| Harness rules written | 1 | 1 | 1 | 0 |
| Misrecording observed | 0 | 0 | 0 | 0 |
| Held or refused | 0 | 2 held | 0 | 2 reviews refused |
| Constraint probes | 3 of 3 | 3 of 3 | 3 of 3 | not reached |
| Learning seconds | 128.99 | 175.36 | 146.97 | 227.42 |
| Main-model cost estimate | USD 0.0213 | USD 0.0130 | not counted | not counted |
| Jev cost estimate | none | USD 0.00126 | none | none, no request sent |
| Gate label | none | `jev-memory-review-unavailable` | none | `jev-memory-review-refused-preflight` |

Digests: the itsdangerous run used
`3714cfa6a5e81525d306f823fa3e762e6b7b385f2a375e0f599574b4a5a3f034` and the
iniconfig run used
`966cbd2b4af8f66a33c9ab282030bfd7c7242417294a54bc9b7ca6af5321a12a`, which adds
the connection-retry fix. The two projects are therefore **not a controlled
pair**.

## What decided each on arm

Neither on-arm failure is a Jev semantic judgment on a supported candidate.

1. **itsdangerous-on: availability.** The Memory review lost 3 of 4 requests to
   connection-level failures inside one concurrent round of four, so the review
   could not complete and the plan stayed a proposal. The Harness review
   completed 4 of 4 requests and was supported; its rule was applied.
2. **iniconfig-on: preflight refusal.** Both reviews were refused before any
   request, with `reason: sensitive`. The guard matched a placeholder credential
   assignment inside a `toolResult` from the project's own tracked source.

So the dominant cause across both projects is preflight and availability
friction, not semantic error. The one recorded case of a real Jev judgment
holding a supported item is the earlier DeepSeek cohort's `yocto-queue-on` arm,
where an uncertain description counterevidence judgment held the verified
command fact.

## Offline measurement of the preflight false positive

The exported guard was run over every retained learning dossier: 6 dossiers and
123 evidence entries across the itsdangerous, iniconfig, and yocto-queue arms.

| Cohort | Entries | Tripping entries | Pattern |
| --- | --- | --- | --- |
| yocto-queue (on and off) | 31 | 0 | none |
| itsdangerous (on and off) | 45 | 0 | none |
| iniconfig (on and off) | 47 | 2 | `assigned-credential` |
| total | 123 | 2 | `assigned-credential` |

Both trips are the same project artifact: a `passwd:`-style placeholder of
exactly the minimum accepted length inside a tool result. The masked excerpt
reads as `pas*****: <pas*****>`; no secret-shaped user data was involved. The
trip is a property of the project's own content, because the off-arm dossier
trips it too. Only the on arm loses learning, because the guard gates Jev
reviews only.

## Open defects with evidence

| Id | Severity | Evidence | State |
| --- | --- | --- | --- |
| `false-positive-privacy-refusal` | major | 2 of 123 entries trip the guard; both are one placeholder in a tracked source file; both iniconfig reviews refused with zero requests | Reported, not changed: narrowing a privacy guard needs an explicit product decision |
| `harness-probe-file-not-found` | major | `phaseObservations.harness` `errorType: FileNotFoundError`, `failedCheck: phase-callback-error` after the parent rejected the Harness rule, because the probe read `.pi/harness.json` although no rule had been applied | Fixed: `read_harness_rules` treats a missing file as no rules and still raises on a malformed one, covered by `tests/test_harness_probe_rules.py` |
| `partial-jev-transport-failure` | major | memory telemetry requestCount 4, completedRequests 1, 1945 ms, no `httpStatus`; 3 of 8 proxy requests with no usage | Diagnosed; one bounded connection retry added and controlled-tested |
| `retry-fix-unexercised` | note | no telemetry recorded `failureKind` or `retriedRequests` in the second project, which sent no request | Open |
| `connection-failure-class-unrecorded` | note | before this work the telemetry kept only the coarse reason, so a per-request failure class was unrecoverable | Fixed: `failureKind` and `retriedRequests` are now recorded and aggregated |

## What this evidence does and does not support

Supported:

- The pipelines keep the failure reason, make no decision on an incomplete or
  refused review, apply no Memory, and release no constraint. That is the
  required behaviour for uncertainty, refusal, and unavailability.
- The constraint direction can complete on an untuned project with a real Jev
  judgment: itsdangerous-on applied its Harness rule from a supported 4-of-4
  review.
- Every acceptance check passed on the Jev-off arms of both untuned projects.

Not supported:

- Any claim that Jev improves learning quality. On both untuned projects the on
  arm lost Memory relative to its own off arm, and neither run reached a Jev
  semantic judgment on a supported Memory candidate.
- Any cost or latency advantage. Latency rose in both on arms, and the lower
  itsdangerous cost follows from doing less work.
- Any reduction in misrecording. No mistaken item was observed on any arm,
  including the Jev-off arms.

## Adversarial negative study (fixed bilingual samples)

@packages/continual-learning/tests/adversarial-negative-study-results-2026-10-07.md
ran the production judge over 14 fixed cases, seven classes in English and
Chinese, with labels frozen before the first paid call. Result: 12 matched,
**0 false allows**, 2 false holds, 14 requests, no transport failure, estimated
cost USD 0.000414, median latency 364 ms.

| Class | Cases | Expected | Held | Allowed |
| --- | --- | --- | --- | --- |
| speculation | 2 | hold | 2 | 0 |
| transient-failure | 2 | hold | 2 | 0 |
| revocation | 2 | allow | 0 | 2 |
| duplicate | 2 | hold | 2 | 0 |
| supplement | 2 | allow | 2 | 0 |
| conflict | 2 | hold | 2 | 0 |
| harness-scope-expansion | 2 | hold | 2 | 0 |

The safety direction is clean: no negative case produced an allow, so no
mistaken recording and no widened constraint appeared. The recovery direction
over-holds supplements: both cases were held on the `support` dimension with
`uncertain`, which agrees with the recorded DeepSeek cohort hold and with the
rejected description and structural studies.

A follow-up with new samples (supplement follow-up results file) confirmed the
over-hold: six of six supplement samples were held across three phrasings and two
languages, including a pure candidate that states only the evidence-supported
addition. So the holds are not a label error by the author. The judge returns no
answer detail on a hold, so the uncertainty margin is not recoverable from its
output, and no production diagnostic was added to expose it.

This is judgment behaviour on fixed samples, not net-benefit proof. The
connection-retry fix also remains unexercised live, because no request failed.

## Fix outcome on the frozen corpus (authorized after the decision brief)

The user authorized both decisions. Two changes landed, each with RED then GREEN:

1. The support question and its grounded criterion now state that a successful tool
   result that ran the command grounds the claim, and that a failed, interrupted,
   or erroring run is transient and grounds nothing. The gate constants were **not**
   changed, because the diagnostic proved no threshold can separate the classes:
   legitimate supplement probabilities (0.64 to 0.87) overlap the negative transient
   probability (0.68 to 0.73).
2. The assigned-credential guard now treats documentation-style placeholders as
   non-sensitive while a realistic assigned value stays sensitive.

Measured on the same frozen 14-case corpus:

| Run | Matched | False allows | False holds |
| --- | --- | --- | --- |
| Before (diagnostic baseline) | 12 | 0 | 2 |
| After both changes | **14** | **0** | **0** |

The negative transient class is also classified more strongly: `transient` at 0.99
to 1.0 instead of `grounded` at 0.68 to 0.73, so the hold no longer depends on the
probability gate. Evidence: tests/adversarial-negative-study-affix-results-2026-10-07.json
and tests/jev-support-instruction-fix-results-2026-10-07.json.

## Isolation result: the support-uncertain over-hold is intrinsic

@packages/continual-learning/tests/supplement-uncertainty-isolation-results-2026-10-07.json
settles the cause. Two new samples judged the same evidence-supported command
candidate with an **empty** existing Memory list; the present-existing comparator
rows were reused from the already recorded corpus and were not rerun.

| Arm | Existing Memory | Cases | Decision | Reason |
| --- | --- | --- | --- | --- |
| present-existing | package-manager fact | 2 | propose | support: uncertain |
| empty-existing | none | 2 | propose | support: uncertain |

Eight of eight samples across three phrasings, two languages, and both
existing-Memory states were held with `support: uncertain`. The over-hold is
therefore intrinsic to the support question for a verified tool observation. It
is not caused by existing Memory, by phrasing, or by language. The judge returns
no answer detail on a hold, so whether the claim was classified as not grounded
or grounded below the gate stays unknown.

This is the dominant quality defect: the Memory direction holds the very
knowledge the task contract says to remember after a successful tool result.

## Two decisions needed before any further quality work

| Decision | Measured evidence | If yes | If no |
| --- | --- | --- | --- |
| Narrow the privacy preflight so a tracked-file placeholder does not refuse a whole review? | 2 of 123 retained entries trip it, both one iniconfig placeholder; both its reviews refused with zero requests | Narrow the guard's input scope, keep refusing real secrets, rerun an untuned project | Record the loss as accepted privacy cost |
| Accept a verified tool observation as support for a command fact, so a grounded supplement is not held? | 8 of 8 verified-observation samples held with support: uncertain | Change the support criteria or the gate, prove it with RED then GREEN, re-measure on a new frozen corpus | Keep the strategies default-off and report the goal unproven with this defect named |

Neither change was made: each alters a privacy or judgment policy, which needs
your decision. The full brief, with the retained real-run hold classes, the exact
code each option would touch, the risk, and the test plan for each, is
@packages/continual-learning/tests/pending-decisions-brief-2026-10-07.md.

## Requirements still without real-run coverage

- The adversarial negative set: speculation, revocation, conflict, supplement,
  and unauthorized write are covered only by unit and feature scenarios.
- Negative examples for the guard itself. Two data points cannot give a
  false-positive rate, and the safest current reading is "rare but possible".
- Cost and latency under a completed Jev Memory review: neither untuned run
  completed one.

## Third untuned project: pluggy, both arms passed

@packages/continual-learning/tests/resumed-cohort-results-2026-10-07-v3.md is the
first real run of the fixed code and the first untuned project where the Jev-on
arm **passed**.

| Measure | Jev off | Jev on |
| --- | --- | --- |
| Acceptance | passed | passed |
| Memory items / Harness rules | 2 / 1 | 2 / 1 |
| Memory and Harness diagnostics | none | `Jev decided: supported` on both |
| Jev judgments | 0 | 2, each 6/6 requests and 5/5 windows |
| Learning seconds | 326.72 | 309.23 |
| Total cost estimate | USD 0.028122 | USD 0.030815 including Jev USD 0.003198 |

So on the fixed code Jev reaches **parity** where its reviews complete: learning
lands, every acceptance check passes, latency is slightly lower, and cost is about
nine percent higher because of Jev itself.

This changes one earlier finding and not the verdict. The claim that the Jev-on
composed path consistently loses Memory no longer holds. Net benefit as a **gain**
is still not demonstrated: the Jev-off arm made no misrecording and missed
nothing, so Jev had no error to prevent on this project. Composed and independent
stay default-off, and the goal stays open.

## Decoy measurement: misrecordings prevented is zero

@packages/continual-learning/tests/decoy-misrecording-results-2026-10-07.md ran a
new pluggy task variant whose text offered two unverified claims (a speculation
about the build command and a transient network failure), with a new
`noDecoyMisrecording` gate on every written Memory body.

| Count | Result |
| --- | --- |
| Jev-off decoy items | 0 |
| Jev-on decoy items | 0 |
| Misrecordings prevented | **0** |

Both arms passed. The Jev-on arm again completed both reviews (5/5 requests and
4/4 windows each, decided supported) with real participation, and was faster
(327.37 s against 436.38 s). But the Jev-off path already avoided both decoys, so
Jev had no error to prevent.

This is the third consecutive measurement whose outcome is parity rather than a
gain. The baseline of main model plus parent structural rules is already correct
on this task class, so the improvement the objective asks for has no measurable
room on these tasks.

## Verdict and consequence

Net benefit is not proven across the six measures together. The composed and
independent strategies stay default-off in production, `createJevJudge()` stays
argument-free, and no completion is claimed. The next quality work must fix the
friction that decides outcomes: the guard's false positive, the runner's harness
probe error, and the reliability of the Memory review.