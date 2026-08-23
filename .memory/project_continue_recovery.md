---
name: continue-recovery
description: /continue retries directly with the current model/config — incomplete or failed turns resume silently, completed turns get a visible continuation request
type: project
---

## Why

`packages/utils/extensions/continue.ts` never re-classifies stale failures into permanent refusals: continuation always retries directly with the current model and configuration. A transient API error (`stopReason: "error"`), truncation (`stopReason: "length"`), aborted/pending/toolUse/deferred stops, and failed tool results all resolve to a silent direct retry; only ordinary completed assistant responses produce a visible continuation request.

## How to apply

- Evaluate continuation against the active session branch — there is no error classification and no blocking gates.
- Incomplete or failed turns retry silently from the current leaf; the request always runs on the current model/config, so switching either takes effect on the very next `/continue`.
- When another process appended to the same session file, unseen entries are inherited before continuing (`needsSessionReload`).
- A leaf selected through session-tree navigation stays authoritative even if the append-only session file still holds a failed abandoned branch.
- Keep feature coverage in `packages/utils/features/continue.feature` and source assertions in `tests/test_continue_extension.py`.

## Related

[[project_pi_package_conventions]]
[[project_continue_stale_session_rebase]]
