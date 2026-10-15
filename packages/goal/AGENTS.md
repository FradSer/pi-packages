# Goal Runtime Package Guidelines

Applies to `packages/goal/` (`@fradser/pi-goal`). User instructions take precedence.

## Runtime boundaries

A Goal is one thread-scoped objective and one completion condition. Do not add a
Task tree, progress fraction, saved next-action workflow, dedicated research agent,
independent user history, or Goal archive. Use ordinary tools for investigation.

- `store.ts` is the sole record writer. One atomic record holds the objective,
  completion conditions, usage and scheduler state. Mutation checks and final
  release occur under the same exclusive lock. Preserve existing legacy files.
- Only the thread's own focus entry restores its goal. A boundary drops queued
  continuation, live checks and revision activation. Restore is not authorization.
- A timer, settled turn or queued message is an opportunity, never authorization.
  Arm and claim separately; recheck identity, owner, generation, phase, dispatch
  and budget. Accept a checkpoint once. Never replay unknown delivery.
- Continue only after successful effective work and without pending user input.
  Repeated identical tool receipts and pending monitors cannot sustain the loop.
  Unrelated background activity is not progress. Empty or failed work waits; only
  the user pauses. Resume preserves lifetime usage and continuation count.
- A recurring blocker requires three consecutive model turns. The same-turn
  report counts once; effective work, changed requirements and restore reset it.
- Only an explicit completion request runs one fresh tool-less completion check.
  No inspecting reviewer and no shell grant. Pass the complete objective and
  conditions; do not approve a truncated prefix. Runtime observations have thread,
  call, outcome and requirement-boundary provenance. Escape every untrusted payload.
- A final marker decides MET/NOT MET. Missing markers, errors, cancellation and
  outdated results are distinct and never complete the Goal. Refusals do not pause.
- Count completion-check usage, including cancelled/superseded results for the same
  open Goal, against the lifetime budget. Budget is not completion.
- `/goal <text>` queues a request, preserving the old record until a complete
  merged revision lands. Activation needs matching accepted delivery, not void
  send success. Completion or clear releases current runtime state without archive.

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
waiting, paused, blocked and budget-limited phrases otherwise. It owns no input.
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
