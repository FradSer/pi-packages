---
"@fradser/pi-kit": minor
---

Add `verbatimSubject`, `subjectBlock`, and `bgToken` to the lifecycle spec so user-authored text renders raw on the band: one row per authored line, wrapping instead of merging, no `@name` recoloring, no expand hint for text that is already visible, an optional block layout (head row, blank band row, then the authored lines), and an opt-in band tint such as `userMessageBg`. Hidden details still expand and keep their hint.