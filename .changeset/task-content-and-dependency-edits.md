---
"@fradser/pi-tasks": minor
---

Simplify task rows around the task name, detailed body, dependencies, and status. Remove holder rows from the transcript. Keep runtime ownership in structured results and persisted data.

Allow `update_task` to replace the subject and dependency list without changing the task id. Validate unknown ids, self-dependencies, dependency cycles, and the dependency count before recording changes. Refuse unfinished prerequisites on in-progress or completed tasks. Require separate calls for content edits and status changes.

Return summaries from `list_tasks`. Keep full descriptions, completion gates, evidence, and gate verdicts available through `get_task`. Preserve completion checks and bounded continuation of unfinished work.
