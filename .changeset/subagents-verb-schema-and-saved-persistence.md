---
"@fradser/pi-subagents": minor
---

Name the resident verbs apart, and let a working child be steered.
`agent action=prompt` becomes `agent action=send`, and the new
`agent action=interrupt` steers a turn already in flight — the one case `send`
refuses — without opening a new turn or suppressing that turn's settled result.
The schema stays one flat object: per-action requirements remain the handler's
job, and the refusals that carry them name what is missing.

A saved definition is the record of its own persistence: a start that omits
`persistent` reuses that Agent's private session and Memory instead of silently
running as a Temporary Agent, `persistent: false` is the explicit opt-out, and
deriving persistence never writes a definition. The receipt names which of the two
supplied it.

The grantable built-in tool universe gained a drift check against Pi's own
canonical set, and the `tools` parameter now advertises that universe where the
model reads it.