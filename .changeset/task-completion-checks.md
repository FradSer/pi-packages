---
"@fradser/pi-tasks": minor
---

A completion is checked against the board's own facts before it is recorded.

**The scenario this exists for.** A model splits a large task into n tasks that may depend on each other, takes them in series or in parallel, then marks them complete. The board is the only thing that sees the whole sequence, and until now it checked almost nothing on the completion path: the dependency graph was enforced when *taking* a task and not at all when *completing* one, and any caller could close a task that had never been taken.

That let a model produce a board like this by bulk-marking four tasks complete:

```
t1 pending    depends=[]
t2 completed  depends=["t1"]      <- its dependency is not done
t3 pending    depends=["t1"]      <- never taken
t4 completed  depends=["t2"]
```

A completed task depending on an unfinished one is precisely the state the graph
exists to make impossible, and the board could not tell it apart from real work.

**The checks**, all of them facts the board already holds:

- **A dependency must be completed.** The refusal names the unfinished one, so the
  model can complete it and retry — which is also what makes a parallel batch
  recoverable: the dependents are refused, the finished ones stand.
- **A success must record a result.** A success is a judgement against the task's
  requirements; it carries the evidence for that judgement.
- **A task nobody worked on cannot be accepted.** A holder that *died* leaves a
  recovery hold behind, and that is what makes an unheld task acceptable again —
  the fallback path so dead work is not stranded. A task that was never taken has
  no attempt on the record, so accepting it is a bare assertion. Those two states
  were conflated; `test_an_unheld_task_accepts_fallback_acceptance` pinned the
  broad fallback while its own docstring described the narrow one, and its setup
  never built the dead-holder state it claimed to test.
- **A declared gate must be answered.** `verify` is a prompt, and a board that
  evaluates prompts runs agents, so the board does not run one. It demands the
  answer and records it: a completion of a gated task carries
  `verdict: "pass" | "fail"`, and the task keeps `completionVerdict` and the gate
  it answered, so a later reader can tell a gated completion from an unchecked
  one. The answer is still taken on trust — the board cannot know otherwise — but
  the omission becomes impossible.

**All four are opt-in** (`ALL_COMPLETION_CHECKS`, and one at a time), because a
coordinator that already verifies a submission by other means would otherwise be
refused for work it has already checked. `update_task` asks for all of them,
because that is the path a model drives.

**The other door, closed in the same change.** The invariant was reachable from
the reopen side too: nothing completes on an unfinished premise, but reopening a
*premise* left the conclusions standing on it. `status=pending` now pulls back
everything transitively standing on the reopened task — a completed dependent had
a conclusion withdrawn, one being worked on had an attempt invalidated — each
returned to pending under a recovery hold, naming what withdrew its premise, with
its evidence kept, its recorded gate verdict withdrawn, and its lease released.

**Reopen is unconditionally available.** Only two refusals remain and both are
definitional: no such task, or it is not completed. It was previously also refused
while a dependent was being worked on, and that rule was wrong twice over.
Reopening is the only way back from a completed task, so refusing it strands the
work for everyone who ever depended on it; and refusing it only sometimes gave one
operation two answers depending on who happened to be holding what at the time.
`test_reopening_is_refused_while_a_dependent_is_in_progress` pinned that rule and
now pins its replacement — the same reopen succeeding whether the dependent is
completed or in progress.

**And the marker path.** A completion submitted through an intent marker — the
file a spawned participant writes instead of calling a tool — is the same
completion, so it now carries the same checks and the same verdict. Without that,
every rule above was advisory to any participant willing to write a file.

One bug found on the way: `applySubmissionIntent` returns an `error` while
`completeTaskWithOutcome` returns a `reason`, so threading the options through
handed the object straight back and dropped the only sentence saying *why* a
submission was refused. A participant refused with nothing to act on.

**Verification.** `python3 -m pytest packages/tasks/tests/ -q` (76 passed) and
`pnpm typecheck`. Driven live on Pi 1.0.0 as well: a throwaway extension split a
task into four, took them out of order and in parallel, and tried every completion
shortcut — the board refused an early take on an unmet dependency, a success with
no result, a completion of a task nobody took, a gated completion with no verdict,
and one with `verdict: "fail"`, then accepted the same completion with
`verdict: "pass"` and recorded the gate. The persisted board held
`t2 pending` while nothing claimed it completed. A three-deep chain was then
completed and its premise reopened: both conclusions came back to pending naming
what withdrew them, their evidence intact, and the board held no completed task
depending on an unfinished one.
