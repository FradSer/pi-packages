---
"@fradser/pi-subagents": patch
---

Name the roster in the `agent_list` row only when the page hides something.

The collapsed row read `[agent] listed · @children · N of M`. `@` is the prefix of a real child's name, so the roster read as a child called "children" on a row where every other subject is one agent; and `4 of 4` answered a question the absence of a count already answers. The row now reads `[agent] listed`, and `[agent] listed · 3 of 9` only when the page omitted entries — the one fact a collapsed page cannot state any other way. Expansion still shows the remaining count and the next offset.
