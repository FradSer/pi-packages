---
"@fradser/pi-agent-teams": minor
"@fradser/pi-kit": minor
---

Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.
