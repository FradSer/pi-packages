---
"@fradser/pi-goal": patch
---

Show one `[goal] requesting` row for `/goal <request>`. The row carries the typed words under it, and the complete request body stays out of the terminal transcript. The request no longer leaves the transcript silent until the model creates or revises the goal. The label stays distinct from the `[goal] started` row that reports the created goal.

The below-editor row for a running check is one neutral activity line. It no longer carries a redundant `[goal] checking...` heading above that line, because the position already belongs to the running goal.
