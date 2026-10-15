---
"@fradser/pi-goal": patch
"@fradser/pi-agent-teams": patch
"@fradser/pi-utils": patch
---

Move the development Pi core cohort to 1.2.0 and stay type-correct on it. `before_agent_start` handlers in the goal runtime, Agent Teams and utils now test for the prompt instead of reading it directly, so they compile against both the older event shape and the current union Pi discriminates by run kind.
