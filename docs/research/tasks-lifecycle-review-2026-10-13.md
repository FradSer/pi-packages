# Tasks lifecycle review

## Scope and evidence

This review starts with the user-supplied two-machine reconciliation record.
The record reports local success and an unreachable remote host.
This review does not verify those machine results or execute that plan.

Source baseline: `8c827980`. The workspace contains unrelated local changes.
No Tasks runtime source changes belong to this review.

## Current chain

1. The presence module tells the model when to record work.
   Source: `packages/tasks/src/presence.ts:38–45`.
2. The tool module validates input and calls the store module.
   Source: `packages/tasks/src/tool.ts:630–762`.
3. The store module checks dependencies, ownership, evidence, and declared verdicts.
   Sources: `packages/tasks/src/store.ts:704–745`, `:923–966`, `:1016–1120`.
4. The extension saves changes and restores session-specific records.
   Sources: `packages/tasks/src/extension.ts:65–121`, `packages/tasks/src/persist.ts:44–93`.
5. The stop-check module checks available work and tool receipts before settlement.
   Source: `packages/tasks/src/stop-check.ts:146–209`, `:270–323`.
6. The rendering module displays task fields through pi-kit.
   Sources: `packages/tasks/src/rows.ts:32–99`, `packages/tasks/src/stop-check.ts:214–250`.

Tasks records work. It does not execute the plan, inspect a remote host, or prove a model's verdict.
The README states this distinction: `packages/tasks/README.md`, Tools and states and Automatic continuation.

## Findings

### 1. Recovery does not present the remaining work as one coherent view

Strength: Strong. This is a design finding, not a state-transition defect.

The case combines two machine outcomes under one completion gate.
The local outcome cannot become a separately completed record while the remote outcome remains blocked.
The reminder displays the original description and gate alongside the current blocker.
It does not display `context.handoff`, although the handoff can contain verification and outstanding work.
Sources: `packages/tasks/src/types.ts:83–143`, `packages/tasks/src/context.ts:23–38`,
`packages/tasks/src/stop-check.ts:101–118`, `:233–248`.

The agent can already split work into independently verifiable tasks.
The package therefore does not necessarily need subtasks or a partial-completion status.
For this case, separate local and remote tasks are a candidate, subject to the actual backup ordering requirement.
Do not impose an invented dependency or repeat completed machine writes.

Candidate: deepen the recovery-view module, using existing task evidence and handoff fields.
Keep the original description as the contract. Present verified results, remaining work, and the blocker separately.
This improves locality across native display and model text without adding execution authority.

### 2. Model text can report an old recovery note instead of the current blocker

Strength: Strong. Confirmed with an isolated source probe.

`executeTaskGet` builds its BLOCKED text from `recoveryNote`, not `blockedReason`.
The projection contains the current blocker, but the content text can omit it.
The tool module explicitly states that the model receives content.
Sources: `packages/tasks/src/tool.ts:410–414`, `:538–555`.

Probe:
- Start with recovery note `Earlier recovery note`.
- Block the task with reason `Current remote blocker`.
- Read it through `executeTaskGet`.
- Content reports `BLOCKED · Earlier recovery note`.
- The projection reports `blockedReason: Current remote blocker`.

This probe uses invented conditions. It does not prove the original session read stale text.

Candidate: deepen the task-projection module so model text and native display share current-state meaning.
Do not collapse historical recovery evidence into a current blocker.
Test through the tool interface, not private formatting calls.

### 3. Recovery text bypasses the retained-text budget

Strength: Strong. Confirmed with an isolated source probe.

`taskContextBytes` does not count `recoveryNote`.
`takeTask` passes the supplied reason into `recordTake` without a budget check.
Sources: `packages/tasks/src/context.ts:78–101`, `packages/tasks/src/store.ts:704–742`, `:1314–1327`.

An isolated task accepts a recovery reason containing 70,000 ASCII bytes.
The task retains all 70,000 bytes. Its measured retained-text size is only 27 bytes.
The README describes a 64 KiB default budget that includes recovery notes.
Source: `packages/tasks/README.md`, Persistence and compatibility.

Candidate: deepen the retained-evidence module so every transition applies the same retention contract.
Preserve runtime cleanup rules that release stopped holders even when legacy records exceed the budget.
This is a correctness fix, not permission to shorten existing user evidence.

### 4. Automatic continuation measures tool novelty, not task progress

Strength: Worth exploring. Confirmed implementation; benefit remains unmeasured.

A successful, distinct non-excluded tool receipt sets `performedWork`.
The receipt has no link to a task or acceptance criterion.
A successful read can qualify. A successful receipt does not establish useful task progress.
Sources: `packages/tasks/src/stop-check.ts:270–300`, `:169–177`.

The predicate is a useful loop guard, but its name and display explanation can imply more than it proves.
Before changing the policy, measure false continuations and premature stops in actual sessions.
Do not replace this rule with model judgments without evidence of added value.

Candidate: concentrate continuation policy and its explanations in one module.
Keep three-turn limits, input ownership, and deliberate blocked recovery.
Test both resumed useful work and unrelated successful tool activity.

### 5. Passive status repeats the contract rather than prioritizing the state change

Strength: Strong for this case; frequency is not measured.

Every status snapshot carries complete displayed descriptions, gates, evidence, blockers, and recovery notes.
The renderer requests `fullSummary: true`.
Sources: `packages/tasks/src/stop-check.ts:101–118`, `:223–248`.

This preserves text but can obscure the only actionable change: the remote task remains blocked.
The explicit `get_task` read and passive waiting reminder have different purposes.
A shorter passive view must not delete evidence or weaken explicit detail reads.

Candidate: deepen the status-view module around the current decision.
Show what remains, why it cannot run, and what would permit recovery.
Keep complete task information available through the explicit read interface.
Native PTY verification is required before changing display behavior.

### 6. A recovery reason guards taking work, not every successful delivery

Strength: Worth exploring. Confirmed behavior; the desired policy requires a decision.

A blocked task can accept successful delivery with evidence and a passing declared verdict.
It does not require an intervening take or a new recovery reason.
Sources: `packages/tasks/src/store.ts:923–966`, `:1037–1086`.
An isolated public-tool probe confirms completed status with no recovery note.

This can support recording work completed outside the task tool sequence.
It also means that a recovery reason is not an enforced condition for every route out of blocked state.
Do not describe that reason as proof of evidence inspection or authorization.
Decide whether direct verified delivery is intentional before tightening this interface.

## Preserve these properties

- Blocked tasks do not silently restart.
- Dependency waits remain pending rather than becoming failed attempts.
- Foreign holders cannot be taken over through ordinary task tools.
- Session restore retains evidence and requires recovery for interrupted work.
- Unreadable task files are not overwritten as empty state.
- Earlier settlement entries remain intact.
- Headless waiting does not replace the final answer.
- A recorded pass is not independent verification.

Sources: `packages/tasks/features/task-stop-check.feature`,
`packages/tasks/src/extension.ts:91–121`, `packages/tasks/src/store.ts:704–745`,
`packages/tasks/src/stop-check.ts:146–209`, `packages/tasks/README.md`.

## Independent review follow-up

A read-only child reviewed the store, persistence, tools, and Agent Teams consumers.
The parent confirmed the two following source paths. These findings change the priority order.

### Refused delivery still produces an Agent Teams outcome

`finishCompletion` and `finishFailure` test the returned object for truthiness instead of checking `.ok`.
Both accepted transitions and refused transitions return objects.
A refused store write can therefore still produce a completion or failure announcement.
The completion path also frees the agent after a refusal.
Sources: `packages/agent-teams/src/team-machine.ts:2251–2262`, `:2279–2290`,
`packages/tasks/src/store.ts:1037–1086`.
This is confirmed source control flow. It has no runtime reproduction in this review.
It is not established as the cause of the user's waiting message.

### Remaining work cannot be retired from the handoff list

`mergeTaskHandoff` unions `outstanding` items, including updates that supply an empty list.
Source: `packages/tasks/src/context.ts:443–455`.
Historical findings need retention. Current outstanding work needs an explicit resolution contract.
A new recovery view must address this difference, rather than present stale items as current work.

### Additional findings awaiting reproduction

The child also identified these source paths:

- Repeated failure delivery replaces the previous result and failure evidence: `packages/tasks/src/store.ts:1090–1104`.
- Taking a task clears an operational blocker without copying it into failure evidence: `packages/tasks/src/store.ts:1314–1325`.
- Missing completion outcome omits the mixed-call retained-edit response: `packages/tasks/src/tool.ts:726–730`.
- Valid JSON without a tasks field returns an absent store: `packages/tasks/src/persist.ts:69–86`.

These need focused probes and regression checks before implementation.
Evidence history and malformed-storage policies need explicit acceptance decisions.

## Recommended order

1. Reproduce and fix refused delivery handling in the Agent Teams adapter.
2. Fix current-blocker text and recovery budget enforcement with failing regression tests.
3. Define how current outstanding work is resolved while historical evidence remains available.
4. Develop one recovery view and distinguish passive status from explicit detail reads.
5. Verify mixed-call and malformed-storage findings.
6. Measure continuation outcomes before changing scheduling policy.

Do not start with additional statuses, remote retry timers, or a general-purpose workflow engine.
The case shows an incomplete recovery view, not a requirement for those features.

## Verification and limitations

- Focused checks: 43 passed.
- Full Tasks suite: `python3 -m pytest packages/tasks/tests/ -q`: 164 passed.
- Source probes run through the existing Node test helper with a disposable agent directory.
- Public tool probes confirm stale blocker text, oversized recovery acceptance, and direct blocked-to-completed delivery.
- Probe observations are retained in `docs/research/tasks-lifecycle-review-probes-2026-10-13.json`.
- A first `pnpm exec tsx` attempt failed because pnpm requested a dependency installation without a TTY.
  No installation was accepted. The probes then used the existing Node test helper.
- No runtime source changed. Typecheck, packaging, installation, and PTY acceptance were not rerun.
- No remote connection, real-model recovery, or original-session reproduction was performed.
- Green existing tests establish their current contracts, not completeness of lifecycle acceptance.

## Acceptance candidates

These are proposed checks, not existing product requirements.

- Given local completion and remote failure, a recovery view identifies only remaining remote work.
- Given a previous recovery note and a new blocker, model text reports the new blocker first.
- Given an over-budget recovery reason, the public tool refuses it without changing state or holder.
- Given explicit detail reads, complete evidence remains accessible after passive display changes.
- Given unrelated tool success, continuation follows the selected policy and reports its actual basis.
