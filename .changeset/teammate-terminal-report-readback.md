---
"@fradser/pi-agent-teams": patch
"@fradser/pi-kit": patch
---

Return a teammate's recorded terminal report in a pi-kit lifecycle event so the leader never needs to force a duplicate resend, and extend leader guidance against resend steers and task_list polling.

Allow lifecycle renderers to explicitly preserve every expanded detail line for user-requested readbacks while retaining the default 50-line bound.
