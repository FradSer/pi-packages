# Subagents local audit verification

Audit: 2026-10-03; final verification: 2026-10-04 (Asia/Shanghai). Status: the requested local subagents audit is complete. The final candidate implements independent durable history for each parent session and passes full-package verification, native concurrent/reopen acceptance and independent review.

## Coverage and execution boundary

The audit covers all 27 `src/*.ts` modules, the root entry and package manifest,
31 feature contracts, and 48 Python test files with their TypeScript fixtures.
It includes runtime transport, exact session controls, cancellation, queued input,
result delivery, identity discovery, Memory, workspace/history paths, migration,
tool selection, public result formatting and passive TUI rows.
Pre-existing repository changes are preserved; the complete working-tree diff
must not be attributed to this audit.

Native evidence uses the repository's installed Pi 1.0.0, actual parent and child
processes, real RPC parsing, and native TUI execution through a PTY. Temporary
HOME/configuration and generated fixture credentials isolate these runs from
personal authentication. Scripted model streams use a loopback provider.
This proves the harness and protocol behavior under those streams; it does not
measure external-provider reliability or model judgment. PTY keyboard/resize
verification is automated terminal interaction, not physical keyboard acceptance.

## Confirmed defects and repairs

- A final JSONL record without LF was lost on child close. The decoder and tail
  now flush before final exit delivery.
- A synchronous close callback starting a same-name successor inherited or
  overwrote its turn baseline. Incarnation ownership now guards old stream writes;
  a successor begins at zero and reports its first completed turn as one.
- The intent startup adapter accepted an identity without a prompt. Nonempty
  input is now required before reserving or starting a child.
- Invalid result turns and timestamps were accepted; a finite date outside the
  ECMAScript range could throw while formatting reports. Invalid metadata is
  refused or omitted at its readback boundary while authored text is preserved.
- A diagnostic preview could split a UTF-16 surrogate pair. The display boundary
  now keeps complete pairs, and blank cancellation reasons use a stable fallback.
- Private Memory entries/indexes, definitions and migration inputs could accept
  hard links. Writes/discovery now reject linked or nonregular candidates, and
  private replacement files publish through owner-only atomic temporary files.
  A linked index is checked before an append creates a new entry.
  Child Memory binding applies the same single-link definition check as discovery.
- Same-title proposals recorded in one millisecond could overwrite each other.
  Unique suffixes retain both candidates. A proposal also enforces the complete
  serialized UTF-8 16 KiB budget before any directory or file is created.
- Several native fixture parents inherited ambient credentials/startup hooks or
  selected a global Pi binary. They now use explicit temporary environments and
  the installed repository cohort; regressions cover both isolation boundaries.
- Initial prompt, idle readiness and in-memory fork setup used the same five-second
  deadline as controls for a running child. That included loading Pi and its
  explicit extensions, cancelling valid cold starts. Startup confirmation now has
  a separate thirty-second window; running input and steering retain five seconds,
  as does the kickoff after fork setup confirms a loaded child. Expiry remains
  uncertain and never repeats input.
- An intermediate message could retain an arbitrarily large tool-call identifier
  in its per-input duplicate set. Parser and injected callback boundaries now
  enforce a 1024-byte UTF-8 identifier limit before retaining it.

Feature scenarios precede failing regressions and fixes. Recorded RED evidence
includes the lost close tail, successor `turns=0`, missing startup prompt,
malformed result metadata, linked writes, timestamp collision, oversized proposal,
report `RangeError`, and ambient native fixture inheritance. An isolated mutant
retaining the identifier-limit export but removing the parser/callback guards
accepts a 1025-byte ID at both boundaries, confirming functional RED evidence
beyond an initially missing export. GREEN boundary tests preserve exact 1024-byte
ASCII/multibyte IDs and an exact 16 KiB multibyte proposal without truncation.

## Requirement proof map

| Requested behavior | Authoritative evidence | Remaining proof |
| --- | --- | --- |
| Real Pi child execution with a minimal grant | `test_live_resident_contract.py` observes the actual OS spawn, correlated RPC ACK, parsed result and child closure | External model quality is not measured |
| Temporary by default, reusable until stop/parent exit | `test_live_temporary_resident.py` checks two inputs in one incarnation, IDLE settlement, explicit stop and no durable home; `test_live_agent_usage.py` checks parent shutdown | None for the tested lifecycle |
| Parent input and distinct intermediate/final responses | `test_live_parent_message.py` checks real queued input, exact session/input identifiers, separate custom types and FIFO; bound/race tests cover invalid and stale callbacks | None for the standalone channel; hosted support is explicitly refused |
| Durable Memory and private history survive restart | The native resident case resumes saved history; `test_live_durable_storage.py` executes real `agent_memory` append and shared scratch operations; the parent-history case reopens actual persisted parent sessions and reads shared data | None for the tested lifecycle |
| Each parent session uses independent durable history | `test_live_parent_session_history.py` holds two real RPC children at a provider barrier, observes different parent IDs/history paths, then reopens both actual parent files and verifies exclusive old markers, four successful shared-data reads and six child closes | Concurrent copies of one logical parent ID are outside this partition policy |
| Own ordinary scratch, usually work in the parent's project | The native durability case writes and reads shared scratch, observes actual spawn cwd, and executes relative file operations in A and B; scratch remains an ordinary directory | None for the tested workspace behavior |
| Clear, passive TUI display | Native usage/parent-message PTY cases observe progress/result text and keyboard/resize execution; `test_agent_row_tui.py` verifies registered renderer width, expansion and malformed fallback | PTY output is not a pixel-level or physical-input assertion |

## Verification

The final parent-isolation candidate passed all **566 package checks in 659.57 seconds**:
`python3 -m pytest packages/subagents/tests/ -q -x` exits zero. SHA-256 values for
all 133 source, manifest, feature, Python/TypeScript fixture and guidance files
stay unchanged from before that run through its completion. The
[candidate hash record](e2e-candidate-sha256.json) preserves the exact verified
files, including the four root-level fixtures referenced by package tests,
package guidance and the Changeset. Both root README policy paragraphs are
checked separately because unrelated coordination edits continued during verification.
The pre-isolation candidate passed 549 checks in 399.89 seconds with 123 stable
hashes. Earlier channel/pre-channel runs passed 548/534 checks; those earlier
totals are not added to the final run.
Interrupted or still-running checks are not passes.

The first parent-isolation full-package attempt finished with 556 passes and
three failures in 1761.55 seconds. Two shutdown-fixture Node processes exceeded
15-second execution bounds without stdout/stderr; a retry-exhaustion TUI case
missed its completion deadline. Observed host load averages were
460.62/671.10/476.46. With unchanged sources, the two shutdown cases passed in
4.72 seconds and the 14-case blank/truncated-output group passed in 40.72 seconds.
An observation-only preload recorded retry exhaustion, settlement, subsequent
input and child close. Anonymous Agentbook recall found no matching solution.
Two later fail-fast package attempts stopped at different print startup-confirmation
cases: 351 passes in 527.72 seconds and 359 passes in 535.48 seconds. They are
incomplete failed runs, not full-package acceptance. One startup case also passed
unchanged in 9.59 seconds after load declined. Concurrent root README edits to
separate coordination guidance are preserved; parent-history paragraphs remain intact.

Those repeated startup failures exposed the five-second cold-start budget issue
above. New virtual-clock Given/When/Then regressions reproduce four failures
before repair. Five new boundary checks pass after repair, including bounded
thirty-second expiry, late ACK handling and the unchanged five-second running
control deadline. The 56 affected transport/execution/parent-history/extension
checks pass. The native/fork group initially found one change-caused fixture gap:
a mock setup-timeout awaited thirty real seconds inside a twenty-second outer
runner. It now verifies the exact boundary with a virtual clock. Native blank
output jobs allow startup plus both scripted inputs and closure; all result,
request-count, history and closure assertions are retained. The corrected group
passes all 25 checks in 66.54 seconds, including parent overlap/reopen, print/TUI
and real temporary fork execution. The next frozen full run was interrupted deliberately after 387 passes in
484.80 seconds to include two regressions requested by the fresh reviewer.
Those cases cover post-fork kickoff expiry and cancellation followed by exact
stop, same-name replacement and late old-child events. Both initially pass in
2.84 seconds. The passing final package run above is a separate full run;
no overlapping attempt totals are added.

The linked-binding repair passes all 64
affected Memory/storage checks, six invalid-binding cases in the independent
review, and four isolated real Pi SDK binding probes: three valid disk scopes
register Memory, while a hard-linked user definition does not. These probes make
zero model requests. The initial ad hoc SDK probe excluded every tool and was
corrected to explicitly select `agent_memory`; that probe error was not a product
failure and is not counted as a passing run.

Checks completed for the final parent-isolation candidate:

- Root `pnpm typecheck`.
- `pnpm pack:check`: 18 workspace packed manifests.
- `pnpm --dir packages/subagents pack --dry-run`: entry, 27 source modules,
  authority/vision guidance and bundled role reference present.
- `pnpm check:install`: 17 installed packages and 18 settings entries.
- 14 focused root runtime-workspace and Pi dependency-cohort checks in 2.71 seconds.
- `git diff --check` and post-run fixture-process inspection.

Earlier audit verification also passed 95 kit checks, 44 focused root
output/prompt/entry/cohort checks and four subagents-only installation cases.
These overlap other runs and are not added to the final package total.

The earlier full package run passed 530 checks before the final review repairs.
There are 58 cases in `test_live_*.py`, including the earlier twelve configured print/TUI
cases; additional native SDK selection, retry and fork probes live in other files.
Do not classify every other package check as non-native.

A broader diagnostic run of `packages/agent-teams/tests`, `packages/kit/tests`
and root `tests` returned 498 passes and 25 failures before the final review
repairs. Failures include old task surface/output expectations and legacy bundle
fixtures invoking the inactive `agent` family in a fresh intent session. A focused
bundle reproduction exits without an E2E report or child; it is not successful
native acceptance. These consumer contracts have not been rewritten in this
subagents audit. No whole-repository clean result is claimed. A separate direct durable
`agent-teams` workflow still calls the legacy two-argument workspace helper;
that consumer has not been changed in this package audit. The public subagents
disk path skips a published host and supplies the parent ID to standalone storage.

## Independent review and resolved decisions

A fresh reviewer without implementation history read the full package surface.
Its first three confirmed P2 findings (successor baseline, report date range,
proposal quota) passed independent second-round reproductions after repair.
Second-round review also found that the child Memory binding accepted a linked
`agent.md` although discovery refused it. The final independent closure confirms
the fix, runs six invalid-binding and eight storage checks, and finds no remaining
confirmed scoped P1/P2 issue. It also repeats the extension TypeScript and pack
checks. Parent history isolation has its separate review below.

A fresh read-only review of the added native durability evidence found two test
proof gaps: resumed reads could match old tool results, and B did not have to
create private history. The frozen test now checks only current-input tool
results, the exact successful native tool frame sequence for every phase, and
new project-scoped B JSONL alongside unchanged A history/files. Independent
re-review closes both gaps with no remaining actionable finding. The reviewer
did not rerun this case; the root's latest isolated run passed in 3.40 seconds.
Each of its three phases observes one actual child, a final notice, successful
exact-session stop, and native closure. Shared Memory/scratch and the definition
remain byte-identical when B runs; the definition's mtime also remains unchanged.

### User-selected parent history isolation

The user chose independent history for every parent session. Both native tool
interfaces derive the trusted parent ID from Pi's SessionManager at execution.
History uses `projects/<project-slug>/parents/parent-<full-sha256>/session/`;
the digest preserves an opaque identity without exposing it in the path.
The same parent ID is stable across reopening; different parents select distinct
directories. Identity Memory and scratch remain shared, and child cwd remains
the original project. Existing project-only history is preserved without an
automatic import, move or deletion. The legacy two-argument path helper still
allows inspection of those old paths. Headless embeddings can provide a stable
`parentSessionId`; omission uses one process-local ID.

The installed Pi 1.0.0 SessionManager has no live-owner history lock: it continues
the most recent matching file and appends to it. Selecting different parent
directories avoids that shared-file path for distinct parent sessions. Reopening
the same parent session concurrently in two processes still denotes the same
logical parent; this change does not add a lock or a second-parent policy.

Given/When/Then scenarios preceded RED evidence: both tool interfaces and the
headless library originally supplied no parent ID, and new workspace cases
originally selected shared history. The integration/resident checks now pass
29 cases, workspace checks pass 32, and the extension typecheck passes. The native
overlap/reopen case passes in 14.07 seconds: both live parents cross an explicit
provider barrier, native spawn/close timestamps overlap, and reopening each real
parent session file preserves its ID and child history path. Historical marker
checks inspect context before the current user input; the new reopen prompt
contains no old history marker. Four real successful read calls per reopened
child retrieve both shared Memory entries and scratch files. Initial temporary
children have no session directory. Six actual child PIDs have confirmed closes,
successful exact-session start/stop receipts and one final per child. Fixture
result and close promises are renewed for successive children rather than reused.
The final full package run passes 566 cases. A fresh reviewer without
implementation history independently ran 36 parent-history/workspace/resident
checks in 51.14 seconds and closed its scoped findings. An initial hosted-disk
P1 was withdrawn after verifying the `scope === "session"` host guard, native
published-host refusal evidence and parent-aware standalone workspace call.
There is no remaining confirmed scoped P1/P2 finding. The reviewer made no edits.

The current goal explicitly requests a distinction between intermediate messages
and final results. This requirement is now included in the implementation scope.
The new child-only `agent_message` capability requires an explicit tool grant;
existing grants are preserved. Its intermediate notice is distinct from final
Session Results. The channel is implemented with 16 KiB per-message, 32-message
and 64 KiB aggregate per-input budgets, per-input duplicate suppression, and
sender-failure attribution that cannot overwrite a later input. The parent binds
the exact session and active input; the child receipt promises only `emitted`.
It neither settles work nor dispatches queued input. Targeted channel/runtime/TUI
checks pass. Three configured real Pi cases pass: granted print, granted PTY/TUI,
and ungranted print. They verify exact session/input attribution, queued receipt,
per-input duplicate suppression and cross-input identifier reuse, intermediate
before final ordering, one final per input, and separate notice types. The queued
state is observed as starting or working, with sequenceEnded=false; this is not
reported as invariably working. PTY output contains both progress and final text.
The gate releases from the parent's actual queued tool-result event; no child
session-file polling is used. The initial no-grant test fixture misclassified its
provider's final response and timed out; the classification was corrected and the
same case passes. That timeout is harness failure evidence, not product acceptance.
Independent channel review found one P2 identifier-memory bound, independently
confirmed ASCII/multibyte exact-boundary repair, and closed all its scoped findings.
The final 566-check result includes this feature and its three native
cases, the three-phase native durability case and the concurrent-parent/reopen case.

### Independent startup-budget review

A fresh reviewer without implementation history found no confirmed scoped
P1/P2 code issue in startup budget routing, acknowledgement ownership, expiry or
close/successor guards. Its two P2 evidence gaps concerned post-fork kickoff
expiry and the combined cancellation/stop/replacement/late-event path. Added
regressions exercise the real intent executor (`executeChildIntent`, see
ADR-0008), spawnResident, parser/control
map and roster/binding; only OS child creation and closure are mocked. The roster
expectation is a deep snapshot, so old events cannot mutate both sides of the
comparison. Independent re-review closes both gaps: the two new cases pass in
2.39 seconds and 23 other transport cases pass in 25.52 seconds. These runs
overlap and are not added. Its earlier complete parameter run hit a 15-second
runner timeout in the existing tail case; no source was changed for that timeout.
The root's affected group passes all 48 transport/cancellation/fork cases in
175.95 seconds, including tail; the two snapshot-corrected regressions also pass
separately in 5.15 seconds. Existing real native fork and process cases cover the
OS/RPC boundaries. The reviewer made no implementation edits and reports no
remaining confirmed scoped P1/P2 finding.

### Completion audit against the original objective

A final fresh read-only reviewer independently checks the original user goal,
the current sources and native assertions rather than treating this report as
proof. It confirms temporary lifetime, real Pi process/RPC execution, separate
intermediate/final messages, durable Memory and ordinary scratch, original-project
cwd, independent parent history with actual reopening, and passive TUI behavior.
It reruns six key native cases (6 passed in 18.40 seconds) and thirteen TUI/native
behavior cases (13 passed in 15.51 seconds), then recomputes all 133 recorded
hashes with no missing or changed file. These overlapping runs are not added to
the full-package total. No remaining required work or confirmed scoped P1/P2
issue is found for the original goal and the user-selected parent-history policy.
Same-parent-ID concurrent reopening remains the documented partition-policy
boundary rather than a distinct-parent isolation failure.

The reviewer also checks the installed Pi 1.0 sendMessage API and runtime.
That API returns void and the runtime catches asynchronous sendCustomMessage
errors internally; SessionNoticeSender is synchronous. An old extension comment
about consuming a returned Promise is stronger than the actual API contract,
but does not indicate an unhandled rejection in the current native path.

## Implementation references

- [Pi's official subagent example](https://github.com/earendil-works/pi/tree/main/packages/coding-agent/examples/extensions/subagent)
  uses separate Pi processes and streaming progress/result capture.
- [Codex harness collaboration](https://developers.openai.com/api/docs/guides/responses-multi-agent)
  separates queued messages from assigning further work and waiting for results.
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
  document restricted tool access, separate subagent context and optional
  persistent memory; their single-session subagent surface is distinguished from
  separate cross-session messaging.

The implemented extension is a child-only parent-message capability with
exact-incarnation/input attribution, a separate intermediate notice and a
bounded body. The parent can consume a successful `tool_execution_end` result;
this requires no new upstream Pi API. The child receipt promises only that
the message was emitted, while the parent supplies its trusted child/input
attribution. It does not settle the active input, mark a result complete, widen
a tool grant, dispatch a queued input, or introduce a peer/team dependency.
Hosted child runtimes explicitly refuse this capability; their channel remains outside this implementation.
