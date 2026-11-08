# Handoff: continual-learning refactor and Goal Docker E2E
Last verified: 2026-11-08 (`check:install`, `bun run check`, Goal gates).
Plan: `/Users/FradSer/.claude/plans/vectorized-sprouting-peach.md` (outside).

## State
`78a9dd6d` committed the first green slice (one `/learning` menu, one final
outcome row, one `[learning] started` row); HEAD `1dc2a3c4` (other session).
Shared checkout has ~154 uncommitted files from other sessions; not a clean
per-session diff. Phases 1-4 (option B, additive harness_write, no-tools inlinedossier, single command + retired worker loadout) are DONE and green; the
result row is now expandable and a live activity row is shown (follow-ups).
Nothing committed since; index 0 staged.

## Phase 1 / option B (details: adr-0014 + session memory)
User chose B. Harness-only ENTRY route uses a pure classifier over the last real
`role:user` entry (`learn-intent.ts`); global screen truth table and
test_learning_efficiency.py unchanged (frozen evidence). `TOOL_NAMES.learn` (no
alias), dual-intent guidance all naming `learn`; 9 flags + planner-json-output
unchanged. `startHarnessProcedureForLearn` (WeakMap bridge) opens the identical
guarded procedure; `learn()` returns honest `authoring-started`, never fakes a
receipt/write or starts Memory. Settled dedup prevents a second rule. Tests:
learning-single-tool.feature, learn-intent (6), learn-harness-route (3),
learning-single-tool (8). Fresh-agent 4 defects ALL fixed with RED; no defect
in write-time gates/screen/bridge/Memory gates/dedup. Gate: typecheck, bun check
323/0; frozen proofs/fixtures/ADR-0012+0013 byte-identical.

## Invariants (do not drop)

- Memory is untrusted discovery context. Harness writes: parent positive AND
  negative cases, exact candidate/predecessor bytes, no-UI fail-closed, option
  confirmation, atomic write + readback + rollback, receipt, undoable record.
- One learn() call: one started row, one final row (expandable for applied safe
  Memory), complete receipt in `details`/disk, no second pipeline.
- Frozen, byte-identical: 6 proof files (`tests/continuous-*`),
  `tests/fixtures/**`, preintegration copies, `tests/jev-*.json` manifests,
  `docs/adr/0012` and `0013` (supersession goes in a NEW ADR, never an edit).
- Keep the 9 `--learning-*` planner-child structured-output flags and
  `extensions/planner-json-output.ts`. Keep `TOOL_NAMES.learningRead` as a
  frozen-dossier evidence marker even after the tool registration is retired.
- Never run real-model / paid / `--live` runners without explicit authorization.

## Phase 2 / 3 DELIVERED (details: adr-0015, session memory)
Phase 2 added `harness_write` (declared parent-owned tool, strict native wire,
exact bytes + cases + confirm + atomic write + rollback); additive, all gates
green. Phase 3 moved 3 of 4 planner spawns to `--no-tools` + inline bounded
dossier (`planner-inline-dossier.ts`); the DYNAMIC current-source collector
STAYS because 6 frozen proofs bind its 18-read prefix. Deleted
harness-planner-preview.ts + plannerReadArgs; kept 9 flags, structured output,
`TOOL_NAMES.learningRead` evidence marker. Both gates green (bun check 335/0,
typecheck, PTY/loopback, frozen SHA). Full pytest went 18->14 baseline
failures; the remaining were detector/corpus drift and another session's
in-flight jev-learning.ts consent refactor, deliberately not taken over.

## Phase 4 DELIVERED (2026-11-06)
Goal: "旧版本彻底删除掉" -- converge on `/learning` + one `learn` tool. RED
first (command-surface-retirement.feature 5 scenarios +
test_command_surface_retirement.py 6 tests). Completed, gates green:

RETIRED (production): WORKER_LOADOUTS / workerCliArgs / workerToolNames /
createWorkerToolSurface / harnessCheckCases / planner case tool + loadout, CLI
allowlist and worker tool_choice. tool-surface.ts now owns 4 canonical names +
createParentToolSurface + createCollectorToolSurface (keeps the collector's
one-read budget, sessionStart activation, tool_choice:"none" prefix-stop
VERBATIM). planner-read-scope.ts + memory-maintenance-audit.ts migrated to
createCollectorToolSurface / TOOL_NAMES.learningRead. tool-surface.test.ts 6->3.
- /learning menu Harness branch now calls startHarnessProcedureForLearn
  DIRECTLY (WeakMap bridge, same as learn tool); no getCommands().find, no
  "Use /harness" notice.
- Guidance (AGENT_LEARNING_TOOL_GUIDANCE, SETTLED_LEARNING_GUIDANCE, tool
  description, project_memory_protocol), 6 runtime diagnostics, both READMEs,
  CONTEXT.md: old slash commands are no longer offered or named to users;
  only /learning is documented. Features rewritten: command-surface-retirement
  (new), learning-command, simple-command-surface, tool-surface.

DELIBERATELY KEPT (internal, NOT user-facing): /memory + /consolidate
(inject-memory.ts), /harness (guardrails.ts). FROZEN proofs drive `/memory
整理记忆` / `/consolidate backfill` through REAL `pi --print` argv
(live_automatic_source_refresh.py:611/623, live_continuous_project_learning.py,
test_continuous_project_protocol.py, continuous-command-proof.ts:273 literal
argv); OFFLINE E2E drives /harness (live_harness_first_run.py,
live_meaningful_details.py PTY, test_harness_authoring_preview.py). Deleting
breaks frozen provenance + E2E; AGENTS.md forbids reclassifying frozen cohorts
/ weakening validation for green. Absent from all menus/guidance/doc tables.
NOT literal deletion -- disclosed plainly.

VERIFICATION (green): typecheck; bun test 163/0; check 332/0; retirement pytest
6/6; pack + pack:check(21); offline loopback passed/requests:0; PTY passed;
diff-check; 8 frozen MATCH. Full pytest SAME 14 baseline failures (Phase 3).
Fresh-agent INDEPENDENT REVIEW did NOT complete (2 read-only attempts timed
out); equivalent main-thread checks done (tool-surface.ts UNTRACKED at HEAD,
collector 163 bun + test_maintenance_collection_stop 11/11, docs/tests/features
cross-checked). No production defect found. Nothing committed; 0 staged.

## Zero-call preflight, backlog quarantine, detector parity (2026-11-07)
User proved one real failure (sensitive guard scanning existing corpus in the
WAL) was misreported as 4. Fixes, all RED-first:
- `learning-history.ts normalizeTrackedMemory`: only actual drift/leak targets
  enter the WAL; no-change runs create ZERO history rows (mirror-hold bun tests
  updated from the obsolete "1 applied sync" expectation).
- `learning-efficiency.ts` + `inject-memory.ts`: `preflight` phase, fixed
  diagnostic, and `no model calls` ONLY for receipts with a preflight/screen
  attempt; failed workers with unknown usage still say unavailable.
- `learning-backlog.ts`: old `auto-memory-off` rows are quarantined (retained,
  never replayed); malformed counting is scope-isolated; damaged rows still
  fail closed. `beginBacklogAttempt` now binds in a clean scope. Regression in
  BOTH test_learning_backlog.py and test_learning_controls.py.
- `consolidation-run.ts` + `scripts/validate-consolidate.py`: `Auth:` mode-label
  and bracketed/quoted placeholders stay benign; `*_WEB_KEY` and realistic
  secrets are refused; structured object members stay strict; both detectors
  classify the shared 40-sensitive / 25-benign corpus identically (0 FP, 0 miss).
  Three sanitized positive samples added to the corpus; no real secret stored.
Gates: typecheck; bun test 163/0; affected pytest 202/0; pack; diff-check.
Full pytest: 10 baseline failures remain (frozen `codeHashes` manifests bound
to shared-tree source + another session's in-flight Jev refactor), confirmed
pre-existing by reverting `credentialNamedKeyAssignsValue` and re-running 2 of
them. NOT weakened for green. Data unseal (3 private Memory files) NOT done:
AskUserQuestion timed out with no response, which is NOT consent. Nothing staged.

## Docker E2E: hunyuan-eval/hy4-dev (2026-11-07, STOPPED)
Model is in Magpie (10.10.0.195:3425/v1), NOT cliproxyapi; `sk-dummy` is a
gateway-special public key; containers need the host InferenceProxy. Disposable
agent dir, no repo edits, no credential literals. Run 1: 0 requests because
`run_pi` read `selection['provider']` while `write_agent_config` writes
`{"model":"provider/model"}` -> FIX `selected_model_ref` (RED test). Run 2:
24 requests / 525448 tokens / 0 errors, learning stopped with empty index,
`real-regression-task` hit 900s. Run 3 (--run-timeout 1800): learningSeconds
991, `learningCommandNativeSuccess` + `regressionChanged` TRUE, failed at
`native-harness-enforcement` because `run_project` overwrote
continual-learning.json with `{"jev":false}` and dropped `model` -> planner
child 404 "magpie knows no model" -> FIX `jev_arm_learning_config` (merge,
RED test, 130 docker_experiment tests green). Run 4 launched, then STOPPED when
user redirected to the real single-run local failure above; NOT verified.
Evidence: /tmp/cl-hy4-e2e-{retry,budget,final}-20261107*, no leftover containers.

## Readable subagent control rows (2026-11-07)
Expanded `[agent] steered` rows were too engineering-heavy; `intentDetails` now
returns only substantive facts (model, tools, role description, evidence,
preview, error), with handles in structured details. `agent_list` keeps its
handles; coordination rows keep `role ·`. RED first, gates green; changeset
`.changeset/subagents-readable-control-rows.md`.

## Real-project classification and filename fixes (2026-11-08)
Three user reports, all RED-first. (1) Voice-Bloom-MVP: `Operation
classification disagrees ...` then `repair dropped recognizable selected
operation` (one chain, not two bugs). Root cause: `indexMemoryCorpus` calls a
no-mirror selected file private, `readPrivateClassifications` only read the
`(harness only)` marker, so a correct private delta was rejected and the
structural repair ran needlessly. Fix: validator uses the same mirror signal
(`run.manifest.publicDir ?? resolveMemoryPaths(cwd).publicDir`); real artifact
now expands both operations as private. (2) Home Lab: `invalid Markdown child
name '88.1-dual-wan-loadbalance-research.md'`. Both `MEMORY_NAME` guards now
allow dotted version names but still refuse leading/consecutive/trailing dots,
path components and repeated `.md` segments. Live fixtures claiming `safe`
without a mirror were corrected to declare a real public root.
(3) User asked why `Learning held: ... no planner started` appeared and said
credentials must not stop learning ("模型会自己处理"), then "删除启动前隐私闸
的所有设计". Deleted the whole design: three pre-pipeline screens, agent-tool
held report, 3 hold constants and both summary/tone branches; 2 feature
scenarios and 3 tests now assert ordinary pipeline outcomes with no screening
reason. `screened` stays only as a historical receipt enum value (frozen
cohorts are not reclassified). Write-side guards (WAL, display, Jev preflight,
semantic review) and explicit `/memory <secret>` refusal remain.
Gates: affected pytest 177/0 + 3 new RED/GREEN, full pytest SAME 10 baseline,
typecheck, bun 163/0, pack, diff-check.

## Goal Docker E2E: hunyuan-eval/hy4-dev (2026-11-08)
Pi 1.5.0 removed `@earendil-works/pi-ai`'s `Type` re-export; Goal now builds
schemas from its declared TypeBox peer. RED regression in
`goal_simplified.mts` + `features/goal.feature`; GREEN scripted Docker gate on
Pi 1.5.0 (`GOAL_DOCKER_OK`). Explicit real-model E2E added:
`packages/goal/tests/goal_real_model_e2e.py` (fresh source-bound image, host-only
InferenceProxy, disposable agent dir). Final strict run:
`/tmp/goal-real-model-hy4-20261108-symlink`, 19 requests / 0 errors after all
review fixes (earlier strict runs: `review`, 9 requests; `final6`, 11), terminal
goal status `complete`, native `get_goal/create_goal/write/bash/update_goal`
events and tool-less completion check. A prior active status falsely graded
as passed; `goalTerminal` and the runner's terminal-only `done()` now reject it.
Final gates: 33 pytest, package/root typecheck, pack, scripted Pi 1.5.0 Docker
(`GOAL_DOCKER_OK .../goal-docker-RY895RKG`), and the strict fresh-image
real-model run. Independent review fixes: terminal delegated results, Goal-id
bound waits, session-bound monitor observations, canonical project paths,
provider-error settle skip, and a three-turn bounded wait. Evidence scan: 16
directories / 128 files, zero hits for either host credential value; all Goal
containers removed. `fix all needed` repaired the live Pi installation: added
eight missing sources to `~/.pi/agent/settings.json`; `check:install` (20/21)
and `bun run check` (332 bun tests, typecheck, 21 packed manifests) are green,
as are Goal pytest 33/0, Goal test tsc, pack and four native PTY probes. Repeated
`Goal check-in` notices are harness evaluator 400 Antigravity quota responses,
not Goal defects. Evidence proves one native real-model lifecycle, not model
quality or benefit. `HANDOFF.md` stays under 200 lines.

## Remaining limitations / next
Literal deletion of 3 hidden internal registrations would break frozen proofs /
offline E2E (AGENTS.md forbids reclassifying frozen cohorts). 10 full-pytest
baseline failures remain (not weakened for green). Private Memory data unseal
needs explicit user consent. Docker run 4 and strict-provider harness_write
dialog remain unverified. Nothing staged; commit via /git:commit skill.
