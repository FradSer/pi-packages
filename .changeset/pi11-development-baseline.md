---
"@fradser/pi-kit": patch
"@fradser/pi-subagents": patch
"@fradser/pi-tasks": patch
"@fradser/pi-agent-teams": patch
"@fradser/pi-monitor": patch
"@fradser/pi-impeccable": patch
"pi-matt-pocock": patch
"@fradser/pi-utils": patch
"pi-continual-learning": patch
---

Align development verification with Pi 1.1.0 and update compatibility documentation. Preserve host-provided wildcard peers and published runtime behavior. Monitor acceptance now selects the locked workspace CLI, isolates user state and retains native diagnostics; deterministic official E2E checks do not require a model.

Declare continual-learning’s host-provided TypeBox as a wildcard peer, retaining its TypeBox 1.3.27 development requirement in accordance with the Pi package guide.
