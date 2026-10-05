# Test suite simplification

Status: complete. Runtime behavior and its acceptance requirements do not change.

## Scope

Reduce repeated tests, process startup, and redundant native matrix combinations.
Do not skip tests, rename collection labels to hide cost, or relax protected behavior.
Each removed check must have a retained observable contract check.

## Baseline

- Subagents: 669 collected cases across 41 Python modules; about 260 seconds for non-live checks.
- Native subagent cases: 82. Several repeat unrelated answer shapes across every control scenario.
- Pi-kit: 123 collected cases across five modules.
- Pure input validation starts Node separately for 59 cases.
- A migration format test runs a 3 × 3 × 3 Cartesian product for independent formatting axes.
- Memory budget variants each create the same 600-entry fixture; they now share one unchanged read-only dataset.

## Required coverage

- Explicit identity, labels, tool ceilings, and read-only discovery.
- Exact incarnation control and original host ownership.
- Positive ACK authority, settlement ordering, FIFO, and input/result correlation.
- Cancelled waits, unconfirmed closure, and terminal outcomes for accepted inputs.
- Linked history, symlink escapes, private state, and copy-only migration recovery.
- Native stream retry disabled, recovered, and exhausted outcomes.
- UTF-8 boundaries, complete final bytes, native Markdown, expansion and TUI width.
- Child environment filtering and explicit extension contributions.

## Changes

1. Group pure input equivalence classes into five observable validation checks.
2. Remove repeated legacy schema, helper, and renderer implementation checks when integration coverage already owns them.
3. Decouple answer shape from native control scenarios; retain formatting diversity in dedicated rendering cases.
4. Replace independent format cross-products with a covering set; preserve security and rollback interaction cases.
5. Consolidate pi-kit response and lifecycle cases without hiding assertions or changing production code.

## Retained coverage map

| Removed or reduced group | Retained owner |
| --- | --- |
| 59 pure validation processes and a type-only test | Five table-driven boundary tests plus root TypeScript checks |
| Answer shapes repeated across control faults | Dedicated native short, multiline and steered-long TUI cases; control cases use one short answer |
| 27 migration format combinations | Nine pairwise combinations; malformed input, byte preservation and rollback tests remain |
| Legacy tool schema introspection and duplicate handle guards | Closed-schema compatibility check, pure boundary tests, and exported-handler integration |
| Legacy lifecycle duplicates | Resident execution, explicit shutdown, exact replacement and native session tests |
| Duplicate answer preview and metadata render checks | Session Result renderer tests, bounded-output integration and native TUI |
| Pi-kit empty/malformed response wrappers | Five grouped transport checks preserve each response/failure class |
| Pi-kit repeated runtime helper/source assertions | Native worker, shared expansion and package boundary checks |
| Cross-package dependency, publication and UI-contribution scans | Twelve checks move to tests/test_runtime_workspace_contracts.py and still run in pnpm test |
| Repeated synthetic environment resolution | Grouped allowlist, secret diagnostics, exact opt-in and override checks keep all assertions |
| Four 600-entry Memory budget fixtures | One read-only dataset checks all four budget boundaries |

The exact duplicate removals and retained owners are:

- Tool verb and deprecated-field introspection: test_agent_tool_schema.py and test_agent_input.py.
- Missing or malformed control addresses: test_agent_usage.py, test_agent_input.py, and test_stopped_inspect.py.
- Busy stop, planned closure, unknown process and unconfirmed termination: test_resident_execution.py and test_session_role_lifetime.py.
- Role kickoff and existing role precedence: test_resident_execution.py, retained test_agent_tool.py cases, and test_intent_tools.py.
- Empty intermediate versus authoritative output: test_unanswered_results.py and retained deduplication tests.
- Result body previews and complete final delivery: test_agent_output.py, test_stopped_inspect.py, and native result cases.
- Short/multiline/long rendering and provenance: retained test_session_result.py and test_live_agent_usage.py formatting cases.
- Pi-kit worker grants: test_run_pi_worker_minimal_mode_disables_discovery_and_keeps_tool_allowlist covers seven actual launch classes and helper defaults.
- Worker message-boundary reset: test_pi_worker_progress_reports_latest_activity_across_stream_kinds includes adjacent text messages with no intervening reset event.
- Plain factory metadata/blank details: test_meaningful_expansion.py covers all six renderer factories.

The grouping exposes one cancellation race in the old decision fixture.
A warm process can complete its response before a one-millisecond cancellation timer fires.
The cancelled case holds the loopback response and waits for request arrival before aborting.
It now deterministically tests cancellation during transport and asserts exactly one endpoint hit.

Every grouped transport case still issues and verifies its intended request.
No security matrix is reduced merely because it has many cases.
No test skips or marks are added to exclude verification.

## Verification

Record the retained-test map before removing cases.
Run both complete package suites and compare native and non-live process costs.
Run root and kit typechecks, package packing, installed-path checks, and diff hygiene.
The prior runtime verification report remains historical evidence; it does not describe the simplified suite's current counts.

Current collection: subagents 503, pi-kit 95, and 12 moved workspace checks.
Subagents has 458 non-live and 45 native cases.
Pure input checks use five Node processes instead of 59.
Native lifecycle checks no longer repeat three answer shapes outside formatting tests.
An initial full reduced run passes 512 subagent cases in 316.73 seconds.
Kit plus moved root checks passes 107 cases in 15.31 seconds.
The final disjoint groups pass 458 non-live and 45 native subagent cases.
Kit and moved workspace checks pass 107 cases: 95 package cases and 12 root cases.
Root/kit typechecks, 18 packed manifests, installation, and diff checks pass.
All 12 protected production source hashes remain unchanged.

Test prose/code lines drop from 10067 to 9010 for subagents and 3459 to 2958 for kit.
The 12 relocated checks occupy 315 lines at the workspace seam.
The change reduces process invocations, not only pytest labels.

Observed durations vary: the final non-live group takes 296 seconds and the native group takes 80 seconds.
The earlier full reduced run takes 317 seconds; kit/root remains about 16 seconds.
No proportional speedup is claimed; retained safety and transport deadlines still dominate parts of the suite.
Independent review identifies three P2 coverage losses, with no P1 finding.
All three losses are reproduced with disposable-source mutations before changing the retained tests.

- The worker launch test now checks omitted, explicit, empty-list, and empty-string grants in minimal and full modes.
- The activity fixture now includes two adjacent assistant text messages before any tool or thinking event.
- The moved dependency guard now scans all subagent source modules, not pi-kit source modules.

Before repair, all three mutations survive. After repair, all three mutations fail the retained assertions.
Production source and user data remain unchanged. These repairs add no collected test cases.
Post-remediation complete runs pass 458 non-live and 45 native subagent cases, plus 95 kit and 12 workspace cases.
The latest durations are 234.10 seconds, 63.74 seconds, and 15.43 seconds respectively.
Root/kit typechecks, all 18 packed manifests, installation, and diff checks also pass.
The 12 protected production hashes remain unchanged.
Independent reviewer turn 2 confirms all three P2 findings are closed, with no remaining confirmed P1/P2 coverage gaps.
The reviewer uses current-source inspection; the parent supplies complete-suite and mutation verification.
After closure delivery, the three repaired checks pass again. Reviewed test hashes stay unchanged.
No claim of exhaustive coverage, proportional speedup, publication, or a whole-workspace clean run is made.

The reviewed test snapshot is:

- packages/kit/tests/test_pi_kit.py: 2e689d083a50ac617c51ae885a94936e5b0e005c5dd96da1279ba66ea2616368
- tests/test_runtime_workspace_contracts.py: 0e5d3af7af6dbff4d3eb1c2826b9d3b4e22e36124740d4006e4b9f708051063c
