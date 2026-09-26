---
"@fradser/pi-kit": minor
"@fradser/pi-agent-teams": patch
---

Pi-kit never pre-truncates the content it derives, and every remaining bound is now either the row's own width-aware `fit` or an explicit limit that announces itself.

**pi-kit**

- A worker's tool activity showed only 40 characters of the command plus a literal ` ...`, even on a wide terminal, while streamed text or thinking activity showed its whole line. Progress snapshots now carry the tool's complete flattened command or query and the live widget row fits it to the terminal.
- `formatToolLifecycleDetails` dropped every detail line past the 50th with no marker, so an expanded row could hide evidence the user had just asked to read. Expanded bodies are complete by default.
- `detailLimit` now takes a number only: `"all"` was the same complete readback as the new default, so it is removed rather than left as dead vocabulary. Callers that passed it drop the argument.
- An explicit numeric `detailLimit` renders a `… N more detail lines` row instead of dropping lines silently, and `0` still suppresses the body instead of advertising an empty one.
- `fieldBlock` no longer clips a value at 2000 characters: the whole value survives. A package with a real content budget (prompt injection, memory index) applies and announces it where it owns it.
- `formatToolLifecycleDetails` no longer accepts a `maxLines` fallback bound, which no caller used.

**@fradser/pi-agent-teams**

- Coordination titles clipped a Work subject or task preview at 90 characters with no way to read the rest, and expanded bodies clipped a kickoff prompt at 2000 characters. Titles now carry the whole value and the kit row truncates them at the terminal width while expansion reveals every line, so the removed caps leave no text unreachable.