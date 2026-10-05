---
"@fradser/pi-tasks": patch
---

Report claimable work from one definition. The `list_tasks` filter and the reminder before settlement now read the task store's own `claimableTasks` predicate instead of keeping their own copies. A restored pending task that still names a departed holder is claimable, and the reminder used to omit it from the work it offered while `take_task` accepted it.

Name the restored-record classification as `resolveRecordKind` beside the persisted-file version, and repair the persistence row of the README module table.