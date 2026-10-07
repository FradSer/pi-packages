# Protocol: what makes a verified-observation supplement uncertain (2026-10-07)

Written before the paid calls. Two NEW samples only. The comparison arm reuses the
already recorded rows `supplement-pure-en` and `supplement-pure-zh` from
`cases-v2.json`, so no earlier sample is rerun.

## Question

The study held six of six supplement samples on `support: uncertain`, including a
pure candidate supported by a verified tool observation. Does the uncertainty come
from the presence of existing Memory, or is it intrinsic to the support question?

## Design

| Arm | Existing Memory | Samples | Source |
| --- | --- | --- | --- |
| present-existing | the package-manager fact | `supplement-pure-en`, `supplement-pure-zh` | already recorded in cases-v2.json results |
| empty-existing | none | `supplement-noexisting-en`, `supplement-noexisting-zh` | new, this protocol |

Identical evidence and candidate text in both arms, both languages.

## Labels

Both new samples carry the label **allow**: the evidence records a passing test run
and the candidate records that command as the project's verified test command,
which the task contract treats as a shareable project fact.

## Interpretation rule, fixed before the run

- Empty-existing allowed and present-existing held: the uncertainty comes from an
  interaction with existing Memory. That is a precise, actionable finding.
- Both held: the uncertainty is intrinsic to the support question for a verified
  observation.

## Budget, stopping rules, limits

- Two requests, well under USD 0.01. No retry, budget 40.
- Record only controlled fields: decision, reason, `candidateFailures`, and any
  answers the judge returns. A held judgment returns no answer detail.
- Fixed author labels measure judgment behaviour only. This is not net-benefit
  proof, and it cannot convert the unproven verdict.
- The privacy-preflight false positive stays unchanged pending the user's decision.

## Raw root

`~/.cache/pi-continual-learning/research/adversarial-negative-2026-10-07/supplement-isolation`
