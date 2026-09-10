---
"@fradser/pi-agent-teams": patch
---

Fix agent presence and work control to use current-session state instead of reporting a fabricated idle result. Deliver leader direction through native priority steering that also starts idle execution, and isolate completion reports by assignment so an earlier PASS cannot close reopened work. Align first-delegation guidance, terminal-report rejection, and transport outcome wording with these contracts.
