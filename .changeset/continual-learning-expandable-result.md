---
"pi-continual-learning": patch
---

Make the final `[learning]` outcome row expandable when the run applied safe
Memory entries. Expanding renders each entry's description and body as Markdown;
frontmatter, filenames and receipt metadata (usage, cost, source, calls,
attempts, diagnostics) are not displayed. Private and credential-shaped entries
are never shown. A run with no applied safe Memory keeps the previous one-line,
unexpandable result.

The generated bodies travel inside the custom message's `content` after the
one-line summary, because Pi persists only a fixed set of custom-message
fields. The stored receipt and the model-facing `details` are unchanged.
