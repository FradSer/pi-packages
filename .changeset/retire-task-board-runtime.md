---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": minor
"@fradser/pi-subagents": minor
"@fradser/pi-kit": minor
---

Retire the task board vocabulary and the `board.json` persistence fallback. Load and write only `tasks.json`. Remove the retired path and resolver exports. Preserve old files without automatic migration or deletion.

Rename shared assignment kind `board` to `task`, use task-prefixed attempt ids, and rename worker binding to `PI_TEAMMATE_TASKS_FILE`. Use task names in coordination callbacks, notices, and console navigation. Update all contributing packages together and restart existing children before using the new bindings.

This is a breaking library and worker-protocol change for these pre-1.0 packages. Task file format version 2, completion evidence, dependency rules, ownership, and recovery remain unchanged.
