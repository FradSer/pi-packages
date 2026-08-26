---
"@fradser/pi-agent-teams": patch
---

The leader's send_message no longer rejects a stray `status` field with "status is reserved for worker reports to=leader". The shared message schema exposes `status` to leaders too, and leader models occasionally copy it from worker report patterns — which hard-failed the call and blocked teammate delivery (observed live in hud-playground). A stray status on a leader-sent message is now ignored with a one-line corrective note appended to the tool result, and the leader tool description no longer mentions `status` at all. Worker-side semantics are unchanged: status is still honored only for reports addressed to "leader".
