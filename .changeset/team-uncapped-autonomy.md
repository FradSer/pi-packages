---
"@fradser/pi-agent-teams": minor
---

Adopt full teammate autonomy as the package constitution: the harness detects and notifies, the leader model decides — no configuration may automatically terminate a working teammate. Remove the per-wake-up turn budget (the former 100-assistant-turn ceiling that silently killed long sequences) and do not ship any duration-based auto-reclaim. Turn counts and silence durations remain visible as telemetry and heartbeat signals; the stall notice is informational and names the recovery options (keep waiting, steer again, shut down, or respawn a successor whose prompt composes context from the original kickoff, mailbox reports, board claims, and the console detail transcript). Leader guidance gains a "recover, never punish" section teaching this workflow.
