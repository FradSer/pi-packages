---
"@fradser/pi-kit": minor
---

`directorySessionsDir` resolves the shared directory-sessions registry directory from `PI_DIRECTORY_SESSIONS_DIR`, then `PI_CODING_AGENT_DIR` / `PI_AGENT_DIR`, then `~/.pi/agent`.

**@fradser/pi-kit**

- Callers had to spell the registry path themselves, and a package that hardcoded the home directory kept updating the user's real registry while the rest of the session ran against a sandboxed agent directory — one feature's state silently split in two. `directorySessionsDir` is that decision in one place, and `open-deskos` already resolved it independently.
- Consumers to migrate onto it: `keyboard` (`src/global-sessions.ts`), `utils` (`extensions/sessions.ts`), and `open-deskos` (`src/discovery.ts`, which keeps its existing precedence). `recap` now uses it.
