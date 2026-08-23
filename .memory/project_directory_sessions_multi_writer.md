---
name: directory-sessions-multi-writer
description: directory-sessions has multiple writers with different ids; readers merge by pid and exclude their own process
type: project
---

The shared directory-session registry receives records from utils and keyboard writers. They may use different sessionId conventions for the same physical process.

## How to apply

Normalize untrusted registry records on read, merge records by owning pid, let the newest record win mutable scalars, and fill optional detail fields from sibling records. Preserve a valid startedAt instead of deriving it from glow records that lack the field. Exclude the current process by pid as well as session id. Sanitize free-text display fields and keep new writers aligned with the utils SessionInfo shape.

Reference implementation: mergeSessionsByPid and normalizeSessionRecord in packages/utils/extensions/sessions.ts.