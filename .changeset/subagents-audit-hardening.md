---
"@fradser/pi-subagents": minor
---

Add an explicitly granted child-only `agent_message` capability for bounded intermediate messages to the direct parent session. Preserve exact input attribution and existing grants, render these messages separately from final results, and keep queued inputs and settlement unchanged.

Separate durable child history by the parent Pi session ID and project while sharing identity Memory and ordinary scratch. Reopening a parent restores only its own child history. Preserve existing project-only histories without importing, moving or deleting them; headless embeddings can supply a stable parentSessionId in runtime options.

Require a prompt at the intent startup boundary, preserve final RPC records without a trailing newline, and keep successor turn counts independent during reentrant close callbacks. Reject malformed result metadata and out-of-range report timestamps without corrupting authored text or Unicode diagnostic previews.

Give a new Pi process thirty seconds to load and confirm its initial prompt, idle readiness or fork setup. Keep running-resident input controls on their five-second acknowledgement deadline and preserve uncertainty on expiry without repeating input.

Protect private Memory, definitions, and legacy migration sources against hard links. Publish private replacement files atomically, give same-title Memory proposals distinct names even when their timestamps match, and reject proposals over the complete serialized UTF-8 budget before writing files.
