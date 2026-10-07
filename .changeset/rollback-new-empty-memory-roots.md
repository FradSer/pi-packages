---
"pi-continual-learning": patch
---

Restore newly created empty Memory roots after a cancelled write with a non-recursive directory removal. Keep the original cancellation error instead of adding an EISDIR rollback failure, and preserve concurrent files.
