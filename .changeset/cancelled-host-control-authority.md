---
"@fradser/pi-subagents": patch
---

Bind hosted closure controls when the new exact incarnation is reserved, so a
cancelled startup wait remains explicitly stoppable before acknowledgement. Refuse
late confirmations that do not match the original reservation or conflict with a
successor's control owner. Check existing ownership before eager binding or
pinning, so synchronous reentrant starts cannot seize an already-owned successor,
even under the same host object. Preserve returned late control failure diagnostics on
only the originally pinned current incarnation after caller cancellation, without
guessing idle, reviving processes or changing automatic final-result delivery.
