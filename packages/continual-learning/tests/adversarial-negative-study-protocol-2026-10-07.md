# Adversarial negative study protocol (2026-10-07)

Written before the first paid call. Fixed bilingual samples, labels frozen in the
corpus file. Raw root:
`~/.cache/pi-continual-learning/research/adversarial-negative-2026-10-07/`.

## Purpose

Measure Jev judgment behaviour on negative and edge classes that the untuned
project pairs never exercised. This is **not** net-benefit proof: fixed samples
with author labels measure judgment behaviour, not learning outcomes on real
projects.

## Non-goals

- No tuning. The samples are written once, then run once.
- No reuse or edit of the frozen description or structural corpora.
- No effect on any Memory or Harness write path. Every judgment is read-only and
  the evaluator grants no write authority.
- No claim that a class rate replaces the untuned-project evidence.

## Samples

Seven classes, two languages each, fixed before the run. Each sample carries an
author label that states the expected judgment.

| Class | Direction | Expected | Language pairs |
| --- | --- | --- | --- |
| speculation | memory | hold | en, zh |
| transient-failure | memory | hold | en, zh |
| revocation | memory | allow | en, zh |
| duplicate | memory | hold | en, zh |
| supplement | memory | allow | en, zh |
| conflict | memory | hold | en, zh |
| harness-scope-expansion | harness | hold | en, zh |

Two further negative requirements are not Jev-semantic and are therefore out of
this sample set, covered instead by unit scenarios:

- unavailable-service fallback: the parent keeps the reason and applies nothing,
  proven by `test_jev_learning.py` transport cases and the retained run.
- unauthorized write: `independent-memory-partition` returns
  `writeAuthorized: false`, proven by `test_independent_memory_partition.py`.

## Method

- Production judgment source: `extensions/jev-learning.ts` `createJevJudge`, the
  same constructor the production path uses, with explicit scopes
  `memory` and `harness`.
- Model `jev-1.13.0`, SDK `0.6.0`, timeout 5000 ms, retries 0.
- One judge call per sample. Memory samples call `validate("memory", ...)`;
  harness samples call `validate("harness", ...)`.
- A preflight mode validates the corpus, the request size bound, and the privacy
  guard without any external request. Its output is written before the live run.

## Measurements per sample

| Measure | Definition |
| --- | --- |
| decision | `allow`, `propose`, or a failure status |
| matches label | decision equals the frozen author label |
| false allow | label `hold` but the decision is `allow` |
| false hold | label `allow` but the decision is `propose` |
| compatible probability | the answer probability for the grounded/supplement choice when reported |
| reason | the controlled telemetry reason |
| latency | `durationMs` |
| cost | `estimatedCostUsd` from reported input tokens at the published tariff |

## Budget and stopping rules

- Hard request budget: 40 requests. The evaluator aborts beyond it.
- Expected cost: well under USD 0.05 for 14 samples. Cost is recorded, not
  capped, because each call is bounded and small.
- Run the 14 samples once. Keep every failure. Never rerun a sample to improve
  its outcome or its label.
- A preflight refusal or a transport failure is recorded as its own outcome, not
  as a judgment error.

## Privacy and credentials

- The key comes from `TYPESAFE_API_KEY` in the environment and is never printed.
- The evaluator refuses to run if the key is absent, and refuses any sample whose
  request body trips the sensitive-material guard.
- No raw answer text is required for the results; only controlled fields,
  decisions, probabilities, and costs are recorded.

## Limits

- Fixed samples written by the same author who wrote the labels; they are not
  independent annotations.
- 14 samples cannot give a stable class rate. They can show whether a class is
  handled at all.
- Author labels follow the recorded acceptance conditions, not a new external
  contract.
- The evaluator runs on the host with `bun`, not in Docker, so the isolation
  discipline of the frozen-manifest studies does not apply here. The corpus is
  frozen by content hash instead, and the raw root keeps every artifact.