---
"@fradser/pi-tasks": patch
---

Fix defects exposed by task test auditing.

- Preserve complete UTF-8 prefixes when clipping context. A split leading byte previously produced a replacement character and exceeded the byte limit.
- Keep clipping output within budgets smaller than the truncation notice. The structured `clipped` flag reports truncation when the notice cannot fit.
- Declare `invalidated` in the tool output schema. Reopen results previously carried this field without declaring it.
- Name unfinished prerequisite ids when refusing to start a dependent task.

Strengthen tests so setup must establish the state being checked. Validate actual structured outputs across all four tools, restore tasks through the shipping session handler, and reject identity fields against otherwise valid parameter objects.

Use isolated agent directories and remove inherited holder bindings from test subprocesses. Mutation probes run in temporary source copies, not in the working directory.
