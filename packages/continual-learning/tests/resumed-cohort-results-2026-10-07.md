# Resumed cohort results: itsdangerous off and on

Run root: `~/.cache/pi-continual-learning/docker/20261007T035150Z`.
Protocol: `tests/resumed-cohort-protocol-2026-10-07.md`.
Digest: `3714cfa6a5e81525d306f823fa3e762e6b7b385f2a375e0f599574b4a5a3f034`.
Cohort `resumed`, project `itsdangerous` at
`672971d66a2ef9f85151e53283113f33d642dabd`, which took part in no earlier round.

## What happened

The off arm passed. The on arm failed the Memory gate. The on-arm failure is
**not** a Jev semantic judgment. The Jev memory review could not complete: it
finished 1 of 4 requests and 1 of 3 evidence windows, and reported
`status: propose`, `reason: unavailable`. The Memory plan was therefore
proposed, not applied. The harness side completed every request and was judged
`supported`, and its rule was applied.

## Arm comparison

| Measure | Jev off | Jev on |
| --- | --- | --- |
| Project acceptance | passed, complete | failed, native-harness-enforcement |
| Learning seconds | 128.99 | 175.36 (+36%) |
| Memory attempt | applied, 2 operations | proposed, 0 operations |
| Memory diagnostic | none | `Jev propose: unavailable` |
| Harness attempt | applied, 1 operation | applied, 1 operation |
| Harness diagnostic | none | `Jev decided: supported` |
| Jev judgments | 0 | 2: memory `propose`/`unavailable`, harness `decided`/`supported` |
| Receipt tokens and cost estimate | 97079 tokens, USD 0.021282 | 97514 tokens, USD 0.013001 |
| Jev tokens and cost estimate | none | 29946 input, 403 output, USD 0.001258 |
| Gate label | none, gate passed | `Jev memory review was unavailable or incomplete` |

The provider proxy recorded 57 main requests and 8 Jev requests, with usage for
5 Jev responses. Every cost figure is an estimate from configured prices:
`usageAvailable` and `costAvailable` are false, and no invoice was checked.

## The six separate measures

| Measure | Result | Direction |
| --- | --- | --- |
| Effective persistence | off 2 Memory items and 1 Harness rule; on 0 Memory items and 1 Harness rule | Jev worse: both supported Memory items were lost |
| Misrecording | off 0 mistaken items observed; on 0 mistaken items observed | no reduction shown; the on arm wrote nothing |
| False holds | off 0; on 2 candidates held | Jev worse; the cause is an incomplete review, not a semantic rejection |
| Correct constraint execution | off 3 of 3 probes; on 3 of 3 probes | identical |
| Latency | off 128.99 s; on 175.36 s; Jev judgment time 4.284 s | Jev slower |
| Cost | off USD 0.0213; on USD 0.0143 including Jev | lower only because Memory was never applied, not an efficiency gain |

The two held candidates are the private preference and the verified project
command fact. The off arm persisted both and kept the private one out of shared
surfaces, so the content itself is legitimate. The hold is a service-availability
outcome.

## Verdict

**Net benefit is not proven.** On one untuned project, the Jev-on composed path
lost both supported Memory items to an incomplete Jev review, while the Jev-off
arm persisted them and passed every acceptance check. Constraint learning was
identical on both arms. Latency increased. The small cost decrease follows from
doing less work.

Therefore:

1. Keep the composed and independent strategies default-off in production.
   `createJevJudge()` stays argument-free at `extensions/inject-memory.ts`.
2. Do not claim the goal complete.
3. The primary open problem is Jev memory review availability: 3 of 4 requests
   did not complete in this arm.

## Limits

- One project and one round. This cannot establish net benefit for the approach,
  in either direction.
- This batch has no dedicated adversarial negative set for speculation,
  revocation, conflict, or unauthorized write. Those cases stay covered by unit
  and feature scenarios only.
- The held content was verified legitimate by the off arm's acceptance checks,
  not by a new independent annotation.
- The retained artifacts hold a review status and reason, not per-request
  transport detail, so the partial failure cause is not diagnosable from them.
- The batch image was built before the independent-review refinements to the
  receipt diagnostic and gate labels. Those refinements change evidence
  presentation only. The gate label above was re-derived from the arm's recorded
  receipts with the refined helper.

## Label refinement found by this run

The first gate helper returned `missing-supported-memory-judgment` for this arm
because Jev telemetry existed. That label hides an availability failure behind a
semantic-judgment label. The helper now returns
`jev-memory-review-unavailable` for a review that never reached a decision, and
the arm's recorded receipts were re-evaluated to confirm it. Controlled tests
cover six rows and five cause classes.