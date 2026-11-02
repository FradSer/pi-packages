---
"@fradser/pi-goal": patch
---

Fix completion checks failing with `Model "…" not found` when the session model comes from a provider an extension registers, such as magpie.

The check runs in a fresh child with `-ne`, so extension-registered providers and virtual routers do not exist there. Naming one made Pi exit before the check could start, and every completion request then paused the goal instead of being judged. Those models are now skipped: the configured or session model is used when the child can resolve it, otherwise the child receives no model and Pi selects one from its own catalog.