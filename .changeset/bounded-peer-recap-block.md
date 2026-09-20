---
"@fradser/pi-utils": patch
---

Bound the injected peer-session recap as a whole. Per-field limits still let five peers with long goals, recaps, and file lists add up, so the block now stops adding peers beyond a 1,500-character ceiling, always keeps the most recent one, and reports how many were omitted to keep the recap bounded instead of growing with the number of sessions.