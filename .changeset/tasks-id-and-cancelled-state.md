---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": patch
---

Give unfinished work an exit, and derive word-complete task ids.

**What changed**

- `update_task` accepts `status=cancelled` with a required `reason`. `blocked` means a blocker is in the way; abandoned work was recorded as blocked and counted as unfinished forever, so the settle reminder reported it at every settlement. A cancelled task keeps its record, reason and evidence, leaves the board, stops counting as unfinished or claimable, and is reopenable to `pending`. A cancelled prerequisite still blocks its dependents, because cancellation does not satisfy an edge.
- `reopenTask` brings a cancelled task back to `pending` and clears its reason. Completed or held dependents are withdrawn exactly as they are for a reopened completion.
- `taskIdFromSubject` truncates at a word boundary within the id limit and disambiguates duplicates with `-1`, `-2`, ... instead of cutting inside a word and starting at `-2`. The id is still minted once from the subject and stays the handle across a rename.
- Agent Teams reports the cancelled count in its task summary and labels cancelled rows.

Contract: `features/simplified-tasks.feature`, `features/work-domain.feature`.

**Verification**

- `tests/test_simplified_tasks.py` proves cancellation requires a reason, keeps the reason, stops claimable work, still blocks dependents, refuses a completed target, and reopens to pending.
- `tests/test_work_domain.py` proves word-boundary truncation and `-1`/`-2` suffixes.
- The tools suite and the Agent Teams consumer suite pass.