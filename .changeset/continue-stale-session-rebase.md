---
"@fradser/pi-utils": patch
---

Continue from the latest session history instead of forking a sibling branch: /continue and the continuation keyword now compare the active leaf with the session file on disk and reload the same session when the view lags, so continued turns fully inherit parallel writers' entries.
