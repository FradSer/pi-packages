---
name: continue-recovery
description: /continue directly resumes incomplete model turns without adding continuation text to context while completed turns remain visible
type: project
---

## Why

A model/API outage can finish an assistant message with `stopReason: "error"`, which the old `/continue` logic treated like a normal completed response. Truncated responses (`stopReason: "length"`) also need resume semantics rather than a visible follow-up prompt.

## How to apply

- In `packages/utils/extensions/continue.ts`, classify assistant `aborted`, `error`, `length`, `pending`, `toolUse`, and `deferred` stops, plus failed tool results.
- Treat context overflow, authentication, quota/billing, malformed requests, and safety/content blocks as user-action cases rather than blindly retrying them.
- Preserve up to 300 characters of transient `errorMessage` when the provider supplies it; still recover when no error text is available.
- Tell the model to inspect current state and avoid repeating completed work. For incomplete turns, use a hidden continuation marker only to trigger the request, then strip that marker and the failed assistant message from the provider context. Keep ordinary completed assistant responses visible so `/continue` still advances recommendations.
- The direct path uses a `context` hook to remove the hidden marker before provider serialization; the provider must never receive the marker or continuation prose as a user message.
- Keep feature coverage in `packages/utils/features/continue.feature` and source assertions in `packages/utils/tests/test_continue_extension.py`.

## Related

[[project_pi_package_conventions]]
