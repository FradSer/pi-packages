---
"@fradser/pi-utils": patch
---

Preserve the selected session-tree node when continuing: /continue reloads the same session only when the disk tip is unknown to the active session, while entries written by another process are still inherited before retrying.
