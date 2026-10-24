# RED evidence for the goal audit

Each confirmed defect was reintroduced into the real tree, the matching regression was run,
and the file was restored byte-for-byte. Fingerprint `8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095`
(SHA256 over a sorted listing of `packages/goal/src/*.ts` as SHA256, two spaces, path, newline) was
recorded before and after the runs and is identical, so the frozen candidate was restored completely.

Method correction: an earlier attempt mutated a temporary copy and pointed the regression at the repository
tests. Those tests read `PACKAGE`/`REPO` from their own file location, so a temporary copy is invisible to them
and a mutation there cannot reproduce RED. That earlier claim of mutation coverage was unsound and is withdrawn.
The runs below mutate the tracked file in place and restore it in a `finally` block verified by content
comparison.

## RED 1 — dead `autoSelectSingleGoal` setting

Mutation: `src/settings.ts`, `autoSelectSingleGoal?: boolean;` re-added after `disableCheck`.

```
AssertionError: settings.ts declares autoSelectSingleGoal but no runtime module reads it
```

## RED 2 — dead `thinkingLevel` setting

Mutation: `src/settings.ts`, `thinkingLevel?: string;` re-added after `model`.

```
AssertionError: settings.ts declares thinkingLevel but no runtime module reads it
```

## RED 3 — ghost `taskIndex` import

Mutation: `tests/goal_store.mts`, `import { taskIndex } from "../src/record.ts";` re-added.

```
AssertionError: unresolved test imports: goal_store.mts: record.taskIndex
```

## RED 4 — load-bearing claim line removed

Mutation: `tests/goal_scheduling.mts`, the claim and its assertion removed again.

```
AssertionError: goal_scheduling.mts stderr:
```

## RED 5 — the autonomous run-level no-work stop (2026-10-19)

Two new contract scenarios and one new native probe pin the replacement of the run-level stop with
the change window. The mutation is the pre-change `src`, kept aside with
`git stash push -- packages/goal/src/scheduler.ts packages/goal/src/core.ts packages/goal/src/events.ts`
and restored with `git stash pop`.

Harness, `node --import tsx packages/goal/tests/goal_simplified.mts`:

```
FAIL Given repeated identical output When each run settles Then count it in the change window: identical output no longer stops the loop at once

false !== true
FAIL Given a successful turn with no tools When it settles Then spend the change window instead of waiting: an answer does not end the goal

false !== true
```

The other 56 scenarios stayed `ok` under the mutation.

Native, `uv run --no-project --with pyte python packages/goal/tests/goal_native_answer_continuation.py`
on a real Pi 1.3.0 CLI, real Goal extension, scripted provider, disposable project and agent
directory. The composed screen reproduced the reported stall:

```
Native fixture turn finished.
Native fixture turn finished.
[goal] waiting
No effective work was recorded. Use /goal resume to continue.
Goal waiting · 0m
```

and `pursuing(agent, 2)` was never reached, so the probe failed. With the replacement in place the
same probe passes: two answering runs spend two of the window's three runs, the loop reaches real
work, neither `[goal] waiting` nor the no-effective-work reason is painted, and the footer reads
`Pursuing`.

Restore check for this entry: `git stash pop` reported no conflict, `grep -n performedWork
packages/goal/src/*.ts` printed nothing, and the package gate over the restored tree passed. The
fingerprint block below belongs to the earlier audit and was not recomputed here.

## RED 6 — progress is novelty, not `edit`/`write` (2026-10-19)

Reproduced from a real goal, not from a hunch. The RayNeo HUD goal
(`goal_mvf0n32u_ak41pz`, thread `01a14387-70c4-71e6-92c0-4208b31c9227`) paused itself at
2026-10-19T12:02:43Z with `3 consecutive runs changed nothing observable. Use /goal resume to
continue.` after 17 authorized runs and 117,378,045 tokens. Replaying its session JSONL by run
(`pi-goal-checkpoint` to the next checkpoint) shows the three runs that filled the window were
receipt-heavy and edit-free: `bash` x12 + `read` x1, then a run with no tool receipts at all, then
`bash` x5. The two runs before them each contained one `edit` and reset the window, so the goal had
been surviving on the runs that happened to touch a file. A verification stretch — run the gates, read
the output, run them again — is work by any reading, and the window counted it as nothing.

RED for the replacement, with the committed `src` in place
(`git stash push -- packages/goal/src/{scheduler,core,events,settings,prompt}.ts`, then restored with
`git stash pop`): `node --import tsx packages/goal/tests/goal_simplified.mts` reports 5 failures out of
58 scenarios.

```
FAIL Given novel reads When each run settles Then keep continuing: read-only run 3 stays inside the window

false !== true
FAIL Given a successful turn with no tools When it settles Then spend the change window instead of waiting: an answer does not end the goal
FAIL Given repeated identical output When each run settles Then count it in the change window: two repeated receipts are inside the window
FAIL Given a reworded objective between repeated reads When the window fills Then stop: The input did not match the regular expression /3 consecutive runs produced nothing new/
FAIL Given a repeated edit after each objective revision When the window fills Then stop: The input did not match the regular expression /produced nothing new/
```

The other 53 scenarios stayed `ok` under the mutation. Restore check: `git stash pop` reported no
conflict, `grep -c NO_NEW_WORK_RUN_LIMIT` finds the replacement in `settings.ts`, `scheduler.ts` and
`prompt.ts`, and the package gate over the restored tree passed.

## Restoration

```
fingerprint before: 8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095
fingerprint after:  8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095
RESTORED_IDENTICAL True
```
