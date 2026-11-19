---
"@fradser/pi-agent-teams": major
---

Remove the task plugin dependency and its leader task tools. Work Items now use an internal task domain; spawned teammates keep their own claim/submit tool. Installations no longer load or register `create_task`, `get_task`, `list_tasks`, or `update_task`.
