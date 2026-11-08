---
"pi-continual-learning": patch
---

Scope the built-in no-bulk-memory-deletion Bash rule to one shell segment. A
later `.memory` grep filter or search pattern in a compound command no longer
inherits an earlier unrelated `rm`, while deletions that name a Memory root in
their own segment stay blocked. Script one-liners with quoted semicolons and
`find`/`rsync` deletion forms keep their existing protection.
