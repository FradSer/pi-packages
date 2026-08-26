---
"@fradser/pi-agent-teams": patch
---

Clarify message routing truth: active control-stream writes render as `steered`, inbox/outbox and wake-up paths render as `queued`, and neither outcome implies recipient processing. Stall diagnostics now render independently as teammate health events instead of message suffixes.
