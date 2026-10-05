# Token efficiency and accuracy: measured evidence

Measured on 2026-10-04 with Pi 1.0.0 on macOS, Node 24.16.0 and tiktoken
0.14.0. Monitor reduces model-facing noise substantially for noisy workflows.
Small outputs, complete large payloads and distinct captures can cost more.
Use the new optional `completion="exit"` for finite workflows; the default
`completion="match"` retains compatibility. Callers validate business success.

## Optimization and current verification

- Exit mode evaluates only newline/EOF records, keeps the first success
  candidate, and requires exit zero. Later failure patterns, nonzero exits,
  signals, matcher errors and timeouts override the candidate. Invalid or
  clipped participating JSON produces `failure` / `invalid_json_result`.
- Model-facing text emits each exact original capture string once and uses
  explicit aliases for repeats. Structured captures and expanded human details
  remain complete within their existing budgets. JSON aliases refer to the
  visible canonical `result=` serialization, not original JSON whitespace.
- Diagnostics collapse adjacent identical records only, preserving order.
  Shorter prompt and schema descriptions reduce fixed context cost while
  retaining workflow choices, integrity checks and untrusted-output guidance.
- The package suite passed 87 tests, including the 107-case process matrix.
  Repository typechecking passed after an unrelated concurrent subagents
  typecheck failure cleared. The independent review ran ten further
  adversarial probes without a confirmed defect.
- The expanded native CLI/RPC/codemode matrix passed 36 cases / 44 monitor
  calls, including 16 exit-mode cases. It runs actual scoped monitor
  typechecking, actual boundary tests and an intentionally invalid TypeScript
  file to verify failure diagnostics.
- Six native CLI/JSON/RPC/TUI cases passed again, including 80×24 and 40×6
  terminal layouts.

The earlier 107-case matrix contains 83 single-monitor parameter cases and
24 shared-manager cases, including 16 seeded first-match cases. Its most recent
four full recorded runs passed. Earlier history recorded 618 monitor executions,
including one failing 107-case run whose failing case identity was lost in
truncated output. Its cause remains unresolved; the recorded history does not
establish a 100% pass rate or guaranteed stability.

## What actually ran for token measurement

The optimized default-mode comparison used four routes for each of 14
workloads: native bash without the extension, bash with it loaded, direct
monitor, and codemode with a validated summary. Each session performed the same
command three times: **56 sessions, 168 commands, 224 scripted provider requests**.
A separate exit-mode sample covered quick output, noisy success, noisy failure,
24 KiB JSON and escaped budget-clipped JSON, using four routes and two repeats:
**20 sessions, 40 commands, 60 requests**. A bash row's completion label records
which comparison it belongs to; native bash has no completion parameter.

All provider responses were local scripts; no online model inferred tool
selection or business success. Commands actually executed through the installed
Pi runtime. Settings, working directories and new temporary bash logs were
isolated. Earlier independent review also ran 15 manager probes, five
registered-tool probes, six native comparisons and four additional transport
instances; those are separate from the current ten optimization probes.

## Measurement method

The comparison captures actual provider context after native tool execution,
then applies the installed Pi OpenAI Responses message/tool serializers.
System instructions, tool declarations, command arguments and previous results
are included. Native bash is compared using its actual truncated output, not
the much larger raw command stream. Injected marker fields demonstrate that
UI `details`, `structuredContent` and direct-tool `outputSchema` are excluded
from this representation. Codemode's visible declaration text still counts.

Both `cl100k_base` and `o200k_base` count serialized JSON locally using
[tiktoken](https://github.com/openai/tiktoken). UTF-8 byte counts, cumulative
input estimates and scripted assistant-content estimates are stored separately.
These are representation-based estimates, not online model usage, provider
billing, caching discounts or guarantees for every model's tokenizer. Random
IDs, temporary paths and elapsed values introduce small run-to-run variation.
Three repeats are three actual commands, not polling or retries of one command.
Cumulative input sums four growing provider contexts for three repeats, or
three contexts for two repeats. Do not compare those totals as equal workloads.

## Optimized default-mode results

Cumulative `cl100k_base` input estimates, three executions / four requests:

| Workload | bash, no plugin | bash, plugin loaded | monitor direct | codemode summary |
| --- | ---: | ---: | ---: | ---: |
| Quick small output | 3,254 | 4,902 | 5,225 | 9,422 |
| 2,000 noisy lines then success | 58,242 | 59,874 | 5,569 | 9,856 |
| 10,000 unique diagnostics then failure | 137,739 | 139,407 | 14,653 | 10,282 |
| Complete 24 KiB JSON | 21,866 | 23,514 | 23,908 | 9,686 |
| Thirty overlapping named captures | 6,346 | 7,998 | 12,583 | 10,278 |
| Chinese progress then success | 102,646 | 104,307 | 5,551 | 9,782 |

Compared with the pre-optimization monitor snapshot, overlapping captures fell
from 31,478 to 12,583 (−60.0%), quick output from 5,779 to 5,225 (−9.6%), and
noisy success from 6,134 to 5,569 (−9.2%). Representative initial extension
prompt/tool overhead fell from 548 to 412 tokens (−24.8%); individual contexts
vary slightly. This fixed cost repeats in uncached representations. Small
commands still cost more than bash, even with the extension already loaded.

The noisy-success case used 90.4% less input than bare bash, the unique-failure
case 89.4% less and Chinese progress 94.6% less. Complete 24 KiB JSON cost
9.3% more than bare bash, and the overlapping-capture case still cost 98.3%
more: its distinct clipped value, capture names, regex and fixed overhead remain.
Full payloads and genuinely distinct values cannot be discarded for savings.

Codemode validates status, JSON integrity and the predeclared required length,
then emits that length instead of a large string. Failure summaries retain only
the last three diagnostic lines. This is task-specific projection. Escaped
JSON exceeds the aggregate serialized capture budget even when the raw capture
fits; its low match-mode count is excluded from information-preserving savings.

## Exit-mode representative results

Cumulative `cl100k_base` input estimates, two executions / three requests:

| Workload | bash, no plugin | bash, plugin loaded | monitor direct | codemode summary |
| --- | ---: | ---: | ---: | ---: |
| Quick small output | 2,343 | 3,570 | 3,764 | 6,432 |
| Noisy success | 29,814 | 31,065 | 3,938 | 6,654 |
| Noisy failure | 29,898 | 31,121 | 9,419 | 6,912 |
| Complete 24 KiB JSON | 11,643 | 12,879 | 13,112 | 6,564 |
| Escaped budget-clipped JSON | 51,447 | 52,686 | 34,662 | 37,332 |

Exit mode correctly fails the clipped-JSON case and includes its bounded
failure diagnostics. That report is larger than match mode's success-with-error
report because its outcome and diagnostics differ. It is not a comparable
lossless compression case. Valid small or large complete JSON retained its
expected value in the exit-mode checks.

## Accuracy and wake-up boundaries

The cases check status, payload, parse errors, IDs, one terminal notification,
absence of duplicate delivery, budgets and shutdown. Remaining boundaries:

- Match mode may accept a newline-free prefix idle for 150 ms, and its first
  success can precede a later failure. Exit mode avoids these paths by matching
  complete records and confirming natural exit. It retains the first candidate;
  a later valid JSON sentinel cannot replace an invalid first one.
- Valid JSON can contain a business field saying failure. Check required
  fields and any required capture truncation before proceeding. Regex matching
  uses raw output: ANSI-wrapped text does not satisfy `^DONE$` unless accounted
  for. Emit plain, unique sentinels after final verification.
- Terminal tails and captures remain bounded. Adjacent repeats preserve the
  order of distinct diagnostics, but the report cannot reconstruct full logs.
- Untrusted text may reach context. Offline scripts do not establish a real
  model's resistance to prompt injection or its choice of tool and contract.

Three identical delayed DONE/FAIL/DONE jobs in direct RPC caused four scripted
provider requests and three custom wakes. The same jobs awaited inside codemode
`Promise.all` produced two requests and no custom wakes. Results are matched to
their command oracle and monitor ID, rather than completion order. This verifies
the scripted batching pattern rather than a real model's decision to batch.

## Practical choice and reproduction

The final optional `compact=true` comparison preserves the paired six-workload
commands, three repeats and bare-bash baseline. Twelve native Pi 1.0.2 sessions
executed 36 commands and 48 scripted requests. Encoded report payloads were
decoded and compared to the exact original report; full bounded structured
values were preserved. The current `cl100k_base` totals (bash / monitor) are:
noisy success 58,226 / 5,178; unique failure 137,743 / 14,260; Chinese progress
102,667 / 5,137; quick output 3,254 / 4,821; 24 KiB repetitive JSON
21,858 / 5,292; overlapping captures 6,346 / 6,301. The last difference is
near parity and sensitive to runtime/tokenizer variation, not a robust promise.
The small-output case still costs 48.2% more. The codec preserves the existing
bounded payload, including explicit capture truncation, rather than recovering
clipped original data. Default reports remain unchanged.

Both encodings and hashes are in `tests/token-results-compact-six.json`; the
latest table, codec format and validation limits are in the package README's
"Optional lossless report encoding" section. Reproduce using
`token-measurement.py --compact-six --output /tmp/monitor-compact-six.json`.
Earlier snapshots below and above retain their original contracts and versions.

The original six-workload table was rerun with native Pi CLI 1.0.2 on
2026-10-04: twelve sessions, 36 commands and 48 scripted provider requests.
The same default match-mode contract, three repeats and cumulative input
measurement were retained. All fixture assertions passed. The current direct
monitor counts are 5,590 (noisy success), 14,664 (unique failure), 5,561
(Chinese progress), 5,239 (quick output), 23,902 (24 KiB JSON), and 12,587
(overlapping captures). Both encoding metrics and hashes are preserved in
`tests/token-results-retest-six.json`; the comparison table appears in the
package README's "Six-workload retest" section. The previous Pi 1.0.0 evidence
above remains unchanged; CLI version and runtime fields differ between runs.

Use direct bash for short, small responses. Use monitor for noisy finite
workflows with `completion="exit"` and a unique newline sentinel after all
required verification. Capture necessary fields. Related jobs can use codemode
to wait together and return only validated decision inputs. Keep complete data
when the task requires it. Avoid broad readiness or success words as contracts.

Run from the source repository:

```sh
uv run --no-project --with pytest python -m pytest packages/monitor/tests/ -q
uv run --no-project --with tiktoken python packages/monitor/tests/token-measurement.py --output /tmp/monitor-token.json
uv run --no-project --with tiktoken python packages/monitor/tests/token-measurement.py --strict-representative --repeats 2 --output /tmp/monitor-token-strict.json
uv run --no-project python packages/monitor/tests/live_transport_matrix.py
uv run --no-project python packages/monitor/tests/live_monitor.py
```

Snapshots in repository `tests/`: `token-results-current.json` preserves the
pre-optimization measurement; `token-results-optimized.json` and
`token-results-strict.json` contain current metrics and content hashes;
`accuracy-results-current.json` preserves matrix history and
`transport-results-current.json` records 36 current transport cases. Full
synthetic token traces remain locally at `/tmp/monitor-token-final.json`,
`/tmp/monitor-token-optimized.json` and `/tmp/monitor-token-strict.json`.
Tests are not shipped in the npm package.

The final runner isolates bash temporary logs; 42 earlier logs with known
paths were removed. Some early failed probes lost trace paths, so potential
leftover logs were not guessed at or removed.

## Tiny-output follow-up

Read @README.md#tiny-output-follow-up for the five-route history and subsequent
six-route inactive-tool comparison. Small replies are dominated by fixed schema
and guidance costs. Compact direct pure success omits repeated label, UUID and
elapsed time while retaining native tool-call correlation and full metadata.
Payloads, parse/truncation warnings and asynchronous reports keep their context.
Minimal arguments change label/deadline policy; they are not equivalent when an
explicit deadline is required. Active monitor remains more expensive than bare
bash. Inactive unused monitor omits guidance; restored monitor results or
compaction/branch summaries retain it. The package does not select or disable tools automatically.

Latest six-route cl100k estimates: bare bash 3,250; loaded bash 4,366; compact
original 4,494; compact minimal 4,420; minimal exit 4,474; inactive loaded bash
3,250. Inactive/bare o200k estimates are 3,276/3,280. These are native offline
contexts across 18 real command executions and 24 scripted provider requests,
not billing or real-model routing evidence. Snapshots: tests/token-results-tiny.json
and tests/token-results-tiny-inactive.json. Historical tables remain unchanged.

## Expanded retest

Read @README.md#expanded-retest for workload definitions, repairs, native counts
and accuracy limits. All estimates below are cumulative cl100k input/tools across
three real executions / four scripted requests per route. Compact monitor uses
exit completion, an explicit label and a five-second deadline. Bash executes
the identical command with the same requested deadline; timer startup semantics
remain host-specific. Required JSON equals the oracle; progress logs are
intentionally omitted. Different route contracts must not be conflated.

| Workload | Bare bash | Loaded bash | Compact exit | Inactive bash | Change vs bare |
| --- | ---: | ---: | ---: | ---: | ---: |
| json-repeat-0 | 3,428 | 4,548 | 5,008 | 3,432 | +46.1% |
| json-repeat-1 | 3,430 | 4,550 | 5,027 | 3,438 | +46.6% |
| json-repeat-16 | 3,440 | 4,556 | 5,031 | 3,444 | +46.2% |
| json-repeat-128 | 3,524 | 4,640 | 5,106 | 3,520 | +44.9% |
| json-repeat-512 | 3,808 | 4,924 | 5,393 | 3,812 | +41.6% |
| json-repeat-2048 | 4,966 | 6,086 | 5,269 | 4,974 | +6.1% |
| json-repeat-8192 | 9,578 | 10,694 | 5,274 | 9,578 | -44.9% |
| json-repeat-24576 | 21,866 | 22,982 | 5,266 | 21,862 | -75.9% |
| json-nonperiodic-128 | 4,314 | 5,430 | 5,914 | 4,306 | +37.1% |
| json-nonperiodic-512 | 5,626 | 6,730 | 7,220 | 5,610 | +28.3% |
| json-nonperiodic-2048 | 10,862 | 11,974 | 12,485 | 10,858 | +14.9% |
| json-nonperiodic-8192 | 31,566 | 32,694 | 33,196 | 31,582 | +5.2% |
| json-nonperiodic-24576 | 87,090 | 88,202 | 88,709 | 87,082 | +1.9% |
| unique-progress-1 | 3,594 | 4,714 | 4,862 | 3,598 | +35.3% |
| unique-progress-8 | 3,934 | 5,050 | 4,862 | 3,934 | +23.6% |
| unique-progress-32 | 5,152 | 6,272 | 4,862 | 5,160 | -5.6% |
| unique-progress-128 | 10,150 | 11,262 | 4,854 | 10,154 | -52.2% |
| unique-progress-512 | 31,654 | 32,754 | 4,862 | 31,650 | -84.6% |
| unique-progress-2048 | 119,623 | 120,751 | 4,874 | 119,599 | -95.9% |
| json-false | 3,278 | 4,398 | 4,854 | 3,282 | +48.1% |
| json-null | 3,282 | 4,398 | 4,837 | 3,274 | +47.4% |
| json-zero | 3,290 | 4,410 | 4,865 | 3,290 | +47.9% |
| json-empty | 3,300 | 4,424 | 4,877 | 3,312 | +47.8% |
| json-unicode | 3,806 | 4,918 | 5,398 | 3,806 | +41.8% |
| stderr-success | 3,254 | 4,378 | 4,540 | 3,254 | +39.5% |
| EOF-success | 3,254 | 4,366 | 4,546 | 3,258 | +39.7% |
| empty-capture | 3,260 | 4,368 | 4,843 | 3,260 | +48.6% |
| late-nonzero | 3,336 | 4,452 | 4,895 | 3,336 | +46.7% |
| late-failure | 3,418 | 4,538 | 5,124 | 3,422 | +49.9% |
| invalid-json | 3,284 | 4,404 | 5,064 | 3,280 | +54.2% |
| no-output | 3,174 | 4,294 | 4,730 | 3,178 | +49.0% |
| partial-near-match | 3,386 | 4,502 | 5,021 | 3,382 | +48.3% |

Unicode/C1 post-hardening native follow-up: Unicode bare/loaded/compact/inactive
3,806 / 4,922 / 5,430 / 3,802; C1 3,590 / 4,698 / 5,241 / 3,590. Both full structured
payloads and parsed model-facing JSON equal the oracle. Snapshot filenames and
source reproduction are in the package README. The 32-row matrix precedes the
C1/Unicode escape hardening; the affected Unicode case was rerun separately.

Eight-repeat short comparison: bare and inactive bash 8,838; loaded bash 11,340;
compact original arguments 12,060; minimal arguments 11,655; minimal exit
11,979. This does not establish automatic routing or universal token savings.

## Design alternatives

Read @README.md#design-alternatives-and-adopted-optimization for the revised
compact successful-payload envelope and comparisons against both separate
and grouped bash. Current optimized direct valid success preserves every
payload/capture but uses native call correlation instead of repeated identity
text. Default, asynchronous, failed and diagnostic reports retain their contract.

The final envelope and orchestration snapshots are token-results-design-envelope.json
and token-results-design-batch.json under tests/. They record 30 native sessions,
150 actual commands and 138 scripted provider requests. Earlier prototype runs
are excluded. Orchestration returns complete required JSON; grouped bash is
sequential with explicit child/outer deadlines while monitor is parallel.
Inherited per-row summaries were corrected to reflect these actual semantics
without changing numeric evidence or content hashes. Eight-job batching reduces
round trips but is not intrinsically cheaper than a well-grouped bash workflow.

## Injected policy overhead

The later execution-policy update adds grouped bash, compact replies, batch
ordering and required payload/failure preservation to before_agent_start. Exact
prompt-only estimates: cl100k 80 -> 114; o200k 82 -> 117; 586 characters. This
is a fixed-cost increase, not a claimed savings. Existing comparisons were run
before this update and remain historical; do not reinterpret them as post-update
measurements. Read @README.md#injected-execution-policy for current wording,
provider-boundary verification and model-adherence limitations.

## Capability-dependent policy

The subsequent correction makes codemode optional: read active tool names on
every turn, recommend it only alongside active monitor_start, and recommend
bash only when active. Registered-hook prompt estimates now vary by capabilities:
bash+monitor 108/111 cl100k/o200k; adding codemode 116/119; monitor-only 97/99.
Inactive unused monitor contributes zero guidance. Native present/absent tests
verify actual system-context injection. Earlier fixed-policy cost and workload
tables are historical. Read @README.md#injected-execution-policy for scope,
activation changes and unmeasured real-model routing/billing outcomes.
