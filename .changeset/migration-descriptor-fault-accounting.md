---
"@fradser/pi-subagents": patch
---

Preserve the first migration write/fsync failure when descriptor closure also
fails. Report close uncertainty separately without retrying recycled descriptors,
and retain/disclose exclusively created destinations whose inode could not be
verified, while continuing rollback of known invocation-owned files.
