---
"pi-skill-router": minor
---

Route to externally hosted skill collections: clone GitHub skill repositories via the `/skill-router` menu, wrap selected skills as hidden prefixed leaves behind generated gateways under `~/.pi/agent/skill-router/`, expose them through `resources_discover`, and keep deterministic `before_agent_start` suggestions. The package ships no skill content and routed collections are never npm packages.
