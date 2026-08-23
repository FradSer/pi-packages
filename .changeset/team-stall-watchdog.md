---
"@fradser/pi-agent-teams": minor
---

Add an output-silence heartbeat for resident teammates. A teammate wedged mid-turn (for example, blocked forever in a provider request) never accumulates assistant turns and produces no RPC output, so nothing could alert anyone while the roster showed "working" indefinitely. The harness poll now tracks `lastOutputAt`: after 30 minutes without any output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) the leader receives one actionable notice per silence episode naming the teammate and its recovery options. The notice is the last automatic action — continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any stream activity or prompt delivery re-arms the watchdog. Steering a silent working teammate now warns that delivery is uncertain instead of claiming success, and the widget, console roster, and detail views show how long a working teammate has been silent.
