# Diagnosis: incomplete Jev memory review in the itsdangerous-on arm

Run: `~/.cache/pi-continual-learning/docker/20261007T035150Z/itsdangerous-on`.
Written from the retained artifacts and the current source. No arm was rerun.

## Observation

The memory-stage Jev judgment reported:

| Field | Value |
| --- | --- |
| status | `propose` |
| reason | `unavailable` |
| durationMs | 1945 |
| requestCount | 4 |
| completedRequests | 1 |
| evidenceWindows | 3 |
| completedWindows | 1 |
| knownInputTokens | 8687 |
| httpStatus | absent |

The harness-stage judgment in the same arm completed 4 of 4 requests and was
`decided`/`supported`.

## What the source proves

- One `evaluate` call is one request, with `timeout: config.timeout ?? 5_000`
  and `retry: { maxRetries: 0 }` at `extensions/jev-learning.ts:431`.
- The failure mapping at `:505-510` sets `cancelled` for an abort, `timeout` for
  `APITimeoutError`, and `unavailable` otherwise. It records `httpStatus` only
  when the error is an `APIError` with a status from 400 to 599.
- A decision requires every window to complete. One failed request makes the
  whole review a proposal, which is why the Memory plan was not applied.

## Inference

1. The three failures were **not timeouts**. The reason would be `timeout`, and
   three 5-second timeouts cannot fit in 1945 ms.
2. They were **not status-bearing HTTP errors**. `httpStatus` is recorded for any
   `APIError` with a 4xx or 5xx status, and it is absent.
3. They were **not aborts**. The reason would be `cancelled`.
4. Therefore they were connection- or transport-level errors with no HTTP status.

## Corroboration from the proxy counters

The run's `summary.json` records 8 Jev requests and usage for 5 of them. The
memory leg's one completed request used 8687 input tokens, which matches the
first `jevUsage` entry (8687). The harness leg's 21259 input tokens are exactly
the sum of the other four entries (3899 + 7695 + 8441 + 1224). So the 8 requests
are 1 memory completion, 4 harness completions, and 3 failures with no usage.

## Concurrency shape

The memory review issues its windows in one parallel round of up to
`MAX_BATCHES = 4`. All four memory requests therefore went out concurrently: one
succeeded and three failed. The later harness review also issued four concurrent
requests and all four succeeded. A systematic limit, a bad key, or a size bound
would fail both legs; both are excluded. The failure was partial inside one
concurrent round, which is the signature of transient transport flakiness.

## Verdict

**Cause: transient connection-level Jev transport failures inside one concurrent
round of four requests.** It is not a semantic judgment, not a bounds or
window-count defect, not a timeout, and not a status-bearing provider rejection.

The pipeline behaved correctly under the failure: it kept the reason, made no
decision, applied no Memory, and released no constraint. The cost of the
flakiness is that the whole Memory learning opportunity was lost, because
`maxRetries` is 0 and a single failed request blocks the review.

## Recorded evidence gap

The telemetry keeps only the coarse reason and the counters. It cannot tell a
connection error from a provider rejection after the fact, and the retained run
artifacts hold no per-request detail. The handoff already names this gap: keep a
controlled failure class without raw error bodies.

## Bounded fix

1. Record a controlled `failureKind` (`connection`, `http`, `timeout`,
   `aborted`, `unknown`) per failed request, and aggregate the first failed kind
   where the telemetry already aggregates `httpStatus`.
2. Retry a request once when, and only when, the failure is connection-level: no
   HTTP status, not a timeout, and not an abort. The retry re-issues the same
   frozen request, so it cannot invent a result; the parent still re-checks
   evidence freshness before any write. Record `retriedRequests` so cost and
   latency claims stay honest.

Not changed: `maxRetries` stays 0 at the SDK level, the decision rules are
unchanged, no partial semantic acceptance is added, and the parent keeps write
authority, transactions, and freshness checks.

## Fix verification

- Scenario: `features/jev-transport-recovery.feature` (four scenarios).
- RED: `tests/test_jev_transport_recovery.py` failed three tests before the fix
  (`KeyError: 'failureKind'` and the missing recovery).
- GREEN: the three new tests pass; the partial suite reported 83 passed with two
  call-count expectations updated under recorded justification (a retried
  connection failure costs one extra attempt).
- Full package suite after the fix: **1086 passed in 422.92 s**, exit 0.
- `pnpm typecheck`: exit 0.
- Source: `extensions/jev-learning.ts` gained `failureKind` and
  `retriedRequests`, one bounded connection-only retry in the single-request
  path, the controlled failure class in the catch, and aggregation of both
  fields at all four combination sites.