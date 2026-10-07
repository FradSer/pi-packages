---
"@fradser/pi-kit": patch
---

Omit the separator when a lifecycle row has no subject.

A row renders `[tool] label · subject`, and the separator was part of the label, so a caller with no subject to name produced `[agent] listed · ` — a `·` advertising text nobody wrote. The head now stands alone in that case, exactly as it already did for a block subject with nothing authored, and `formatToolLifecycleTitle` follows the same rule.
