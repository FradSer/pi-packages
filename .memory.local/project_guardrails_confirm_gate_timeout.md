---
name: guardrails-confirm-gate-timeout
description: pi-continual-learning guardrails confirm gates fail closed after a bounded 60s select timeout — never let the gate hang the agent loop
type: project
---

## Why

The guardrails `tool_call` confirm gate blocks the entire agent loop while its `ctx.ui.select` waits for "Allow once"/"Block". An unattended session (user walked away, RPC client not answering) hung indefinitely. pi dialogs natively support `{ timeout }`: an expired `select()` resolves `undefined`, which maps cleanly onto the gate's existing fail-closed semantics.

## How to apply

- The confirm dialog passes `{ timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS }` (60s, module-private constant in `packages/pi-continual-learning/extensions/guardrails.ts`); pi renders a live countdown.
- Timeout and explicit Block are both fail-closed but the block reason distinguishes them: "(blocked: confirmation timed out)" vs "(blocked by user choice)". Keep that distinction — diagnostics depend on it.
- Do not replace the timeout with per-policy configuration or a `{ signal }` unless a real consumer appears; fail-closed-on-timeout is the settled behavior.
- BDD coverage lives in `features/guardrails.feature` ("An unanswered confirm dialog fails closed after a bounded wait") and S3 of `tests/test_guardrails_integration.py` (`dialogBounded` + `timeoutFailsClosed` assertions).

## Related

[[pi-package-conventions]] [[no-custom-interaction-tools]]
