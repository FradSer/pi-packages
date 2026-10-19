# 0009: Record the Memory correction worker budget

## Status

Accepted 2026-10-18, after three consecutive paid Pi 1.2 cohorts were aborted at
semantic Memory repair and after an independent reviewer with no implementation
history raised two blocking findings that were repaired before acceptance.

Scope: one worker budget and one evidence-marker filename in
`packages/continual-learning`. Supersedes no earlier ADR. Every semantic
threshold, request bound, retry count and mutation gate is unchanged.

## Context

Independent body review and semantic Memory repair both run a one-shot Pi worker
with `--thinking xhigh` over complete frozen evidence, and both used the same
230-second parent abort.

Three consecutive paid cohorts were aborted at exactly that bound: `v64`
230217 ms, `v72` 230176 ms and `v73` 230115 ms, all `exitCode 143`. The retained
`v73` usage ledger reported `assistantMessages: 0` with all-zero usage, so no
assistant message had completed when the parent timer fired. That evidence sits
outside this repository, in the recovery evidence root recorded by
`packages/continual-learning/CONTEXT.md`:
`.../continuous-reviewed-deepseek-pi12-memory-purpose-v73/idle-final-review-evidence/memory-repair-usage-dd01946c-bbe6-4a2b-b127-4cc7ed98d4ee.json`,
whose `-lifecycle-` sibling reports `timedOut: true`, `exitCode: 143`,
`durationMs: 230115`.

The same run measured the smaller sibling worker. The two-target body review
completed at 184004 ms with 22549 output tokens, 46 seconds inside the same
230-second bound. The correction workload therefore already ran close to its
budget, and the heavier amendment needed more than it had.

Those runs establish only that the parent abort fired before a complete answer
arrived. They do not establish whether the service was generating, stalled, or
would have finished with more time. A longer budget is a prospective
intervention that still requires real-model verification.

Two enclosing bounds matter. A continuous study runs one task CLI, and the
automatic learning phase inside it, under a 900-second guardian in bounded mode
and a 7200-second guardian in unlimited mode
(`tests/live_continuous_project_learning.py`). The package also already treats
15 minutes as a phase-level budget for heavy workers
(`HARNESS_PHASE_TIMEOUT_MS`, `AGENTS_PHASE_TIMEOUT_MS`).

## Decision

- `MEMORY_CORRECTION_WORKER_DEADLINE_MS = 600_000` (10 minutes) is the single
  recorded budget for both Memory correction workers: independent body review and
  semantic Memory repair. It is about 2.6 times the previous worker budget.
- The Harness correction path keeps its own 230-second bound. Planner, selection,
  transport and per-request deadlines are unchanged.
- The parent writes distinct started and closed lifecycle markers
  (`memory-repair-lifecycle-<ledgerId>-started.json` and `-closed.json`), so both
  are retained. Previously the closed write reused the started filename.
- A timeout still retains the rejected proposal, the parent-controlled markers
  and known partial usage. It admits no mutation, adds no retry and changes no
  semantic gate.
- The recorded budget is disclosed per cohort by the study protocol. Because two
  heavy correction workers can outlast the bounded 900-second task guardian, a
  guardian interruption stays an interrupted observation and never a pass, and a
  correction acceptance run uses the unlimited guardian. The guardian stays
  authoritative over any worker budget.
- Historical cohorts keep their original budget and failures. A cohort that hit
  the 230-second bound is not relabelled, and the longer budget is not evidence
  that a repair now succeeds.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep 230 seconds and shrink the request | Every authorizable reduction removes complete bodies, cited evidence or the held-body reasoning the gates require. The package forbids trimming evidence or lowering a threshold to make an experiment pass. |
| Split the combined amendment into sequential requests | One bounded amendment is the authorization unit. Splitting it would create partial authority and contradict the contract that one bounded amendment covers every held record. |
| Lower `--thinking` for held bodies | Held source, permission and preservation bodies require `--thinking xhigh`. A cheaper reviewer is a different judgment, not the same one. |
| Align to the existing 15-minute phase budget (900 seconds) | It equals the bounded task guardian that encloses the learning phase, so it would be unreachable in bounded mode without changing the study's own bound. |
| Add a second retry or reopen the deadline | Adds paid spend without evidence, and the package forbids added retries to make a run pass. The retry count is unchanged. |

## Verification contract

- `tests/test_memory_repair_deadline.py` covers child termination, retained
  partial usage, parent-cancellation precedence, the recorded value itself, and a
  repair that needs more than the historical 230 seconds but less than the
  recorded budget and is accepted. It asserts the recorded deadline on the
  started lifecycle marker and an untimed-out closed marker.
- `tests/test_body_review_output_contract.py` proves the body review uses the same
  recorded budget and is aborted without producing any judgment when it never
  answers.
- Proving the budget is not proving a semantic correction. A real cohort must
  still satisfy every learning-coverage field, and its acceptance run must use the
  unlimited guardian.
- Checks at acceptance: full package suite 1997 passed and 1 skipped,
  `pnpm typecheck` and `pnpm --dir packages/continual-learning pack --dry-run`
  green.

## Consequences

A longer budget costs wall-clock time on the few runs that need it: a failing run
stays occupied for up to 10 minutes per worker instead of aborting at 230 seconds,
and in bounded mode it can now reach the 900-second task guardian. The change
delays a demonstrated premature abort. It does not establish that 600 seconds is
sufficient, and a future cohort that still hits the recorded bound is a new
finding rather than a regression of this decision.