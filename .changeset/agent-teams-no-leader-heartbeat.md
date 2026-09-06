---
"@fradser/pi-agent-teams": patch
---

Remove leader heartbeat and stall notices. Silence, spawn age, and usage stay as passive console telemetry in `/agent-teams` (roster "stalled" marker at `PI_TEAMMATE_STALL_SILENCE_MS`, default 5 minutes); the leader context is never interrupted by health prompts, and provider hangs surface only through the standard terminal close-path diagnostic. See `docs/adr/0002-no-leader-heartbeat-notices.md`.
