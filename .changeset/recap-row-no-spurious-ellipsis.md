---
"@fradser/pi-recap": patch
---

A complete recap no longer ends in a truncation marker it never earned.

pi-tui's `Markdown` pads every rendered line to the width it was asked for, and the recap widget fed those padded lines straight into the kit row renderer. The composed row was therefore always wider than the terminal by the row's leading space plus that padding, so the row fitter clipped the invisible padding and appended its `...` to text that was fully present: a one-line recap showed its whole summary followed by a stray marker at the right edge, and a wrapped wide-character recap marked rows that had dropped nothing, sometimes after a run of padding spaces.

**@fradser/pi-recap**

- Markdown padding is trimmed before a row is composed, and the content width now subtracts the widget row's leading space from the prefix budget, so a full-width recap line fits exactly and keeps its real text.
- The widget no longer calls `wrapTextWithAnsi` for its side effect: the discarded result was dead weight left over from the pre-Markdown renderer.