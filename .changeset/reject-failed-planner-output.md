---
"@fradser/pi-kit": patch
"pi-continual-learning": patch
---

Reject failed and aborted assistant output even when the worker CLI exits successfully. Preserve cancellation until a successful reply, stop learning before repair or application, and report unavailable usage and cost without exposing provider error text.
