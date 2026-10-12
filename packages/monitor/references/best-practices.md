# Engineering practices and implementation comparison

Compatibility baseline updated on 2026-10-12 to workspace Pi 1.1.0
CLI/types and Node 22.19.0 APIs. Current upstream documentation is checked
against that installed contract before adopting an API.

## Changes supported by reproductions

| Practice | Previous behavior and evidence | Implementation decision |
| --- | --- | --- |
| Apply backpressure before a hard resource limit | A 40 KiB burst of 20,000 short lines failed with `matcher_queue_limit` before the worker consumed it. | Pause both readable pipes at a soft queue watermark; drain buffered records as the matcher catches up, then resume. Keep hard limits as an explicit failure boundary. |
| Keep physical records intact | A 64 KiB prefix followed by `READY` falsely matched `^READY$` after fragmentation. | Never evaluate a continuation as a fresh line. An over-budget physical line fails with `matcher_line_limit`; the diagnostic tail remains bounded. |
| Bound the aggregate result before IPC | Overlapping named groups returned a 415,047-byte terminal object despite individual capture limits. | Bound serialized named captures in the worker, omit unused positional captures, prioritize the JSON capture, and disclose incomplete fields with `capturesTruncated`. |
| Distinguish an absent value from an empty value | An empty named `json` capture skipped parsing and hid its error. | Parse every participating JSON capture. Preserve regex status, report parse errors, and never parse a budget-truncated JSON value. |
| Use a monotonic clock for durations | Moving the wall clock backwards by 60 seconds produced a negative timeout duration. | Keep epoch timestamps for display, but calculate every elapsed duration from a monotonic start. |
| Roll back a partially acquired resource | A synchronous worker-construction failure left a started child and active monitor without its timeout. | Attach process handlers before acquiring the matcher, reclaim partial startup, and expose one failed outcome. |
| Honour cancellation before side effects | An already aborted invocation still started its shell command. | Reject before spawning; propagate cancellation while synchronous work is awaited. A background monitor owns its lifecycle after its acknowledgement. |
| Return data to programmatic callers | Codemode received monitor text instead of a terminal object. | Declare output schemas and return matching `structuredContent`, retaining existing text, details, IDs, and delivery rules. |
| Confirm finite completion after the process exits | Match mode can accept an idle partial prefix or a success line before a later failure. | Add optional `completion="exit"`: match newline/EOF records, keep the first candidate, and require exit zero; later failures, signals and timeouts remain authoritative. Preserve the match-mode default. |
| Preserve JSON integrity as a success requirement | Regex success can coexist with invalid or clipped JSON. | Exit mode reports `failure` with `invalid_json_result`; match mode retains its existing status plus diagnostics. Callers still validate required business fields. |
| Remove only exact duplication | Thirty overlapping captures cost 31,478 cumulative input tokens in the earlier native trace. | Emit explicit capture aliases for exact original string equality; retain bounded structured data and distinct values. The comparable trace fell to 12,583 tokens. |
| Preserve diagnostic chronology | Global repeat grouping reordered alternating A/B records. | Collapse adjacent identical records only, preserving the order of distinct records and bounded tails. |
| Measure fixed cost and routing alternatives | Long guidance/schema descriptions repeated in every request; small commands cost more than bash. | Shorten guidance and descriptions, document direct-bash and validated codemode choices, and report both beneficial and expensive workloads. |

The backpressure decisions follow Node's [stream guidance](https://nodejs.org/en/learn/modules/backpressuring-in-streams)
and [Readable APIs](https://nodejs.org/download/release/v22.19.0/docs/api/stream.html#readablepause).
A stream watermark is a threshold, so the application still needs a hard queue
bound. Pausing pipes also lets their finite capacity slow the producer, as
described by the [child-process API](https://nodejs.org/download/release/v22.19.0/docs/api/child_process.html).

Record-boundary preservation is an inference from the newline record semantics
in the [NDJSON specification](https://github.com/ndjson/ndjson-spec#3-functional-specification)
and the truncation discussion in [RFC 7464](https://datatracker.ietf.org/doc/html/rfc7464#section-2.4).
Monitor keeps JavaScript regex contracts; it does not require an NDJSON protocol.

Worker ownership and startup/error/termination handling follow the
[Node worker API](https://nodejs.org/download/release/v22.19.0/docs/api/worker_threads.html).
Elapsed-time measurement follows Node's [high-resolution performance clock contract](https://nodejs.org/download/release/v22.19.0/docs/api/perf_hooks.html#performancenow).
Pre-cancellation follows [AbortSignal semantics](https://nodejs.org/download/release/v22.19.0/docs/api/globals.html#abortsignalthrowifaborted).

The structured output contract comes from Pi's [extension guide](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md#tools)
and [codemode guide](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/codemode.md).
Both are verified against the installed v1 declarations and an offline execution
through Pi's codemode sandbox and normal nested tool dispatcher.

## Existing decisions retained

One interruptible matcher per monitor prevents a pathological expression from
blocking the main event loop or a shared matcher pool. This addresses the
failure mechanism described by [OWASP ReDoS guidance](https://community.owasp.org/attacks/Regular_expression_Denial_of_Service_-_ReDoS).
There is no added dependency, service supervisor, polling tool, or mandatory
structured-output format for child commands.

Session resources are cleaned up by an idempotent shutdown path. Pi v1 also
uses that lifecycle for runtime/session replacement; historical pre-v1 issues
are not treated as evidence of a current leak. Core peers remain `"*"` because
Pi's [package dependency contract](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md#dependencies)
requires the host-provided cohort. Development validation remains on Pi v1.

No speculative worker pool, global concurrency default, or heap-size setting is
introduced. Per-monitor input/result limits and pipe backpressure address the
reproduced failures; worker heap limits would not guarantee protection from
process-wide out-of-memory conditions.

## Verification boundary

The executable Given/When/Then regressions are in `features/` and `tests/`.
Use `tests/live_monitor.py` for the native offline CLI, RPC and PTY cases, and
read @tests/native-verification-current.md for their exact scope. These checks
do not establish real-provider behaviour, physical keyboard acceptance, or
Linux/Windows support.
The optimized comparison and exit-mode rerun are recorded in
@references/efficiency-and-accuracy.md. Their local serialized-input estimates
include actual native Pi history and tool declarations; lossy summaries and
truncated data are disclosed separately.

## Choose orchestration before compression

Read @README.md#design-alternatives-and-adopted-optimization for matched native
experiments. Group suitable small shell jobs into one bash call; use codemode
for related monitor contracts and preserve every required field. Keep dependency
order explicit: Promise.all is appropriate only for independent jobs. Do not
compare a single batch only against many separate native calls. Retain failure
and integrity information and distinguish payload equivalence from scheduling
and timeout equivalence.

Primary design references: [writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents)
and [code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp).
These support evaluating response relevance and orchestration; local snapshots
provide this package's measured savings and counterexamples.

## Execution policy in the system context

Read @README.md#injected-execution-policy for capability-dependent wording and
current cost estimates. Read active tools on every turn: recommend grouped bash
only when bash is enabled, and codemode batching only when monitor_start and
codemode are both enabled. Otherwise use direct monitor calls. Codemode is not
a required package or fixed host mode. Do not activate tools to satisfy advice.

Dependency ordering, complete required payload/failure data, deadline, authority,
business validation and delivery rules remain explicit. Native provider tests
verify capability-present/absent injection, not real-model policy adherence.
The optional codemode recipe preserves full terminal diagnostics on failures.
