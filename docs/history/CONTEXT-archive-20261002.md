# Agent Teams

## Prompted-start completion verified live (2026-10-02)

- User asked to test the completion after a `[agent] prompted ·` row. One real
  temporary child (session scope, no tools, prompt `Answer with exactly one line:
  PROMPTED-COMPLETE 42`) started in this reloaded session against the workspace
  `packages/subagents` source loaded from `~/.pi/agent/settings.json`.
- Observed: `AGENT · subagent-9cce408d · started · session:…` with `WORKING`,
  then exactly one automatic Session Result with body `PROMPTED-COMPLETE 42` in
  an `<agent-result from=… session=… turn="1">` envelope. No polling, no session
  file reads, no second delivery. The child was stopped afterwards.
- Scope: one prompted start to completion in this session. It is not a rerun of
  the offline suites, a native PTY check, or a hosted (agent-teams) delivery
  check. Independent review closure listed below is unchanged.

Agent Teams models durable AI Agents that can work across projects, develop their own capabilities, and execute project work through isolated replaceable sessions.

## Tool-boundary independent review remediation — in progress (2026-10-02)

- Valid turn1 review received from exact
  session:review-agent-boundary:703e6288-34ea-40f6-96a0-68b1124a0306: three scoped
  blockers (P1 late hosted ACK can rebind successor; P2 pending hosted startup has
  no close binding; P2 cancelled returned failures dropped). Its dynamic probes
  used invented in-memory host/process conditions, not native acceptance. Prior
  output required-prompt and forged preview metadata fixes confirmed in its scope.
- Parent scenarios first, injected regressions **16 RED / 5 pass**; bind original
  host at reservation, require ACK to match it/owner/current nonstopping incarnation,
  consume returned failure after cancelled wait on pinned current record only.
  Added missing-reservation same-host claim **1 RED / 1 pass**, now requires host
  synchronous new reservation (documented host contract). No control fallback.
- Focused code/cancel/resident/row/tool **104 passed**, parser/native66 passed,
  actual shipping team host32 passed; root + strict native/scoped tsc passed.
  New native authority18 cases included in66: real Pi/RPC processes with explicitly
  invented delayed/forged host confirmation and late host error after positive
  native ACK, not claimed provider fault reproduction. No automatic retry/kill;
  diagnostic recorder changes error only. Native definitive false send may restore
  IDLE through its existing ack logic, not by cancelling or recording diagnostics.
- Final parent current-candidate verification: subagents+kit+root-output **786
  passed** (native authority18 included), standalone install4 + cohort/prompt5
  passed. Shipping teams **280 passed / 1 failed**: remaining bundle surface test
  expects old task name while concurrent tasks now registers TaskCreate/Get/List/
  Update. Root combined install audit **8 passed / 6 failed** before cutoff for
  same task-name mismatch. No task edits, permission changes or expectations
  relaxed; no blanket whole-workspace success claimed. Root/scoped/native strict
  tsc, subagents pack dry-run, all18 packed manifests and diff hygiene pass.
  Candidate hashes unchanged across final verification.
- Fixed task-created duplicate output-test basename collision: combined pytest
  initially collected zero tests due root/package test_agent_output.py import
  mismatch. Renamed only the new root test to tests/test_agent_management_output.py,
  contents preserved, package+root38 pass then full786 pass. Root feature remains
  features/agent-output.feature; historical test paths below describe old runs.
- Reviewer valid turn2 received: original3 blockers no longer reproduced in23
  independent invented in-memory cases; one new P1 eager binding overwrite in
  synchronous reentrant host remained. Parent added same/different-host x cancelled/
  uncancelled scenarios, **4 RED**, then checks ANY existing owner before eager
  set/pin (same host object is another invocation too), late owner must still equal
  original host. Focused71 passed; latest authority/cancel/native/parser117 passed,
  shipping host32 passed. New native reentrant6 print/TUI included: synthetic
  A in-memory reserve/retire + real native RPC successor B, original cancellation
  has no successor handle, B confirms and owns exact close. No provider-fault or
  shipping-host reentrancy claim. Current strict scoped/native tsc pass; root tsc
  temporarily blocked by concurrent goal scheduler wait/decision/type edits. Parent
  did not modify goal package. Full rerun and exact reviewer turn3 closure pending.
  No polling/replacement for review; prior pass totals not security acceptance.

## Agent interrupt receipt expansion — user requested (2026-10-02)

- User expects `[agent] interrupted · @review-agent-boundary` to expand/collapse
  like other agent rows. Root cause: row summary copied the fixed120-char receipt
  headline; expanded details appended only prompt lines after the first, dropping
  a long single-line steer's tail. Short controls had no provenance details/hint.
- Feature precedes three RED rendering cases. Input rows now use complete bounded
  details.prompt as sole summary (pi-kit fits/wraps), never duplicate prompt tail.
  Send/interrupt expanded details expose session/state/pending/next; collapsed
  handles remain hidden. No shared-kit/control transport or original data changes.
- Row/result suites34 passed; real Pi1.0 PTY steering3 passed for short/multiline/
  long answer variants, Ctrl+O expand + collapse, first-line tail exactly once,
  width fitting and unchanged structured steering input. Fixture needed a corrected
  starting/working assertion (ACK can precede progress) and same-sequence second
  assistant request after steer; timeout trials not acceptance, original scope
  preserved. Final subagents+kit **714 passed**, standalone install4 and cohort/
  prompt5 passed: **723 disjoint checks**. Root/scoped/native fixture tsc,
  subagents dry-run and pack18 pass; relevant candidate unchanged during checks.
  No whole-team/full-workspace pass claimed given concurrent task migration.
  Current session needs reload for the already-loaded renderer; original reviewer
  handle was not re-steered merely to test display. Broader independent review
  remains pending and is not implied by this localized display closure.

## Tool-definition optimization — authorized, in progress (2026-10-02)

- User requested all audit recommendations. Preserve flat six-action input,
  disk identity, IDLE/send, asynchronous final bytes, exact handles and widget
  policy. No dependency/data migration/global settings/publication changes.
  Memory overwrite and read-only proposal authority remain existing contracts;
  optimize honest names/docs without silently changing them.
- Disjoint local delegates: optimize-agent-input owns NEW agent-input.ts + its
  tests/feature; optimize-agent-output owns NEW agent-output.ts + tests/feature;
  optimize-child-tools owns agent-extension/tool-activation + their tests/features.
  Parent owns agent-tool integration, cancellation/native tests and docs.
- optimize-agent-input turn1 completion report received from exact
  session:optimize-agent-input:6eaa05a2-9ff9-4385-9d02-a45ab0f31ee9. It changed
  only its three assigned module/tests/feature files. Reported RED54/1 typepass,
  follow-up guidance/safe-offset RED4 and RED5, final GREEN59, strict module tsc
  (exactOptionalPropertyTypes/noUncheckedIndexedAccess), cached root compiler,
  pack dry-run and whitespace checks passed. Wrapper Corepack bootstrap was
  network-disabled; equivalent cached compiler passed. This is its implementation
  report, not independent review; parent integration/native evidence is separate.
- Cancellation feature defines caller wait vs resident lifetime: before dispatch
  no effects; after dispatch return cancelled/uncertain with pinned exact handle
  and observed state, original acknowledgement/closure still settles in background,
  no automatic kill/retry/idle guess. 11 substantive RED cases observed; parent
  integration and prior resident/tool suites **67 passed**, root tsc passed.
  Hosted synchronous reservations pinned; native print/PTY cancellation probes
  pass. Roster-observer synchronous abort RED fixed with microtask cancellation
  receipt so it names the committed exact reservation. Accepted/coalesced results
  expose current state and no invented pending result. Cancellation suite14 pass.
- Four handler integration RED checks observed: null/type/misplaced fields, prompt
  trim loss, absent structured output, absent list pagination/budget. Integrated
  input/output modules; all three tool outputSchemas/structuredContent native1.0,
  no parameter as-never casts, honest annotations and shortened main description.
  Session role whitespace retained in registry (RED) without changing disk
  definition normalization. list summary/pagination16KiB/200lines, JSON32KiB,
  inspect8KiB body, diagnostics1000 chars; final notices unchanged. Public types
  exported through existing agent-tool barrel. Same-name Memory upsert/proposals
  preserved and explicitly described. No typebox dependency added.
- Delegates input/child tools implemented local edits; parent verification130
  input/Memory/activation checks passed. optimize-child-tools turn1 returned an
  explicit unanswered error from exact
  session:optimize-child-tools:35c3847e-48d8-45fe-b543-0f80ea94c860:
  provider408 stream disconnected before response.completed, no original final
  text. No completed implementation/verification report was received from that
  child; evidence for its actual edits is parent source review and executed tests,
  not this notice. No automatic retry, replacement or rollback; this is distinct
  from the independent review-agent-boundary review, whose closure remains open.
  optimize-agent-output turn1 returned unanswered provider stream-disconnect error
  from exact session:optimize-agent-output:7282a496-55a4-4de0-84f5-e2ef3215f856,
  with no original final text. This is not an implementation completion report,
  nor a result for its later continuation turns. It created the module but no
  feature/unit tests; parent took ownership, added feature/tests. No notice-driven
  retry, replacement or rollback; parent verification remains the evidence.
- optimize-agent-output turn2 valid completion report now received from the same
  exact session, distinct from its failed turn1 and later handoff turns. It reports
  typed/bounded output APIs and31 output tests; its root goal/activation type errors
  are historical candidates, not current blockers. Parent read the actual delivered
  files and reran root tests/test_agent_output.py **31 passed**, package output suite
  **7 passed**, and pnpm typecheck **passed**. The child feature/tests landed at root
  features/agent-output.feature and tests/test_agent_output.py; package equivalents
  added during parent takeover also exist. Both sets preserved, no silent removal.
  This implementer report is not the independent review-agent-boundary verdict.
- optimize-agent-output turn3 explicitly hands off ownership and retracts its
  focused GREEN claim for artifacts it says were absent. Parent rechecked current
  workspace: both root test/feature files exist, in addition to package versions;
  its absence claim does not describe the current parent candidate. Use parent-run
  31/7 passing checks and observed files, not the conflicting child self-report,
  as current verification evidence. No further edits delegated to this resident.
  Parent integration
  RED + GREEN, native codemode RED then GREEN with observed stopped state; full
  subagents at initial integrated candidate573 pass. Latest scoped/native54 pass;
  output-schema required prompt deletion regression RED then fixed;28 focused pass.
- Broader consumer rerun exposes strict-input fixture mistakes fixed narrowly:
  undefined tool grant now omitted; inspect no longer passes name; agent error
  wording asserted semantically. Remaining task tests fail on concurrently changed
  task actions/update/reopen/row contract, not subagent effects; no parent task
  edits or rollback. Initial teams227pass/6fail (cutoff); kit/install178pass/4fail
  prevent claiming a clean combined run. Tasks interface currently uses take/reopen.
  Root/scoped tsc, subagents dry-run and pack18 pass. Personal check:install still
  pre-existing15 missing registrations, global settings untouched.
- Latest full subagents+kit **706 passed**, native print/PTY/codemode30 cases
  included; exact handles on errors/observed state and failure codes further tested.
  Dedicated output required-prompt deletion RED/GREEN; all schema/cancel/native
  targeted58 pass, scoped strict+unused tsc pass. Initial root tsc/pack18 passed;
  current root typecheck is blocked by concurrent task API rewrite (registerTaskTool,
  TASK_TOOL_PARAMS removed, extension/imports not yet reconciled; parent did not edit
  those files). Whole-team run257pass/12fail cut off; parent-caused strict-fixture
  and new diagnostic handle assertions corrected, targeted18/19pass with last
  failure from missing task export. Task-only stale action/row tests remain outside
  requested subagent scope. No whole-repo clean claim. Standalone install4 pass;
  cohort/prompt-budget5 pass separately (prior -k filtered them). Candidate hashes
  stable during706 run; source output/input/child files parent-owned now.
- Final pre-row-follow-up optimization verification subagents+kit **708 passed**,
  standalone configured install4/cohort+prompt5 passed, root/scoped strict tsc and
  pack18 passed. Later changes include control-row projection only (see above).
  Fresh scoped read-only review pending exact
  session:review-agent-boundary:703e6288-34ea-40f6-96a0-68b1124a0306. No polling or
  repeated review starts; static/dynamic acceptance stays separate. Its valid
  turn1 three-blocker result now received; remediation and exact turn2 closure
  follow-up are tracked above, not inferred as a blanket security acceptance.

## Tool-definition best-practice audit — assessment only (2026-10-02)

- User requested reflection on current subagent tool definitions, not changes.
  Checked Pi1.0 extension docs/types and current agent/activation/Memory source.
  Preserve six-verb flat input contract; model availability is not authorization.
  Native structuredContent/outputSchema and typed results remain design gaps;
  signal is ignored at tool boundary, so cancellation semantics need definition
  before implementation (accepted residents must not die with parent-turn abort).
- Cheap isolated invented probes (injected spawn, no real child/network/data):
  list with start-only prompt/tools is accepted and ignores those fields; direct
  executeAgentAction(action:true,name:...) starts a fake child even though schema
  rejects it. Pi schema protects model entry, not exported handler callers.
  Twenty retained stopped entries with 16k text yield 321,955 text bytes / 323,175
  detail bytes: per-entry preview caps are not an aggregate list budget.
- Suggested priorities, not implemented: handler action/field/type validation,
  total readback/failure budgets, cancellation ownership, typed structured output,
  then shorten tool description/fix send snippet. Memory append currently rewrites
  a same-name file; proposal writes remain allowed under read-only execution grant
  as an explicit contract exception. Naming/authority clarity requires user policy,
  not a silently changed Memory contract. No security acceptance from this audit.

## Stopped exact-session inspection fix (2026-10-02)

- User explicitly required fixing the erroneous inspect failure for arithmetic
  handle retained as stopped. Root cause: read-only inspect reused the living-only
  process-control resolver, despite list exposing that same stopped record.
- Contract/scenarios updated before six observed RED regressions: known stopped
  inspect succeeds with exact recorded status/bounded answer/error and no effects;
  controls remain living-only; unknown/replaced handle never reads a successor.
  New matching lookup is local to inspect; no resolver/roster/history changes.
- Focused tool/resident/result/regression suites **82 passed**. Real Pi1.0.0
  print/PTY **12 passed**, including start -> automatic answer -> stop -> inspect
  for short/multiline/long output; successful inspected row, Ctrl+O, unchanged
  result, one model request, no revival/data writes. Strict fixture tsc passed.
- Final grouped verification: subagents/kit **577 passed**, team consumers
  **281 passed**, isolated installation/cohort/registration **56 passed**;
  **914 disjoint checks**. Root/strict fixture typechecks, package dry-run and
  all 18 packed manifests pass. Candidate hashes unchanged during those checks.
  The initial install command named a removed tests/test_tools_default_minimal.py
  and ran zero tests; corrected paths were rerun successfully, not restored.
- Personal read-only check:install still finds the pre-existing 15 missing
  workspace registrations; isolated configured installation passes. No global
  settings changed. Independent static review turn1 from exact
  session:review-stopped-inspect:7e41d117-39ff-4fb3-971a-ee03a5d9d197
  returned one blocker: project/readback copied raw unbounded agent.error. No
  other scoped lookup/control blocker found; no dynamic/security acceptance.
- Review follow-up: feature/scenarios and two long stopped-error tests first
  observed RED (24,040 raw vs expected 1,024 preview). project now reuses existing
  boundedFinalDiagnostic for error on inspect/list; raw state/final output intact.
  Startup-failure + runtime callback, short/1000/1001/sanitized boundaries pass.
  Native lifecycle print/PTY adds invented retained long error solely to probe
  readback bounds, not to claim reproduction of an actual provider failure.
  Focused prior suites **80 passed**, stopped+native **29 passed**, strict
  fixture/root tsc pass. First full follow-up: subagents/kit **587 pass/2 fail**
  solely in new PTY shutdown test, teams **281 passed**, install checks **56
  passed**, pack18 passed. Failure evidence confirmed native shutdown and no
  living children: harness missed process exit between two polls (and lacked the
  established EIO reaping branch). Fixed test-only EOF/exit predicate handling;
  **29 passed** and extra native TUI **6 passed**. No production shutdown edits.
  Candidate unchanged during initial verification. Corrected full rerun
  subagents/kit **589 passed**. The simultaneous consumer run encountered tasks
  API source churn: bindTask/failTasksHeldBy unavailable, unrelated overlapping
  take regression and missing TASK_HOLDER_ENV. No parent task edits or reverts;
  later interface probe and targeted consumer checks passed, then complete
  consumers **281 passed**, isolated install/cohort **56 passed**. These final
  disjoint groups total **926 passed**, native print/PTY **18** included. Root and
  strict fixture tsc, subagents dry-run, pack18 and diff hygiene all pass. Scoped
  code unchanged since the 589-pass candidate; consumer candidate hashes stable.
  Independent exact reviewer turn2 returned: its P2 unbounded-error blocker is
  fixed with no scoped blocking finding or control regression. Static closure
  only; the reviewer inspected tests/fixtures but ran no dynamic verification.
  Parent owns the 926 passing checks. No polling/duplicate starts, broader
  storage/security acceptance or full pnpm check claim.
- Current loaded extension still requires reload; do not claim the user's
  original old handle was retested live. No history archive or recovery of
  replaced/lost-parent records is introduced. Widget policy remains unchanged.

## Above-editor activity row diagnosis (2026-10-02)

- User asked why no agent activity row is currently visible. Working explanation:
  widget is activity-only (starting/working), not a roster of IDLE residents.
  Diagnostic exact inspect/list confirmed arithmetic incarnation stopped and
  current remaining child IDLE; no active child to render. Personal subagents
  package source is configured. No child/session files read and no waiting polls.
- Activity-widget + native print/PTY regression checks **13 passed**. Result-row
  deduplication did not modify widget/runtime paths. Work-time absence in the
  user's specific TUI is not reproduced; do not claim a fix or change IDLE display
  policy without clarifying whether idle presence was expected.

## Subagent result-row redundancy follow-up (2026-10-02)

- User's one-child arithmetic invocation was correct: prompt-only, no tools,
  one start, yield, automatic result. No polling or lifecycle change needed.
- Reproduced display bug: summary 2 plus details Session Result/turn and 2;
  details caused unnecessary expansion and fixed 200-char headline clipped wide
  displays. New feature precedes three observed RED renderer tests (short hint,
  multiline first-line duplicate, wide result truncated).
- sessionNoticeSpec now uses the complete answer as its sole summary and empty
  display details; pi-kit fits collapsed and wraps expanded content. Turn/session
  and exact final bytes remain in original content/details. Authored repetition
  and paragraph breaks survive; no shared-kit/runtime behavior edits.
- Current verification: result-row suite **22 passed**, real Pi1.0.0 print/PTTY
  cases **6 passed** (short/multiline/long with Ctrl+O and resize), strict fixture
  tsc/root typecheck passed; unanswered + native + team rows **35 passed**.
  Final subagents + shared kit suites **566 passed**; package dry-run and all
  18 packed manifests pass. Relevant change is display-only and localized, with
  no new cross-module behavior. Separate storage blockers/migration hold remain
  unchanged; no dependency/global-config/data writes. Reload required for this
  session's already-loaded renderer to reflect the code change.

## Pi 1.0.0 validation cohort — authorized (2026-10-02)

- User explicitly superseded the earlier 0.99.2 requirement: this session must
  also use Pi **1.0.0**. Confirmed/reconciled root pi-ai/coding-agent/tui and split
  kit/subagents/tasks/teams coding-agent/tui via offline pnpm add -D (scripts off).
  Manifests ^1.0.0, installed/locked 1.0.0, published wildcard peers unchanged.
- Updated current cohort assertions, native/E2E guards, features and bilingual
  docs. Old verification reports/0.99.2 counts below remain historical evidence,
  not relabeled as 1.0.0 acceptance. Former version mismatch blocker is resolved
  by user authorization, not by dropping tests. RED 2 cohort failures/3 native
  setup errors observed, focused GREEN **6 passed**, root typecheck pass.
- Initial combined verification timed out at 650s during tasks concurrent edits;
  not counted as a pass. Parent made no task business edits. Final grouped
  1.0.0 verification: subagents **436 passed**, teams/tasks/kit/root **553 passed**
  (989 disjoint tests). Only tasks/tool.ts + lockfile changed during those runs;
  final affected/cohort/native/combination recheck **82 passed** after those edits.
  Root tsc, strict native fixtures, four pack dry-runs and all 18 packed manifests
  pass. pnpm frozen offline dry-run makes no dependency changes.
- This closes the user-authorized version upgrade and previous cohort mismatch,
  not separate cross-parent safety policy or migration acceptance. Global
  check:install remains a personal declaration audit with known missing packages;
  no real storage migration, publication, commits or global configuration writes.
  Cross-parent history policy and broader safety blockers below are separate.

## Empty fork-review result investigation (2026-10-02)

- User explicitly requested reproduction and fixes for empty fork review. One
  short authorized review child returned nonempty static text; parent inspected
  its settled exact handle for diagnosis and stopped it, without waiting polls.
  Its automatic nonempty Session Result now arrived from
  `session:fork-review-repro:42073a9e-9bd9-420a-a4b2-362873ac9248`, matching the
  diagnostic readback: no blocking finding in fork-extension.ts + temporary
  spawner setup/ack static paths. The review explicitly excludes codec/ack parser,
  native runtime and dynamic checks. This disproves universal fork-delivery loss
  but does not reproduce the earlier blank child or prove a provider root cause;
  it is not full fork safety acceptance or the unanswered-contract review.
- Confirmed code gap: standalone native parser dropped stopReason/errorMessage
  and emitted authoritative blank, error or length-limited final messages as
  ordinary result envelopes. New Given/When/Then unanswered-results contract,
  11 observed RED cases; explicit unanswered kind/envelope with exact turn,
  observed reason, preserved output and bounded diagnostics. No semantic PASS,
  automatic retry or replacement. IDLE/send retained; intermediate blanks/ready
  frames remain nonterminal.
- Updated parser preserves final evidence across coalesced settle/reset; roster
  readbacks distinguish UNANSWERED from RESULT, TUI error-band renderer resumes
  parent once. New native print/PTTY loopback **8 passed** (blank/whitespace/
  length with and without partial text, same resident explicit second send).
  Final subagents suite **427 passed** after additional native HTTP400 and
  notice/retry-reader coverage; team/kit/install/combinations/core/prompt groups
  **463 passed** (890 total, separate disjoint invocations). Root tsc now
  passes after unrelated concurrent goal edit resolved; standalone package/fixture
  strict tsc passed independently, and all 18 packed manifests pass. No edits
  made to the unrelated goal package.
- Extended native error cases use local HTTP400 with retries disabled: total
  native print/PTTY **10 passed**. Final targeted result/render/notice/retry group
  **44 passed**. Record reader accepts old result notices, rejects malformed new
  reasons; unanswered delivery retries once without duplication, no model retry.
  Global check:install still reports 15 unregistered workspace package sources;
  did not modify personal settings. Root and dedicated tsc passed.
- review-unanswered-contract returned a valid static NEEDS FIX report: later
  messages reused previous answerComplete/stopReason without message_end, and
  unknown long stopReason bypassed diagnostic bounds. Both reproduced RED via
  real parser (3 failing probes). Parent added per-message evidence reset at
  native message_start with first-content fallback, preserving multiple blocks
  and only authoritative final text; stop reason normalized to protocol enum
  or fixed unknown at parse/tool/reader/render/envelope boundaries.
- Current parser/entry/native unanswered groups **47 passed**, including 6 new
  full extension+spawner-parser probes (only OS creation mocked), 10 real native
  print/TUI empty/length/error cases, no legacy final evidence reuse. Root and
  strict fixture tsc/diff checks pass. Same exact reviewer turn2 returned a valid
  scoped static verdict: both findings fixed, no remaining blocking in that scope;
  no independent dynamic rerun or full-system PASS claimed. Full subagents rerun
  after correction **436 passed in 308.79s**, targeted parser/result/fork/native
  group **76 passed**. Older 427/463 totals precede this correction.
- Concurrent dependency mutation then changed root and four split packages to
  **1.0.0** (^1.0.0 manifests), while user-selected/test contract is still 0.99.2.
  Did not revert another session or relax its cohort assertions. Wider caller
  rerun: **435 passed, 25 failed, 3 setup errors**, all failures/errors shown from
  cohort mismatch, not evidence of parser regressions. Current 1.0.0 targeted
  unanswered/parser/native group **47 passed**, root + strict fixture tsc pass.
  This historical version conflict was superseded by the explicit 1.0.0 upgrade
  authorization and new verification at the top of this file. Scoped empty-result fix and independent
  static closure remain valid but are not relabeled a clean whole-repo check.
  Existing storage-policy blockers and migration hold
  below remain unchanged; this task does not authorize their scope expansion.

## Independent-review remediation — not accepted yet (2026-10-02)

- review-disk-migration returned a substantive current-candidate static report,
  not a PASS: unsafe linked history, cross-parent history sharing, temporary fork
  disk writes, rollback ENOENT interruption and canonicalizer grant loss. Older
  853-pass evidence is superseded for these missing cases. Real migration paused.
- Cross-parent policy is BLOCKED pending user confirmation: parent proposed one
  live owner per identity/project mutable history, second start refuses, no lock
  stealing/dead-owner guesses. Do not implement a concurrency-policy guess.
- Separate fix owners: migration `session:fix-migration-findings:50b37313-be6e-4375-a1ab-6250b3cd35ea`;
  temporary fork `session:fix-temporary-fork:4a56f247-c988-4ce6-a46f-e574b69d1ad6`
  returned empty, not an implementation/verification report. Parent inspected
  its helpers, extension and tests; spawner integration was still missing.
  The first start was real despite orchestrator error; one diagnostic agent list
  recovered its exact handle after duplicate name refusal. No replacement spawned.
- Parent linked-history RED: symlink/dangling/directory/hardlink all provisioned,
  raw resume spawned. Added shared assertPrivateSessionFiles at provisioning and
  shared spawner boundary, both standalone/host resume selection use it. Current
  history candidates must be regular single-link JSONL; validation opens nofollow
  and checks inode. Workspace+transport **38 passed**; native outside-history
  probes **2 passed**, no child spawn and target bytes/mtime/context unchanged.
  Combined storage/transport/native plus team-disk checks **48 passed**, root
  TypeScript and package dry-run passed. This is targeted P1 evidence, not a
  final security verdict or substitute for unresolved history ownership/fork.
- Parent temporary-fork RED reproduced two production-spawner no-session failures.
  Integrated child-only fork extension, versioned sanitized snapshot on control
  pipe, dedicated correlated setup ack, then kickoff/idle handshake. Generic
  handled does not count. Added real production spawner prompted/idle two-input
  probes, plus rejected/closed/timed-out setup with no kickoff/history file.
  Fork+history helper group **14 passed**, full subagents+related native/E2E
  **424 passed**, root tsc and 18 packed manifests pass. Temporary-fork identity
  never writes history, durable-fork still uses authorized private files.
- fix-migration-findings actual handoff received: only migration.ts/feature/tests
  edited, rollback continues after ENOENT and retains original cause/residual paths,
  whitespace tool keys preserved, duplicate/invalid-UTF8/semantic changes blocked.
  Parent read current source and reran migration/workspace/Memory **165 passed**;
  root tsc and whitespace pass. Migration source SHA256
  7448bab8b95b9c26ffe66c4d2b7003eb306fe4f765ae43051fde07033e51a384.
  Targeted independent 4/5 recheck started: exact
  `session:review-migration-fault-fixes:fa7124c7-10f5-43dc-975f-5fc11def447e`.
  Source/ancestor and lstat/unlink races remain explicitly unproven, not sandboxed.
- review-migration-fault-fixes actual verdict: item5 fixed, item4 fd chains still
  blocking (close error overwrites write/fsync error; fstat-after-create leaves
  unrecorded destination). Parent reproduced 9 RED descriptor faults, captured
  first failure and distinct close diagnostics, never retried uncertain close,
  retained/disclosed unverified ownership paths while rolling back known files.
  Expanded probes include first canonical definition and last session targets.
  Migration/fd/workspace **135 passed**, root tsc passed. Dedicated correction
  review `session:review-migration-fd-chain:7587795f-dd99-4efe-a4e0-6c3c0a4904ac`
  returned a substantive static verdict: both fd findings fixed, no new blocking
  finding in that scope; dynamic independent rerun not performed. Item5 had already
  been confirmed fixed by the preceding review. Parent matched current code to the
  reviewed chains; migration SHA256 now
  5637d2ca103e4d90370c0a062458b14eab76db4c9bbf98bdd7eb063092c35a00.
  Scoped items 4/5 have independent static closure plus parent dynamic evidence,
  not a full storage safety verdict or real-migration authorization. OS close
  uncertainty and source/ancestor/lstat-unlink races remain disclosed limits.
- Cross-parent ownership policy remains BLOCKED awaiting user confirmation, not
  silently enforced. Targeted fork reviewer
  `session:review-memory-fork-fix:5ade90c7-40c6-46d4-a9f4-c270b2cb8983` returned
  an empty Session Result, not a valid independent verdict. Parent fork tests are
  still self-verification; independent fork review remains missing. No duplicate
  starts, polling or session-file reads to wait or infer acceptance.
- resident-final-review returned an empty Session Result: no valid independent
  verdict on hosted controls, verification gates or latest shutdown cleanup. Its
  earlier progress text is not review evidence. Record this review gap; do not
  infer PASS or duplicate/poll to wait. The fork review attempt covers a different
  scope and returned no verdict; it cannot substitute for hosted-control review.
- Pending actual reports, approved history ownership policy, final safety review. No real user
  history/definitions altered; prior dry-run is not authorization to bypass flaws.

## Requested design replacement — adopted (2026-10-02)

- User requested disk-defined identity: no model-facing persistent/memory/worktree
  flags, durable `<name>/agent.md` homes with memory, ordinary workspace and
  project-scoped history; pure in-memory inline roles; six verbs unchanged;
  no promotion or git workspace machinery; durable-but-offline entries on list.
- User explicitly adopted IDLE/send for temporary children after every result.
  Settlement never closes either kind; stop/parent shutdown does. New authority
  is @packages/subagents/VISION.md and @packages/subagents/AUTHORITY.md, rewritten
  before implementation. Historical opt-in/worktree policy below is superseded.
- Existing implementers/reviewer were steered to stop old-contract edits and
  return handoffs, preserving all changes. `fix-rpc-fixtures` returned: 22 Pi0.99.2
  tests passed before final type-only edit; native ack/negative/timeout fixtures
  repaired; remaining scripted.ts types and hosted kickoff ack unverified.
- Active disjoint implementation owners: disk-identity-storage (agents/workspace/
  migration), resident-identity-runtime (tool/roster and resident tests),
  identity-memory (Memory/child capability/package README), adapt-identity-consumers
  (team production + tests), disk-identity-e2e (native combination fixtures). Parent
  owns VISION/AUTHORITY, original live fixtures, root docs/context and integration.
  Shared interface: ensureAgentWorkspace({agentName,cwd}) returns project cwd,
  workspacePath, sessionDir, reused; definition/roster have no isolation field.
- Read-only real inventory confirms one user legacy role `calc-check.md`, private
  sessions `subagent-sessions/calc-check`, no workspaces root. Do not mutate real
  data until safe copy-only migration is implemented and tested. Project overrides
  become `.pi/agents/<name>/agent.md` and `<name>.local/agent.md`; data homes may
  exist without a user-scope definition, never imply identity themselves.
- Parent new live temporary/send regression observed RED at old automatic close
  and is now GREEN under real Pi0.99.2/loopback. Native fixtures use canonical
  disk paths and scope/source details.
- Current new native checks **5 passed**, rerun after runtime landing: true temporary same-process two-send,
  canonical disk identity/history/Memory resume, project identity without user
  promotion, correlated real steer, and PTY expanded source. Typecheck now passes.
  Parent shutdown role cleanup **2 passed**; Corepack pack test now uses installed
  local pnpm under isolated HOME and passes without network downloads.
- In-progress broad integration **412 passed / 47 failed** during parallel edits: mostly
  old flag/flat-path assertions and migration module not yet written; owners received
  scoped failure lists. Idle prompt budget currently exceeds 3600 by 29 chars and
  consumer owner must compress, not raise ceiling. Do not treat this as final
  candidate validation or restore obsolete compatibility paths.
- Hosted temporary agents must also support send/interrupt. Runtime/consumer
  owners received that correction; pinned AgentHost optional send/interrupt
  Promise ok/error interface landed, production coordinator wiring still pending.
  Controls must await native acceptance, not merely writable-pipe success.
  Shipping publishAgentHost now wires sendResidentSequence/interruptResidentSequence;
  installed bundle smoke passed native-ready and prompt-ack-before-receipt assertions.
- Obsolete Memory enable marker removed. Child contribution now validates pinned
  definition path/scope; runtime/consumer received new env-binding requirements.
  Latest root tsc passed after production source/scope bindings landed.
- Exact active implementation handles: storage
  `session:disk-identity-storage:465f3708-22f0-46f7-bab4-5ceaa7d0cb54`; runtime
  `session:resident-identity-runtime:b041e355-b8df-4041-a58a-7b29042360be`; Memory
  `session:identity-memory:41a8ee6e-b0ce-4b86-91fc-be51e46e3b7f`; consumers
  `session:adapt-identity-consumers:36f54e59-aaea-4790-aec9-bc2c440ddc48`.
  E2E `session:disk-identity-e2e:142fcc40-2249-4afc-b069-908f5b314733` refused
  one scope interrupt, then returned an empty Session Result: no usable report.
  Parent verified and repaired its E2E changes independently; coverage is included
  in the final 853-test pass. Do not attribute verification claims to this child.
- Old `fix-install-isolation` handoff received: 19 pass/2 fail, unimplemented
  `/accepted` GET pending. Parent implemented actual loopback observer + regression;
  model arrival never substitutes for RPC acknowledgement. Native bundle smoke is
  now GREEN including correlated input-before-receipt and explicit child closure.
  Latest native lifecycle/steer/TUI/transport + install-wiring checks **41 passed,
  1 deselected** (root packed-manifest gate still has unrelated missing goal package).
  Combination E2E/independent-work rerun found new observer bindings and report
  JsonValue mismatches after its owner stopped; parent fixed limited helper seams:
  record only PROJECT/WORKSPACE/DEFINITION/SCOPE (no credentials), validate reports
  through jsonValue. Complete combination+work-sessions group now **35 passed**.
  Prompt budget **3 passed** without any ceiling increase.
- Public steer now has `deliverResidentSteer` Promise native correlated acceptance,
  reusing prompt transport without resetting stream/turn baseline. New parser
  RED->GREEN tests cover wrong command, queued/reject/close/timeout and draft
  preservation; **11 transport probes passed**. Runtime owner notified to await
  this path and update tests; consumer owner may use the new helper.
- Stable affected checks subsequently passed: core/subagents/tasks/kit/root/install
  **508 passed**; team+combination **306 passed**. Full-repository attempt timed
  out at 600s before completion. Two encountered failures reproduced separately:
  plan-mode PTY sends /plan during native startup (2 failed/1 print passed), an
  unrelated test-readiness issue. No claim of full pnpm check success.
- Final affected-package/root verification **853 passed in 430.82s**. Previous
  combined run had 851 pass/2 harness failures: PTY quit predicate race (fixed
  with authoritative process exit recheck) and parent-created pnpm shell shim
  incorrectly reused as Node input (removed for final run). No business assertions
  relaxed. No runtime fingerprint changed during the preceding final candidate run.
- Parent integration found a new state-writer gap: workspace bypassed Memory
  lock and lost extra fields. Added RED regression, moved read/update state helper
  into workspace as one mutation boundary, memory re-exports; both use latest
  state under state.json.lock. Memory/workspace **67 passed**, migration/native
  **45 passed**, root tsc passed after correction. Fresh review was steered to
  inspect this new candidate. Packed manifests 18 passed before final state edit
  and final candidate pack/typecheck are rerun below.
- Storage owner became unavailable for an explicit scope steer and later returned
  an empty Session Result, not a usable implementation/verification report.
  Parent implemented its already-RED migration contract in
  src/migration.ts and exported it: **40 disk/migration tests passed**. Sources/body
  preserved, plans rebuilt/hashes compared, stale/conflicts/symlinks rejected,
  exclusive writes, bounded rollback of only invocation-created inodes. Git
  workspaces stay manual. No automatic migration or deletion.
- Real user dry-run plan is READY: calc-check flat definition + one old private
  session (2 files), no conflicts; no apply yet. Independent read-only security
  review `session:review-disk-migration:d399001c-05fb-4a45-b9c7-6aac94989b79` started.
  Await actual report; never infer acceptance from start/empty result.
- Old review-integration-contracts handoff received: static, no edits or dynamic
  checks; dependency cohort 0.99.2 confirmed at its snapshot. It does not review
  or accept the adopted disk-identity design; obsolete Memory opt-in findings are
  not current blockers. New review-disk-migration remains the pending reviewer.
- adapt-identity-consumers handoff received: its team-owned runtime/control,
  schema/guidance/UI/docs changes reported 281 package tests, 28 combination/budget
  and 43 task tests plus Pi0.99.2/native/types/pack checks. Parent had independently
  rerun these seams (73 consumer/native after closure delta). Its fresh-review
  gap is now assigned to `session:resident-final-review:3ac1857f-4707-459f-8714-7d55e359d609`,
  read-only current candidate hosted/verification/shutdown-control review. Separate
  earlier migration reviewer result is still pending; no verdict inferred.
  Consumer AGENTS.md was updated to actual agent/task/message and disk identity
  authority to avoid its pre-existing instructions naming removed tools/verbs.
- resident-identity-runtime handoff received: owned runtime/roster and tests,
  reported 329 plus later 170 affected passes. Its explicit remaining integration
  gap was real: extension shutdown had not called retireAgentControls. Parent added
  feature + entry-level RED regressions (confirmed/replaced/already-stopped failed,
  uncertain passed), copied immutable exact snapshot facts and retired controls
  only after confirmed/stopped state. Successor and uncertain controls retained.
  After this correction: subagents **312 passed**, affected/native/TUI/control
  group **44 passed**, root + fixture TypeScript passed. Prior 853 pass precedes
  this correction and is not relabeled as the new candidate result.
- identity-memory handoff received: its six owned files, 49 local/native passes
  and 18-pack/typecheck results are reported for its snapshot. Verified current
  source against its remaining limitation: parent already moved state read/update
  helpers into workspace, Memory re-exports them, and provisioning now uses the
  same lock/latest-state boundary. The stale direct-three-field-write limitation
  is resolved and covered by parent RED/GREEN + final 853-test verification.
- Old verify-resident-live handoff received: its 201/4 passes and opt-out assertions
  refer to superseded flag contract. Parent already rewrote owned native files to
  canonical definitions, scope/source and always-IDLE, and reran them successfully.
  Do not reuse old validation as current acceptance.
- Await actual owner reports, stable-candidate suites and fresh review before real
  migration. Parent native tests use scope/source, no flags/sessionNote. Migration
  module is now implemented/tested and dry-run only; no user data was changed.
  Security review actual result is pending; prior 853-test/state-helper candidate
  was supplied. A later attempt to steer the new shutdown-controls delta returned
  no living reviewer handle, so that delta is not independently reviewed yet. Do
  not infer verdict, duplicate a review to wait, or read session files. New
  subagents312/affected44 tests + root/fixture types and 18 packs pass after delta.
  Consumer resident + combination/install wiring rerun after delta **73 passed**.
  Real migration stays dry-run until effective current-candidate review arrives.
- Pi 0.99.2 validation preceding the design change: **668 passed, 1 tooling failure**
  (isolated HOME hid Corepack's pnpm cache and attempted a network download).
  Runtime fingerprints stayed stable except concurrent lockfile edits. Typecheck
  passed. pack:check now blocked by concurrently missing `@fradser/pi-goal`; do
  not restore/remove another session's package work. Earlier 0.87.1 passes are not
  evidence for the latest cohort. Global Pi configuration/auth unchanged.

## Multi-agent integration of reported verification gaps (2026-10-02)

- User authorized multiple agents to modify the reported Q1/Q2/Q3 verification
  gaps. Keep the flat schema, derived persistence without definition writes,
  canonical-tool drift guard and exact-session send/interrupt contracts.
- Disjoint work: `fix-rpc-fixtures` owns independent-work/E2E readiness fixtures
  and combination tests; `verify-resident-live` owns new native resident tests;
  `fix-install-isolation` owns install-wiring isolation tests. They must not edit
  shared manifests/lockfile/runtime; parent owns integration and final checks.
- Baseline reproduced: independent-work fixture has no RPC input ack; subagents
  lifecycle E2E has no readiness response; split core lockfile drift. Prompt
  budget currently passes; no budget change is needed.
- User corrected the development cohort to Pi **0.99.2**. Parent updated root
  pi-ai/coding-agent/tui and split kit/subagents/tasks/teams coding-agent/tui
  through pnpm add -D; manifests use ^0.99.2 and installed/locked versions are
  0.99.2. Published wildcard peers/runtime dependencies stay unchanged. pnpm added
  exact 0.99.2 core release-age exclusions to workspace config; install scripts
  stayed disabled. Full dedupe was only probed in temporary copy and rejected.
  Root and split installed-resolution regression tests pass. Current typecheck
  exposed old `addedToolNames` usage: structurally strip legacy metadata from
  forked history, preserving original content and parent state; regression passes.
- New Q1 regression: a published host previously stole omitted-persistence
  saved-role starts. Parent added `!persistent` to hosted routing; private
  session/Memory stays standalone with one result owner. RED confirmed; 64 affected
  tests + typecheck passed. Prompt budget differs with personal Agent catalog
  (3681 vs isolated 3589); benchmark now isolates HOME/project with regression and
  leaves all ceilings unchanged.
- Parent checks so far: core/subagents/tasks/kit/root contract group **374 passed**;
  teams excluding the fixture owner's in-progress work-sessions file **241 passed**.
  TypeScript, native arithmetic print/PTTY and 18 packed manifests pass. No user
  settings/auth modified; no full dedupe, publication or commits.
- Pending: automatic implementer reports, integration tests, native Q1/Q3 evidence
  and fresh read-only `review-integration-contracts` report (exact
  `session:review-integration-contracts:743817b9-dd14-4ea2-841e-982c41f06525`).
  Do not poll/sleep/read child session files to wait.

## Current local verification: agent usage and activity (2026-10-01)

- Arithmetic delegation misuse was caller-side: truncated handles omitted `session:`,
  and queued follow-ups were mistaken for lost results. Sleeps, repeated starts,
  session-file searches, unrequested persistence and unreceived-result claims were
  incorrect. The complete `calc-check` handle inspected successfully; its extra
  process was stopped, and saved data was left intact.
- Implemented in `packages/subagents`: explicit async-input receipts and waiting
  guidance; malformed-handle errors; model-readable bounded output/errors; global
  roster observers driving pi-kit's above-editor widget during startup/streaming,
  with settlement/shutdown cleanup. `agent-teams/src/ui.ts` excludes standalone
  children to avoid duplicate widget rows. No result transport rewrite.
- Startup model-row follow-up: `MODEL` from the model-facing receipt was copied
  into the TUI summary as well as structured `model` details. The renderer now
  filters that receipt from the summary, retaining one expanded model line and
  leaving original content/details intact. RED observed for standalone/hosted rows;
  GREEN: **198 passed** (subagents suite + team coordination rows), TypeScript and
  package dry-run passed. Native PTY Ctrl+O verifies collapsed metadata stays hidden
  and expansion shows exactly one model line; resize/result/cleanup still pass.
- Contracts: @packages/subagents/features/agent-usage.feature and
  @packages/subagents/features/agent-row-tui.feature. Native verification uses
  @packages/subagents/tests/test_live_agent_usage.py with
  @tests/live-agent-usage-fixture.ts, isolated HOME/config and loopback-only model.
  Pi print/RPC plus PTY 48/90/240-column startup, result and cleanup passed.
- Latest broadened verification: subagents + agent-teams + kit + root ownership/entry
  tests: **566 passed, 3 unrelated failures**. Failures: stale four-action schema
  expectation in `test_agent_delegation.py`; fake child without RPC acknowledgement
  in `test_work_sessions.py`; existing 0.84.1/0.87.1 peer lockfile mismatch in
  kit's dependency-chain check. Root and native-fixture TypeScript checks passed;
  packed manifests passed for 18 packages. `pnpm check:install` reports 15 missing
  global package declarations; no global installation changes authorized or made.
- Concurrent local work changed `prompt` to `send`/`interrupt` and added saved-role
  persistence derivation during this task; those changes were retained and tests
  adapted. The active session still has the old tool schema until reload.
- Fresh review `agent-usage-review` returned an empty Session Result, not a valid
  review or acceptance. One bounded read-only retry `agent-activity-review` started,
  exact handle `session:agent-activity-review:a8cf7cc6-6514-4a67-acea-4fc474a65de0`,
  with explicit nonempty verdict/findings/limits. Await its automatic result without
  polling, sleeping or session-file reads; fix relevant findings and rerun affected
  checks. Independent review remains unverified until an actual report arrives.
  No commit, publish, destructive cleanup or remote writes.

## Packages

The vocabulary below is split by owning package. Each term is implemented by exactly one package, and no package names a participant it does not own.

| Package | Owns | Model-facing surface |
| --- | --- | --- |
| `@fradser/pi-subagents` | Agent, Work Session, Assignment Attempt, Session Result, Agent Memory, Computer Lease | `agent` |
| `@fradser/pi-tasks` | Task, Task Board, Task Status, Recovery Hold, Submission, Task Acceptance | `task` |
| `@fradser/pi-agent-teams` | Message, Coordination Event, Agent Presence, Team Console | `message` |

`@fradser/pi-agent-teams` is a bundle: installing it loads all three. Each package is also complete on its own.

## Language

**Agent**:
A persisted AI coworker with a stable identity, capability-focused Agent Memory, and work history that may span projects. Project definitions specialize the Agent for a project without turning it into a project-owned identity.
_Avoid_: Teammate, Bot, worker, sub-agent, resident process

**Leader**:
The coordinating role responsible for delegation and synthesis in a work context. A Leader can send and receive the same communications as Workers; the role is not a separate Agent identity or Definition scope.

**Worker**:
The executing role of an Agent Work Session for an Assignment Attempt. Workers can communicate with their Leader and peers through the same shared communication language.

**Temporary Agent**:
A session-scope in-memory actor with no disk `agent.md`, Agent Memory, private
workspace or persisted history. It becomes IDLE after results and accepts send
until stopped or its parent exits. It cannot be promoted or retroactively persist
its earlier conversation.
_Avoid_: Persisted Agent, promotion, automatic one-shot close

**Agent Definition**:
The versioned declaration of an Agent's identity, responsibility, instructions, and requested capabilities. The user definition is the persistent identity source; a project definition only specializes that same Agent, and each Work Session pins the resolved version.
_Avoid_: Role Template, project-owned identity, spawn configuration

**Project Memory**:
Durable facts, concrete decisions, and history of one project, available independently of any particular Agent. Abstracting a reusable lesson does not move or replace the originating project record.
_Avoid_: Agent Memory, complete chat history

**Agent Memory**:
Private durable knowledge of a persisted Agent's reusable capabilities, methods, judgment criteria, and operating patterns, including abstractions learned through project work, kept in the Agent's own folder. Project-specific facts, decisions, and history remain in Project Memory; Temporary Agents have no Agent Memory.
_Avoid_: Project archive, per-project subfolder, shared memory folder, complete chat history, session scratch state

**Memory Proposal**:
A versioned, evidence-backed candidate for Agent Memory that describes a reusable capability or abstracted lesson with its applicability and limits. Its learning source may be a project, but its content does not carry that project's concrete facts, decisions, or history.
_Avoid_: Direct memory write, project fact, unqualified generalization, self-reflection log

**Task**:
One durable unit of work recorded on the Task Board by a person, Routine, external event, or Agent handoff. A Task states what must be done and under which completion requirements; it never states who must do it. Ownership is derived from action and never declared, so a Task carries no assignee and any Agent or the main session may take it.
_Avoid_: Work Item, Direct assignment, Board Task, prompt-only task, assignee field

**Task Status**:
The lifecycle position of a Task: pending, in progress, completed, or superseded. Moving a Task into progress is the act of taking it, and completion is the only terminal transition for work someone actually did.
_Avoid_: Claimed, state, phase

**Recovery Hold**:
A flag on a Task whose last attempt ended in failure, withholding it from automatic taking until a participant proceeds with a stated reason. It keeps one transient failure from being silently retried by whichever participant happens to be idle, and it is not a Task Status.
_Avoid_: Blocked status, failed status, automatic retry

**Assignment Attempt**:
One authorization for an Agent Work Session to perform or hold a Task, acquired by taking the Task rather than by being named as its owner. It is distinct from Agent identity and from the Task. Each new assignment has a new attempt; completing, reopening, process exit, or stopping retires the old authority before another attempt can acquire it.
_Avoid_: Assignee, pre-declared owner, role grant

**Task Board**:
The shared register of Tasks and their availability, readable and writable by every Agent and by the main session through one interface. It is not a separate kind of work with different completion rules, and it does not dispatch work to a named Agent.
_Avoid_: Work Board, Second work lifecycle, independent task store, dispatch queue

**Submission**:
One candidate result supplied by the current Assignment Attempt, recorded as a success or a failure together with its evidence. An ordinary final answer and an explicit submission represent the same kind of evidence; a blocker reported as prose rather than recorded as a failure is not a failure. A revised result is a new submission, not acceptance of the previous one.
_Avoid_: Completed Task, message status, process exit, prose blocker report

**Task Acceptance**:
The decision that a current submission satisfies its Task's completion requirements, including any verification gate. Acceptance is distinct from execution ending, submitting a result, or integrating changes into another workspace.
_Avoid_: Work Acceptance, Final answer, report receipt, successful shutdown

**Handoff**:
An offered transfer of a Task between Agent Work Sessions, expressed as a Message to the target and finished by the current holder releasing it. The source keeps its resource authority until it releases, so the target cannot begin before then.
_Avoid_: Copy, immediate reassignment, pre-declared owner

**Routine**:
A standing trigger that creates a Task for an Agent from a schedule, external event, or Agent signal while the current Agent Teams runtime is available. Cross-session background execution is outside the current redesign.
_Avoid_: Repeated prompt, polling turn, promised background daemon

**Attention Request**:
A bounded request for human judgment or authorization containing the decision, evidence, recommendation, and allowed choices. Routine progress, ordinary routing, and recoverable execution remain internal rather than becoming Attention Requests.
_Avoid_: Status update, full transcript, generic stall notice

**Capability Grant**:
A user- or project-policy authorization that lets one Work Session use a requested external tool or computer capability. Grants may differ by Agent and Task, and become visible progressively as the Work Session needs them.
_Avoid_: Tool name in a prompt, shared credential, automatic role permission

**Computer Lease**:
Exclusive external resource authority granted to one Work Session. The subagent
package now provisions only ordinary scratch folders: no Git worktree, branch,
automatic commit or write isolation. Broader resource leases remain coordinator
concepts, not an execution-layer workspace promise.
_Avoid_: Agent identity, shared mutable desktop, working directory alone

**Takeover**:
An explicit transfer of a Computer Lease from an Agent Work Session to a person. Preview is read-only; Takeover pauses Agent writes until the person returns or ends control.
_Avoid_: Shared control, automatic access, transcript view

**Work Session**:
An isolated execution context of one Agent with at most one current Assignment Attempt. A resident Work Session can be unassigned or serve successive attempts. An Agent's concurrent work uses separate Work Sessions whose prompts, execution state, tools, and uncommitted memory remain isolated.
_Avoid_: Agent identity, shared chat, task thread

**Fresh Work Session**:
A new Work Session that receives its own assignment without inheriting the Leader's conversation history. Agent instructions and authorized capabilities are separate from that history.
_Avoid_: New Agent identity, new process only

**Forked Work Session**:
A new Work Session that inherits a snapshot of the Leader's active conversation context before pursuing its own assignment. It neither continues the Leader's session nor transfers the Leader's execution authority.
_Avoid_: Handoff summary, shared mutable conversation, workspace copy

**Process Incarnation**:
One temporary process executing a Work Session. A Process Incarnation may stop and later be replaced without ending the Agent, Work Session, or responsibility.
_Avoid_: Agent, Work Session, identity, permanent worker

**Session Result**:
The settled output one Work Session turn produced for the work it was given, handed to the Leader's session once per settled turn. It carries that turn's final answer verbatim and names its Agent and Process Incarnation; it is not a claim that the work was accepted, and an ended Process Incarnation whose turn produced none says so without requiring a turn.
_Avoid_: Submission, Message, Agent Presence, report receipt, progress update

**Agent Inbox**:
The Agent's persistent addressed-message queue. A message may wait with no active Work Session; an available Agent Teams runtime starts a Session only when the message requires a response or creates work.
_Avoid_: Ephemeral process inbox, broadcast transcript, background-daemon promise

**Agent Presence**:
The leader-visible state of an Agent and its Work Sessions, including whether work is queued, starting, active, waiting, blocked, or complete. Presence reports state without requiring a model turn.
_Avoid_: Status polling prompt, raw process telemetry

**Message**:
One point-to-point communication from a participant to a named participant, carrying either an information notice or a request that needs a decision. Sender identity comes from the runtime, and a recipient is addressed by name or by an exact session rather than by a thread or reply reference. A Message is not evidence, is not a broadcast, and does not submit results or change work ownership, acceptance, or lifecycle state.
_Avoid_: Agent Event, thread, reply chain, broadcast, attachment, worker-only report, caller-supplied sender identity

**Coordination Event**:
An asynchronous Message, work intent, verification result, or lifecycle marker that may propose a shared-state transition. Its authority depends on its source and the addressed state; an ordinary Message does not require an Assignment Attempt.

**Historical Evidence**:
A Coordination Event from an Assignment Attempt that is no longer current. It remains in Task history and may support capability-focused Memory Proposals, but cannot propose a current shared-state transition.

**Team Console**:
The interactive surface through which a leader views cross-project Agents, project Tasks, Work Sessions, and coordination history. It presents richer detail without adding model-facing tool parameters.
