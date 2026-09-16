---
"@fradser/pi-agent-teams": patch
---

Render `agent`, `work`, and `agent_event` transcript rows for people instead of
models. A started Agent now shows its name, role, the full kickoff text, granted
tools, and model; inspect shows the live status and current activity; Work and
message rows lead with the Work subject and show the message that was sent.
Session, Work, and assignment handles stay in model-facing tool content and are
scrubbed from every rendered line (a Work id becomes its subject, a session route
becomes `@name`), while text a person wrote themselves is preserved verbatim.
