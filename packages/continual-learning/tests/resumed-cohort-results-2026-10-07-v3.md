# Resumed cohort results v3: pluggy off and on

Run root: `~/.cache/pi-continual-learning/docker/20261007T070830Z`.
Protocol: @packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07-v3.md.
Digest `e274695653a0dfd5dede02834bd616924c98178c4fef313f5a52f411d02faba0`, the
first run carrying both newest fixes.

## Headline

**Both arms passed.** The Jev-on arm is the first untuned project where the
Memory and the Harness review both completed, were decided `supported`, and
applied:

| Measure | Jev off | Jev on |
| --- | --- | --- |
| Project acceptance | passed, complete | passed, complete |
| Memory items | 2 | 2 |
| Harness rules | 1 | 1 |
| Memory diagnostic | none | `Jev decided: supported` |
| Harness diagnostic | none | `Jev decided: supported` |
| Jev judgments | 0 | 2: memory 6/6 requests, 5/5 windows; harness 6/6 requests, 5/5 windows |
| Acceptance checks true | 12 | 15, including the three participation flags |
| Learning seconds | 326.72 | 309.23 |
| Main-model cost estimate | USD 0.028122 | USD 0.027617 |
| Jev cost estimate | none | USD 0.003198 |
| Total cost estimate | USD 0.028122 | USD 0.030815 |

## The six measures

| Measure | Result | Direction |
| --- | --- | --- |
| Effective persistence | both arms wrote 2 Memory items and 1 Harness rule, and both used them in a fresh session | parity |
| Misrecording | 0 observed on either arm; the private preference stayed private and the mirror was byte-identical | parity, nothing for Jev to prevent here |
| False holds | 0 on both arms; the Memory plan was applied after a supported decision | parity |
| Correct constraint execution | 3 of 3 probes on both arms | parity |
| Latency | 326.72 s off against 309.23 s on | on 5.3 percent faster |
| Cost | USD 0.028122 off against USD 0.030815 on | on about 9.6 percent more, driven by Jev |

## What changed and what did not

Changed: the earlier finding that the Jev-on composed path consistently loses
Memory no longer holds on the fixed code. When its reviews complete, Memory and
Harness learning both land, and every acceptance check passes.

Not changed: **net benefit is still not demonstrated as a gain.** The off arm
made no misrecording and missed nothing, so Jev had no error to prevent on this
project. Parity at a small cost premium is not a gain. Composed and independent
stay default-off.

## Limits

- One project and one pair; parity on one project is not a rate.
- Both arms passed, so this run cannot separate a benefit from a neutral outcome.
- Cost figures are estimates; `usageAvailable` and `costAvailable` are false.
- The three untuned projects form no controlled set: itsdangerous ran before the
  retry fix, iniconfig before the support and guard fixes, pluggy after.
- No misrecording has been observed anywhere in the real runs, so the value Jev
  is supposed to add remains unmeasured.
