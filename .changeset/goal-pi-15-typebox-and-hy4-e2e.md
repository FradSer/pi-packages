---
"@fradser/pi-goal": patch
"@fradser/pi-kit": patch
---

Use TypeBox directly for Goal tool schemas and declare the TypeBox peer in Goal
and pi-kit. Pi 1.5.0 removed the `Type` re-export from `@earendil-works/pi-ai`;
the isolated Docker acceptance now loads the packed Goal package on Pi 1.5.0.
Add an explicit opt-in Docker E2E for `hunyuan-eval/hy4-dev` that keeps the real
Magpie credential on the host and records one native Goal lifecycle.

Independent review fixes bound delegated-result waits to their Goal, recognize
terminal monitor/subagent reports, stop provider errors that skip the settle
boundary, and stop a hung child after three quiet turns.
