# Adversarial negative study results (2026-10-07)

Protocol: @packages/continual-learning/tests/adversarial-negative-study-protocol-2026-10-07.md
(frozen before the first paid call). Raw root:
`~/.cache/pi-continual-learning/research/adversarial-negative-2026-10-07`.
Corpus hash `5f1011e5f696fd711b10887e45b87805443157aec6c2f57928014b6ee95623e8`.
Model `jev-1.13.0`, SDK `0.6.0`, production judge `createJevJudge`.

## Totals

| Field | Value |
| --- | --- |
| Cases | 14, seven classes, English and Chinese |
| Matched label | 12 |
| False allows | 0 |
| False holds | 2 |
| Requests | 14, one per case, no retry, no transport failure |
| Tokens | 9869 input, 1238 output |
| Estimated cost | USD 0.000414 |
| Latency | 326 ms to 1004 ms, median 364 ms |

## Per class

| Class | Cases | Expected | Held | Allowed | Reasons |
| --- | --- | --- | --- | --- | --- |
| speculation | 2 | hold | 2 | 0 | unsupported |
| transient-failure | 2 | hold | 2 | 0 | uncertain |
| revocation | 2 | allow | 0 | 2 | supported |
| duplicate | 2 | hold | 2 | 0 | duplicate, uncertain |
| supplement | 2 | allow | 2 | 0 | uncertain (both false holds) |
| conflict | 2 | hold | 2 | 0 | unsupported |
| harness-scope-expansion | 2 | hold | 2 | 0 | uncertain |

## What this shows

**The safety direction is clean on this set.** All ten hold-labelled cases were
held. Speculation, transient failure, duplicate, conflict, and Harness scope
expansion produced no false allow, so no mistaken knowledge and no widened
constraint appeared.

**The recovery direction over-holds supplements.** Both supplement cases were
held on the `support` dimension with reason `uncertain`, in both languages. The
candidate added a verified command to an existing package-manager fact; the off
arm of the untuned projects proves such content is learnable. This agrees with
the recorded DeepSeek cohort hold and with the rejected description and
structural studies, which also reported false holds from counterevidence
uncertainty.

A follow-up with new samples settles the cause:
@packages/continual-learning/tests/adversarial-negative-supplement-followup-results-2026-10-07.json.
Six of six supplement samples were held, across three phrasings and two
languages, including a pure candidate that states only the evidence-supported
addition. The first explanation, that the candidates restated an uncited existing
fact, is refuted. The mechanism is not recoverable from the production judge,
because a held judgment returns only the controlled failure reason, and no
production diagnostic was added to expose the margin. The incremental Memory path
does attempt one bounded semantic repair for an `uncertain` reason and passes the
controlled failure location, but that repair is not proven to recover this class.

**The two languages agreed** in every class except the duplicate reason, where
the Chinese case reported `uncertain` but still held.

**The connection-retry fix is still unexercised live.** No request failed, so no
telemetry recorded `failureKind` or `retriedRequests`.

## What this does not show

- It is not net-benefit proof. Fixed author labels measure judgment behaviour,
  not real-project persistence.
- Fourteen samples cannot give a stable class rate.
- Two negative requirements stay out of scope because they are parent-side:
  unavailable-service fallback and unauthorized write. Both remain covered by
  unit scenarios and by the retained runs.
- The labels are not independent annotations; the same author wrote samples and
  labels.

## Consequence

Net benefit stays unproven. The clearest remaining semantic defect is the
supplement over-hold on the support dimension, and it should be addressed by
evidence before any quality claim.
