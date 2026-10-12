# Native offline monitor verification

## Current baseline: Pi 1.1.0 (2026-10-12)

The workspace CLI and all 18 packages declaring Pi peers now resolve core
modules to 1.1.0. Published host peer ranges remain wildcard compatible.
The isolated native runner passed all **10 cases**: print text/JSON, standalone
and mixed RPC, output consoles at 80x24, 40x6, 20x4 and 120x40, and complete
value consoles at 80x24 and 40x6. The existing transport matrix passed
**36 cases / 44 monitor calls / 75 scripted provider requests**, including
actual project typechecking, boundary regressions and located compiler errors.
These provider requests are in-process fixtures with no paid model calls.

The runners select the workspace CLI, whitelist the child environment, isolate
HOME and agent state, and deny ancestor project resources with `--no-approve`.
The UI probe disables built-in tools while retaining the tested extension tools.
Compilation uses the installed compiler directly, avoiding package downloads
under the disposable HOME. Set `MONITOR_ACCEPTANCE_OUTPUT` to a fresh output
parent to retain traces, raw stdout/stderr and PTY bytes on success or failure.
The recorded terminal text reconstruction is not an OS screenshot.

Current evidence is in `.artifacts/tester-army-integration/complete-gate-20261012/`,
with original failures retained. This proves local deterministic behavior on
macOS, not real-model quality improvement, Windows/Linux behavior, physical
keyboard acceptance or a live resize of one component. Older measurements below
retain their original versions and are not combined with this baseline.

## Earlier verification records

Verified on 2026-10-04 with the installed Pi CLI 1.0.0 on macOS.
The complete six-case run also passed after package-local coding-agent and tui
development dependencies were relinked to 1.0.0; the native TypeScript fixture
passed a separate strict typecheck against those dependencies. The final
six-case run passed again after monitor identities changed from resetting
counters to UUIDs, including native RPC terminal identity delivery.
All six cases passed again after the backpressure, physical-line, capture-budget,
monotonic-clock, and structured-output improvements.
The six-case runner passed again after exit-confirmed completion, exact-value
capture aliases, adjacent-only diagnostic compression, and shorter guidance.

Run explicitly from the repository root:

```sh
uv run --no-project python -u packages/monitor/tests/live_monitor.py
```

Six native acceptance cases passed:

| Case | Verified behavior |
| --- | --- |
| Print text | One monitor terminal returned from the tool, then one scripted response; no custom wake |
| Print JSON | Same result contract through the real CLI JSON event stream |
| RPC standalone | Pending acknowledgement, exactly one custom terminal with monitorId, then exactly one resumed scripted response |
| RPC mixed tool batch | Monitor waits for its terminal alongside a foreign tool; no duplicate custom wake or premature scripted response |
| TUI 80 columns × 24 rows | Console stays within terminal height; Enter discloses output; PageDown and End reach diagnostic-79; q returns to editor; console reopens and Escape closes it |
| TUI 40 columns × 6 rows | The same console behavior and bounded height in the compact layout |

The print/JSON/RPC cases also assert that progress text does not enter later
provider context, the unrelated fixture tool remains active, and monitor_stop
is absent once the terminal has arrived. Each transport case makes exactly two
in-process scripted provider requests. The fixture uses a fresh agent directory
and temporary project, `--offline`, and a local provider implementation; it
makes no real model or network request and does not change user settings.

The native fullscreen TUI initially failed: only Enter reached the console;
PageDown and End were consumed by Pi's fullscreen viewport. The same real PTY
input sequence passed after the console adopted the public focused-overlay API.
Small terminals hide the startup extension listing, so fixture readiness uses
its structured session trace rather than looking for a filename on screen.

Every child has a 35-second external watchdog and isolated process-group
cleanup. Temporary traces and terminal bytes are removed after each run.
This is explicit acceptance coverage, not a default pytest or real-provider test.
It does not establish Windows/Linux, other Pi versions, real authentication,
real model behavior, pixel screenshots, or physical keyboard acceptance.

Additional offline acceptance in `test_monitor_structured_tools.py` exercises
the installed Pi `executeCodemode` sandbox and normal `runToolCall` dispatcher.
Nested monitor calls return typed terminal objects and preserve JSON objects,
`false`, `null`, and `0` without parsing text. It does not use a real provider.
An independent probe also loaded the manager through Pi's current jiti loader
and executed its worker with a named JSON capture.

The independent concurrency review ran six further manager-level rounds with
stdout and stderr each producing approximately 1 MB of short records. Every
round matched its final sentinel, notified once, left no active monitor, and
completed shutdown. This is Node-level pressure evidence, separate from the
native transport and terminal cases above.

## Finite completion and token comparison rerun

The expanded `live_transport_matrix.py` passed 36 native cases containing 44
monitor calls. Sixteen exit-mode cases (eight each in print and RPC) cover
partial writes, success followed by nonzero exit, malformed JSON, scalar JSON,
late failure patterns, candidate timeout, EOF records and signals. Other cases
include mixed/nested delivery, actual monitor typechecking, actual boundary
tests and an intentionally invalid compiler fixture. The typecheck command is
scoped to monitor so unrelated repository edits cannot change that oracle.

Three identical delayed DONE/FAIL/DONE jobs use four scripted provider
requests and three custom wakes in direct RPC, and two requests with no custom
wake in codemode `Promise.all`. Results are correlated by monitor ID and their
command oracle, rather than completion order.

The optimized token runner executed 56 native sessions/168 commands/224
scripted provider requests. A separate exit-mode representative runner executed
20 sessions/40 commands/60 requests. Snapshots are in
`token-results-optimized.json` and `token-results-strict.json`; read
@references/efficiency-and-accuracy.md for local tokenizer methodology and
counterexamples to universal savings. An independent review ran ten additional
adversarial probes against the optimized behavior, with no confirmed defect.
The README's two-job JavaScript example also ran verbatim through native
`executeCodemode` and `runToolCall`, returned `counts=[3,5]`, and emitted no
duplicate custom terminal message.

## Optional lossless reports

Native acceptance was rerun successfully on Pi CLI 1.0.2 after optional
`compact=true` reports and reduced prompt/schema descriptions. The runner now
accepts stable Pi 1.0.x and prints the actual runtime version; it previously
stopped at its exact-1.0.0 guard before executing any cases on 1.0.2.
The six CLI/JSON/RPC/TUI cases passed. Package verification reached 89 passing
tests; affected report/schema/guidance checks were rerun after description
cleanup. Independent review exercised 500 seeded payload roundtrips (402
encoded), six additional registered-tool headless/custom outcomes and bounded
payload timing probes. Unicode line-separator hardening was added following
that review. Encoding preserves the existing bounded payload; it cannot recover
captures already clipped by resource limits. No real model was used.

## Tiny replies and inactive guidance

The follow-up suite reached 92 passing tests. Compact pure direct success keeps
native call_id correlation and full metadata; falsy JSON values, empty named
captures, warnings and asynchronous results retain the full report. The new
inactive-tool regression failed before implementation and passes with no active
tool mutation; restored custom/tool results and compaction/branch summaries keep safety guidance.
Six-route native offline measurements executed 18 commands / 24 scripted
provider requests. Inactive loaded bash approximately matches bare bash; active
monitor remains more expensive. Read token-results-tiny-inactive.json and the
package README for exact numbers and changed default-deadline policy.

## Expanded retest

Final package suite: 96 passed in 155.00 seconds. Whole-repository typecheck
and strict monitor/fixture checks passed. Native CLI text/JSON, direct/mixed RPC
and standard TUI probes passed on Pi 1.0.2. Additional native TUI probes passed
at 120x40, 20x4, 80x24 and 40x6. A busy-run fixed-delay console-open observation
failed once; the runner now waits up to four seconds for a real frame, and all
four dimensions were rerun successfully. This is a harness observation repair.

The 36 native transport cases / 44 monitors passed, including mixed/nested,
codemode batches, deadline, signal, stop and exit-mode failure overrides.
Expanded measurements covered 33 unique workloads across 154 completed native
measurement sessions / 492 command executions / 646 scripted provider requests
(including repeated workload follow-ups). Failed discovery probes are excluded.
Snapshots and per-route comparisons are documented in the README.

New tests exercised actual Pi SessionManager history, Unicode record separators,
regex dot versus all-character contracts, and JSON C1 preservation. JSONL record
parsing and valid C1/DEL/Unicode JSON report escaping were repaired with failing
regressions before fixes. Independent review passed ten adversarial probes and
ten targeted tests. The final complete suite includes those regression tests.
No real model or paid provider was invoked; routing/decoding accuracy remains
separate from the deterministic payload/status correctness verified here.

## Design alternative verification

Final package suite: 97 passed in 297.41 seconds while native design probes
were running. Repository typecheck, strict monitor/fixture typecheck, install
validation and package dry-run passed. The six standard CLI/JSON/RPC/TUI
acceptance cases passed on Pi 1.0.2 after extending compact successful direct
replies to retain payload/captures while omitting repeated label/identity/timing.
A new registered-tool payload regression failed before implementation and passed
afterward; scalar, default, asynchronous and diagnostic contracts remain covered.

The adopted-envelope comparison ran 18 native sessions / 54 commands / 72
scripted requests. The full-payload orchestration comparison ran 12 sessions /
96 commands / 66 requests, including a single grouped bash call as a matched
payload/count baseline. Grouped bash is sequential with child 5s/outer 40s
deadlines; codemode is parallel with per-job deadlines and its native outer
execution policy. Timing semantics differ and latency was not measured.

Independent review passed 16 targeted tests, seven native correlation/payload
probes and all 12 batch comparison sessions. It identified stale documentation
contracts and inherited inaccurate equivalence strings; both were corrected.
No changed-runtime defect was confirmed. Snapshots retain numeric estimates and
content hashes, with equivalence corrections explicitly noted.

The README eight-job full-payload JavaScript recipe ran verbatim through native
Pi codemode after documentation updates: eight complete 512-byte JSON payloads
were validated, using two provider requests. This verification is additional
to the final comparison session counts above.

## Injected execution policy verification

Final suite: 98 passed in 184.39 seconds. A registered-hook regression failed
before the policy update and passed afterward. A native provider test confirms
grouped bash, compact replies, independent Promise.all, dependency sequencing,
required payload/failure retention and existing safety rules appear in serialized
system context. Inactive/history regressions remain covered.

Six CLI/JSON/RPC/TUI cases passed on Pi 1.0.2. Repository/scoped typechecks,
installation and package validation passed. The revised README batch recipe
ran verbatim with eight complete JSON results; a nonzero-exit command variant
returned full failure reports for all eight jobs, including identities, exit
codes and process-exit reasons.

Guidance-only tokenizer estimates: cl100k 80 -> 114, o200k 82 -> 117; 586
characters. Prior comparison snapshots precede this update. Native injection
verification does not establish real-model routing or billed-token outcomes.

## Optional capability correction

Codemode is no longer a fixed injected recommendation. Every turn reads the
current active tools: bash suggestions require bash, and codemode/Promise.all
suggestions require both monitor_start and codemode. Direct monitor calls are
the fallback. No host selection is mutated. Restored-history safety remains
present while inactive tools are not advertised.

The new capability regression failed before implementation. Final suite passed
100 tests in 182.27 seconds; six native CLI/JSON/RPC/TUI cases passed. Both
absent and enabled codemode cases passed native provider-context assertions.
Activation-switch and missing-bash combinations passed registered-hook checks.
Independent review verified SDK active names, 47 package/guidance tests and
two native capability cases, with no confirmed issue.

Repository typecheck initially reported an unrelated GoalStore.invalidate error
in goal/core.ts; it passed on the final rerun without this task editing goal.
Scoped monitor/fixture typecheck, installation and package verification passed.
Current raw guidance estimates: bash+monitor 108/111 cl100k/o200k, with codemode
116/119, monitor-only 97/99. Snapshot: guidance-capabilities-current.json.


## TUI rendering follow-up (2026-10-04)

- Before implementation, long-name/status and live-refresh regressions failed on
  the existing console. Six viewport checks then passed; a seventh checked actual
  live output before termination and absence of closed-console repaint.
- Full package suite: 103 passed in 192.93s. Registered-extension suite: 42 passed.
- Independent review reproduced Kitty CSI-u question-mark failure. Its subsequent
  regression failed before the fix; final console suite: 8 passed in 23.30s.
  The decoder is present in local Pi TUI 1.0.0 and installed Pi TUI 1.0.2; raw
  navigation sequences stay untouched. Release and Ctrl+x input are excluded.
- Native Pi 1.0.2: text, JSON, RPC standalone/mixed and 80×24/40×6 TUI passed.
  Native console checks at 80×24, 40×6, 20×4 and 120×40 were repeated after the
  keyboard fix: CSI-u help, help/output tail, close and reopen passed.
- Root typechecking, installation validation (17 packages / 18 entries), package
  dry-run and diff whitespace validation passed after the final implementation.
- This uses offline scripted providers and real PTY input/rendered text frames.
  No model requests or live terminal screenshots are used. Screen readers,
  terminal zoom/font rasterization and actual light/dark contrast are unverified.

- Review follow-up also reproduced xterm modifyOtherKeys help failure. That
  regression failed before the public `parseKey` exact-key whitelist fix. Final
  focused tests pass both protocols' help/close keys and exclude Ctrl/Alt/release
  input. Typechecking passed again, and native four-size acceptance was repeated
  with xterm-encoded question mark.
- Final independent review: no additional actionable issue; 8 console checks
  independently passed in 21.84s.

## TUI outcome and value-disclosure retest (2026-10-04)

The expanded native runner passed all **10 cases** on installed Pi **1.0.2**:
print text, print JSON, standalone RPC, mixed RPC, console at 80×24, 40×6,
20×4 and 120×40, and full JSON value disclosure at 80×24 and 40×6.
The value probes execute a 24 KiB JSON-producing command, verify that its tail
is initially folded, press v and End to reach the complete value tail, open
help through xterm input, close, reopen and restore the native editor.
These are isolated, offline scripted-provider PTY interactions.

Six added regressions cover terminal status/color on tool and custom-message
surfaces, Unicode-aware previews and full-value parity, metadata priority,
adaptive twelve-job widget budgets, full values after restoration/history
eviction, and stopped rows with a real SDK Theme instance. Independent review
reran the six regressions successfully. The 24 KiB example uses 11 expanded
transcript rows at 80 columns instead of 316, while its structured body retains
all 24,000 characters. Screen readers and actual rendered theme contrast remain
unverified.

Final full package run: **110 passed in 214.84 seconds**. Root typechecking,
installation validation, monitor packaging dry-run and README relative links passed.

## Startup presentation/provider-boundary retest

The expanded ten-case native runner passed again after startup rows adopted
shared pending styling and persisted effective UI configuration. Actual provider
contexts passed through Pi's OpenAI Responses converter. Replacing tool-result
details with a UI-only marker left the converted request input identical; no
startConfiguration field appeared in it. This verifies that boundary only,
not universal provider behavior or a billing reduction.

The package run passed 112 tests. A later whitespace regression plus the two
startup snapshot tests passed as a separate three-case run, also independently
reviewed. Startup snapshots preserve command/regex/cwd spaces and newlines;
tab/CR controls are explicitly escaped. Typecheck/install/pack checks passed.
