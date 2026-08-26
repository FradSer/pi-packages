---
"@fradser/pi-agent-teams": patch
"@fradser/pi-kit": patch
---

Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
