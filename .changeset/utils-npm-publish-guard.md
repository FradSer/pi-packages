---
"@fradser/pi-utils": minor
---

Block package publish and npm credential commands (`publish`, `login`/`adduser`/`logout`, `token create/revoke/delete`) from the agent's non-interactive bash tool. These flows cannot complete there — 2FA web-auth exits immediately with EOTP and dead tokens surface as masked 404 PUT failures — so the guard blocks the call and returns corrective steering that routes the interactive step to the user's own terminal and the `npm-package-first-release` skill procedure.
