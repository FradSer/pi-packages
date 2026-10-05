# Resident contract consumer handoff

## Scope and current state

Consumer adaptation follows @../features/disk-identity-resident.feature and the
execution authority in @../../subagents/VISION.md and @../../subagents/AUTHORITY.md.
No dependency, manifest, parent test/harness, task-board business, real Pi config,
commit or publication changes were made by this consumer task. The excluded files
`independent-work-fixture.ts`, `test_work_sessions.py`, `e2e/install-fixture.ts` and
`features/human-readable-coordination-rows.feature` were not edited by this task.
Pre-existing and concurrent changes remain intact.

Production changes: `src/team-machine.ts`, `src/agent-host.ts`, `src/agent-actions.ts`,
`src/index.ts`, `src/guidance.ts`, `src/types.ts`, `src/ui.ts`, `src/tool-copy.ts`.
Documentation: `README.md`, `references/agent-roles.md`.

- Removed identity persistence, Memory opt-in, Git/worktree/commit/preserve/release
  paths from this consumer. Disk scope supplies mandatory Memory and ordinary
  private data; temporary children use project cwd and no-session. Both kinds
  launch in the original project, not scratch. Durable contribution pins canonical
  definition/source/scope plus role, effective tools and project cwd.
- Published acknowledged exact `send`/`interrupt` controls. Send preserves the
  same process/history; a later independent input publishes its attempt before
  RPC delivery. Active interruption retains its sequence and attempt. The
  runtime owner added public host routing and `deliverResidentSteer`; this task
  did not edit subagents runtime files.
- Prompted startup awaits correlated accepted input; prompt-less startup awaits
  native readiness. Pending input reserves the incarnation, fast result callbacks
  stay idle, negative ack cannot undo settled evidence, timeout retains authority,
  and drain-before-input rechecks verification freezes.
- Pinned role is delivered on first input only for send; temporary roles are not
  cleared by the team extension. Task acceptance, worker reporting and peer
  message business semantics remain unchanged. No new_session on public send.
- Idle guidance was shortened, not its ceiling raised. UI trailing whitespace
  was removed. Tests isolate HOME/Pi config/XDG roots before subprocesses.

## Verified on Pi 0.99.2

Commands use `uv run --no-project --python "$(command -v python3)" python -m pytest`.

| Check | Result |
| --- | --- |
| `packages/agent-teams/tests -q` final run | **281 passed** |
| `tests/test_three_package_installs.py tests/test_prompt_budget.py -q` final run | **28 passed** |
| `packages/tasks/tests -q` with outer temporary HOME/config | **43 passed**, no task files edited |
| `pnpm typecheck` | Passed |
| Strict standalone tsc of new resident fixture + two native TS probes | Passed |
| `pnpm --dir packages/agent-teams pack --dry-run` | Passed |
| `pnpm pack:check` | **18 packed manifests** passed |
| `pnpm check:install <temporary-settings.json>` using cached pnpm executable and generated local sources | **17 entries** passed; no real settings read |
| Owned-path `git diff --check` | Passed |

Native coverage is real Pi 0.99.2, fixture-only in-process/loopback providers:
`test_native_disk_identity.py` proves disk Memory binding/injection, private
project history, temporary two inputs in the same PID/incarnation/history, and
busy interrupt in the same sequence. `test_bundle_ack.py` proves bundle kickoff
has a correlated native started/queued response, expected tools and shutdown
closure. Full package suite also executes real print/RPC and PTY message
expansion/resize checks. No production provider or user auth/config was used.

RED evidence: initial 11 regressions failed, including early host receipt before
kickoff ack. Hosted send/interrupt controls first failed as missing. Three extra
invented callback-order probes failed before fixes: late negative response after
settled output, sibling send during pending startup ack, and verify gate opened
while draining a final report. They test adjacent hypotheses, not a reproduction
claim about the original symptom.

## Limitations and remaining acceptance

- A fresh read-only reviewer is required for cross-module/concurrency acceptance;
  this session has no fresh-agent dispatch tool. Parent should review the final
  `sendResidentSequence`/startup reservation/negative/timeout/verification paths.
- Native loopback print/RPC and PTY tests passed; authenticated real-provider
  control delivery and manual `/agent-teams` console acceptance were not rerun.
  Those require separately authorized isolated config, never real user HOME.
- Historical opt-in scripts `live-agent-reopen.ts`, `live-unassigned-start.ts`,
  `live-capability-blocker.ts` predate the current flat tool contract and were not
  used as evidence. `live-child-env.ts` still assumes caller-owned auth/config;
  it was not run. Use the new isolated native probes for this change.
- The first isolated Corepack audit invocation was blocked from downloading pnpm;
  rerunning the cached 11.21.0 executable with network disabled passed. Earlier
  parent-owned observer/scripted fixture failures disappeared after concurrent
  owner repairs; final 25 install tests pass.

No fresh review or unrun production verification is claimed by the passing tests.
