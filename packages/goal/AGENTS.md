# Goal Runtime Package Guidelines

Applies to `packages/goal/` (`@fradser/pi-goal`). User instructions take precedence.

## Runtime boundaries

A Goal is one thread-scoped objective. Do not add a second requirement text, a
Task tree, progress fraction, saved next-action workflow, dedicated research agent,
independent user history, or Goal archive. Use ordinary tools for investigation.

- `store.ts` is the sole record writer. One atomic record holds the objective,
  usage and scheduler state. Mutation checks and the final
  write occur under the same exclusive lock, and no operation deletes a record.
  Preserve existing legacy files.
- State lives under Pi's own agent directory, keyed by project: a new goal writes
  nothing into the working tree. A goal stored by an earlier version inside a
  project is still read, locked and written where it lives.
- A finished goal is terminal. The record is kept, and no later writer — a stale
  charge, a check that finished after someone else completed the goal, or another
  session's stop — may move it out of `complete`.
- Only the thread's own focus entry restores its goal. A boundary drops queued
  continuation, live checks and revision activation. Restore is not authorization.
- A timer, settled turn or queued message is an opportunity, never authorization.
  Arm and claim separately; recheck identity, owner, generation, phase and dispatch.
  Accept a checkpoint once. Never replay unknown delivery.
- Continue only after successful effective work and without pending user input.
  Progress means a workspace change: only an unseen successful `edit` or `write`
  earns the next run, while reading, searching, fetching, commands and delegated
  child work explore.
  Three consecutive runs that change nothing stop the loop and name the window;
  a requirement revision must not clear that memory, and a user's own turn does
  not count against it. Repeated identical tool receipts and pending monitors
  cannot sustain the loop. Unrelated background activity is not progress. Empty
  or failed work waits; only the user pauses. Resume preserves lifetime usage,
  continuation count and a fresh change window.
- A recurring blocker requires three consecutive model turns. The same-turn
  report counts once; effective work, changed requirements and restore reset it.
- Only an explicit completion request runs one fresh tool-less completion check.
  No inspecting reviewer and no shell grant. Pass the complete objective; do not
  approve a truncated prefix. Runtime observations have thread,
  call, outcome and requirement-boundary provenance. Escape every untrusted payload.
- A final marker decides MET/NOT MET. Missing markers, errors, cancellation and
  outdated results are distinct and never complete the Goal. Refusals do not pause.
- Usage is a report, never a ceiling. Main-model and completion-check usage are
  recorded against the open Goal, and every path that charges it — including a
  cancelled or superseded check for the same open Goal — keeps the goal running. No
  spending cap, budget field or cap verb exists, and none may be added: a goal is
  bounded by the work it does, not by a number. A record an earlier version wrote
  with a `tokenBudget` is read without it, and a cap-era status reads as `paused`.
  A record an earlier version wrote with a `verificationContract` is read without
  that field too, because the objective is the only requirement a check judges.
  An action verb applies only when typed alone, so `/goal clear my schedule` stays a
  request.
- `/goal <text>` queues a request, preserving the old record until a complete
  merged revision lands. Activation needs matching accepted delivery, not void
  send success. Completion and clear write the terminal status and keep the record
  without an archive.
- Every Goal tool declares its parameters and refuses a call that carries any
  other field, even when the declared part would be valid. A stale schema or a
  hand-built call cannot resurrect a removed field, and cannot have it silently
  dropped from a revision the user meant.

## TUI

Read @TUI.zh-CN.md when editing any Goal display path.

Use pi-kit lifecycle bands, `renderShell: "self"`, empty tool calls, consistent
lowercase transcript action words, and complete width-wrapped settled bodies.
Commands and automatic lifecycle results use durable custom messages. Do not emit
both a tool result and a notification for one outcome. `/goal <request>` shows one
`[goal] requesting` row with the typed words and keeps the complete request body
out of the terminal transcript; checkpoint messages stay hidden. No hidden message may
claim that work already started.

Pi persists `display` with the entry, so a session replayed without this renderer
falls back to Pi's default custom-message rendering, which prints the whole body.
That residual case is accepted, and the send-time check does not cover it.

The passive below-editor footer is the explicit exception to transcript framing:
`Pursuing goal · 2h 25m` during actual work or authorized continuation; accurate
waiting, paused and blocked phrases otherwise. It owns no input.
Checker status is neutral. Never intercept global terminal input.

## Verification

Start changes with Given/When/Then scenarios and a failing regression. Use
@features/goal.feature and @tests/goal_simplified.mts for the unified contract;
@tests/goal_scheduling.mts and @tests/goal_store.mts protect concurrent mutations.

```bash
python3 -m pytest packages/goal/tests/ -q
pnpm exec tsc --noEmit -p packages/goal/tsconfig.tests.json
pnpm typecheck
pnpm --dir packages/goal pack --dry-run
uv run --no-project --with pyte python packages/goal/tests/goal_native_completion.py
uv run --no-project --with pyte python packages/goal/tests/goal_native_request_row.py
uv run --no-project --with pyte python packages/goal/tests/goal_native_revision.py
sh packages/goal/tests/goal_docker.sh
```

The Docker acceptance packs this tree, installs it into an isolated Pi that resolves to the
latest published version, and mounts no host credentials and no other extension.

Use isolated native CLI/TUI sessions. Decode terminal frames, not occurrences in
repaint bytes. Separate scripted-provider acceptance from real-model evidence.
For Docker changes/install verification, test packed artifacts with only Goal and
necessary dependencies installed. No host credentials or unrelated extensions.
After self-verification, get a fresh agent review for these complex state changes.
Mutate a repaired branch and require a regression failure, then restore exactly.
