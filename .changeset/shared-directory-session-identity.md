---
"pi-keyboard": patch
"@fradser/pi-recap": patch
"@fradser/pi-utils": patch
---

Use one canonical, hashed directory-session identity across keyboard, recap, and utils. Verify registry ownership before reading or removing records, preserve per-command keyboard failures through the serial queue, pair recaps with the latest complete answer, and ignore pre-cancelled, auth-cancelled, or late provider responses.
