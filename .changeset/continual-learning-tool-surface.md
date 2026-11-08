---
"pi-continual-learning": patch
---

Centralize the tool surface without changing behavior.

`extensions/tool-surface.ts` now owns the four canonical tool names, worker loadouts, parent active-tool transitions, read/case budgets and the worker CLI allowlist. Existing tool definitions, commands, prompts and validation gates remain unchanged.
