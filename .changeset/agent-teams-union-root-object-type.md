---
"@fradser/pi-agent-teams": patch
---

Declare `type: "object"` on the union-root coordination tool schemas (`agent`, `work`, worker `work`). Google's GenerateContent API rejects a tool whose `parameters` carries `properties` without an object type (`parameters.properties: only allowed for OBJECT type`), so every Gemini-routed request that included those tools failed with a 400; OpenAI and Anthropic routes tolerated the omission.