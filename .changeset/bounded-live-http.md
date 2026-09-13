---
"@fradser/pi-impeccable": patch
---

Limit live JSON request bodies to 1 MiB before parsing or applying events. Return an actionable HTTP 413 response for oversized bodies and discard interrupted uploads.
