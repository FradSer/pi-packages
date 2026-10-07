---
"@fradser/pi-subagents": patch
---

State what a child can be given, in the contract a caller reads before spending a call.

Three facts about starting a child lived only in the refusal of a real call.

An optional `identity` carried `minLength: 1` and a name pattern from the shared string schema, so an empty value was rejected before the extension ran. The extension already read that value as absence: it trims the field and tests it for truth, so an empty identity never reached the identity-not-found path. A caller that took the temporary-role branch of the description was refused by a rule the code did not have. The field is now declared without either constraint, a blank value is normalized to absence, and the description says to omit the field for a temporary role.

The `tools` description said the list was minimal and narrowed a saved grant, and never named a single id a child accepts. The grantable set is fixed — `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`, `powershell`, `agent_memory` — and a project-extension or MCP tool is not in it, because a child runs a bare pi process. Both facts are now in the description.

An `agent_list` page with no entries reported the count and nothing else. A caller with no saved identity had to find the layout on disk, and the first path it reaches is the user scope under the agent home. The notice now names the project-local path, `.pi/agents/<name>/agent.md`, and states that a temporary role needs no file at all.

Still missing, deliberately: an `agent_save` tool. Creating a saved identity in-session needs its own decisions about scope, naming, and overwrite, and inventing them here would pre-empt that design.