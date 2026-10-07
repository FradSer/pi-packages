# Resumed cohort results v2: iniconfig off and on

Run root: `~/.cache/pi-continual-learning/docker/20261007T042933Z`.
Protocol: `tests/resumed-cohort-protocol-2026-10-07-v2.md`.
Digest `966cbd2b4af8f66a33c9ab282030bfd7c7242417294a54bc9b7ca6af5321a12a`, which
includes the connection-retry fix.

## What happened

The off arm passed all 12 checks in 146.97 s. The on arm failed both the Memory
and the Harness gate. Jev issued **no request at all**: both reviews were refused
by the privacy preflight with `reason: sensitive` and `durationMs: 0`.

The refusal is a **false positive**. The preflight's assigned-credential pattern
matched a placeholder credential assignment inside a `toolResult` from the
project's own tracked source. The shortest failing slice is 28 characters and
reads as a `passwd:`-style placeholder of exactly the minimum length the pattern
accepts. No secret-shaped user data was involved.

## Arm comparison

| Measure | Jev off | Jev on |
| --- | --- | --- |
| Project acceptance | passed, complete | failed, native-harness-enforcement |
| Learning seconds | 146.97 | 227.42 |
| Memory attempt | applied, 2 operations | proposed, 0 operations, `Jev propose: sensitive` |
| Harness attempt | applied, 1 operation | rejected by parent validation, then proposed, `Jev propose: sensitive` |
| Jev requests | 0 | 0, refused before any request |
| Checks passed | 12 | 2 |

## The six measures

| Measure | Result | Direction |
| --- | --- | --- |
| Effective persistence | off 2 Memory items and 1 Harness rule; on 0 and 0 | Jev worse |
| Misrecording | 0 observed on both arms | no reduction, because nothing was written |
| False holds | off 0; on both reviews refused before judgment | Jev worse |
| Correct constraint execution | off 3 of 3 probes; on not reached | Jev worse |
| Latency | 146.97 s against 227.42 s with no Jev judgment time | Jev slower |
| Cost | no Jev spend, because no request left the process | not comparable |

## Findings

1. **False-positive privacy refusal (major, needs a decision).** On any project
   whose tracked source, docs, or tests hold a placeholder credential assignment
   of eight or more characters, Jev is skipped entirely and both Memory and
   Harness learning are lost. Narrowing a privacy guard changes privacy
   behaviour, so this was reported and not changed.
2. **Harness probe FileNotFoundError (major, runner defect).** After the parent
   rejected the Harness rule, the effect probe aborted with `FileNotFoundError`,
   so the arm reports `phase-callback-error` instead of a clean not-applied
   result. This is separate from the Jev refusal.
3. **Retry fix still unexercised (note).** No connection-level failure occurred,
   so no telemetry recorded `failureKind` or `retriedRequests`.
4. **Gate label refined (fixed).** The first refined label called this refusal
   "unavailable or incomplete", which conflated a privacy refusal with an
   availability failure. The helper now returns
   `jev-memory-review-refused-preflight`, verified against the arm's own receipts
   and by controlled tests.

## Verdict

**Net benefit remains unproven.** Two untuned projects both ended with Jev
losing Memory. Neither run reached a Jev semantic judgment on a supported Memory
candidate, so the dominant cause is preflight and availability friction, not
semantic error. The composed and independent strategies stay default-off in
production, and the goal stays open.

## Limits

- The two projects are not a controlled pair: only the second ran with the retry
  fix.
- No adversarial negative set ran in either protocol.
- Cost comparison is not possible for this project because Jev was never called.
- The conclusion is drawn from two projects and two rounds only.