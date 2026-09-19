---
"@fradser/pi-context": patch
"@fradser/pi-monitor": patch
"pi-matt-pocock": patch
"@fradser/pi-agent-teams": patch
---

Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.