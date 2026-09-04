---
name: continue-recovery
description: /continue always retries directly with the current model/config — no error classification, no blocking gates; completed turns stay visible
type: project
---

## Why

Classification-based gating turned stale persisted errors into a permanent refusal: once a turn failed with an auth/quota/context/safety/malformed error, every later `/continue` re-read the old persisted error text and blocked with "fix before retrying" — even after the user switched models or fixed configuration. User directive (2026-08-22): `/continue` means "retry now with whatever is current"; switching model or config must take effect on the very next continuation. Also, automatic provider retries stack several failed assistant entries, so popping only one per marker leaked empty assistant messages into provider context.

## How to apply

- In `packages/utils/extensions/continue.ts`, there is no error classification, no blocking gate fields, no auth preflight (pi's own `prompt()` already validates model/auth with `checkAuth`). Only two outcomes:
  - Last message is an assistant with `stopReason === "stop"` -> visible user message ("Please continue execution based on ...").
  - Everything else (aborted/error/length/pending/toolUse/deferred stops, errored tool results) -> hidden marker direct retry via `sendMessage({ customType: "continue-extension" }, { triggerTurn: true })`.
- Empty branch (no previous request) is the only refusal: notify "there is no previous model request", never prompt the provider.
- The `context` hook strips each marker plus the whole contiguous run of trailing incomplete assistants (`while` pop on `stopReason !== "stop"`); it never pops past another message type, so an assistant tool-call message stays paired with its saved tool results.
- Never fork session history: keep the disk-tip rebase (`readDiskTipEntryId` + `ctx.switchSession(sessionFile, { withSession })`) so continuations extend the persisted tip linearly — user constraint: no sibling branches in pi history.
- Keep feature coverage in `packages/utils/features/continue.feature` and source assertions in `packages/utils/tests/test_continue_extension.py`.

## Related

[[project_continue_stale_session_rebase]]
[[project_pi_package_conventions]]
