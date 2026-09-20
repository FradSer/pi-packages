---
"pi-skill-router": patch
---

Parse the skill-collection registry once per session instead of on every user turn. Prompt routing read and re-parsed the registry JSON during `before_agent_start`, so the parse is now keyed on the file's own identity and invalidated by an application write or any change to the file. Measured: 0.34 ms to 0.002 ms per turn with two collections installed.