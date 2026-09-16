---
name: continue-recovery
description: Continue extension session recovery behavior
type: project
---

`packages/utils/extensions/continue.ts` retries directly when it can reuse the
selected session state. It sets `needsSessionReload` when another process has
written entries or the selected tree node requires reload before continuation.
Ordinary stale-session recovery has no separate user-action flag.
