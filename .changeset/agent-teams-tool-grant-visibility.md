---
"@fradser/pi-agent-teams": minor
---

Spawn surfaces now expose each teammate's effective tool allowlist: `teammate_spawn` records the granted tools in the roster before the first wake, the spawn result line and console detail name them, and a role derived inline without a `tools` field visibly shows its narrow capability-only grant. Leader guidance now requires matching definition tools to the assignment — file-inspecting work needs explicit `read`/`bash` — and prescribes shutdown-plus-respawn instead of steering when capabilities are missing. This prevents workers from burning turns discovering they cannot execute their kickoff.
