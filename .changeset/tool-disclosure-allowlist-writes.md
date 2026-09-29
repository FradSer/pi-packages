---
"@fradser/pi-kit": patch
"pi-matt-pocock": patch
"@fradser/pi-monitor": patch
"pi-utils": patch
"@fradser/pi-agent-teams": patch
---

Stop `setActiveTools` toggle writes from deactivating tools the harness has not published yet.

`setActiveTools` is an allowlist write: the caller passes the complete set the
model may call, and anything absent is deactivated for the rest of the session.
Every extension that toggled a tool read the active-tool snapshot, adjusted it,
and wrote it back, so a snapshot that had not yet reported an extension's own
registrations silently erased them. `pi-matt-pocock` then kept delivering routing
prompts that name `matt_pocock_workflow`, instructing the model to call a tool it
could not see.

`@fradser/pi-kit` gains `setOwnedTools`, which re-asserts the extension's own
tools instead of trusting the snapshot, and all five call sites now use it:
`pi-matt-pocock`, `pi-monitor`, `pi-utils` sessions and worktree-session, and
`@fradser/pi-agent-teams`' worker disclosure. Repeated identical writes are now
idempotent rather than accumulating a duplicate entry.
