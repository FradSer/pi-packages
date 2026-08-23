---
"@fradser/pi-utils": patch
---

Make /continue always retry with the current model and configuration: remove error classification gating that turned stale persisted failures into permanent refusals even after switching models or fixing config, drop the redundant auth preflight, strip consecutive failed assistant messages from retried context while keeping tool-call/result pairs intact, route the continuation keyword through the registered /continue command, and remove the internal __continue command from the command menu.
