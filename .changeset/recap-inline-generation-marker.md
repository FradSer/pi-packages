---
"@fradser/pi-recap": patch
"@fradser/pi-kit": patch
---

Replace the recap line with a single identity-only `Recapping...` activity row while a recap is generating instead of stacking the marker above a stale `✦ Recap:` line, and let pi-kit live activity widgets omit the `· <activity>` suffix when no fallback activity is configured.