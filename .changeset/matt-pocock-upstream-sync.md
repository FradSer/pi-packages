---
"pi-matt-pocock": patch
---

Sync the bundled procedures with `mattpocock/skills` at `49dd158d` (tag `v1.3.1`), adopting upstream content and typography, and classify the new upstream skill.

Content adopted: `grilling` now carries the design-tree, frontier and rounds model with the required recommendation, `pr` and `retro` adopt the upstream body template and retrospective categories, and `diagnosing-bugs` (prove a forced mutation landed), `implement` (fetch a passed ticket reference), `tdd` (name what each seam catches and misses), `teach` (workspace paths, varied quiz answer position), `setup-matt-pocock-skills` (create the tracker labels the repo lacks), `handoff` (resolve the temp directory), `wait-what` (`GLOSSARY-MAP.md`), `to-tickets` (native blocking edges) and `wayfinder` (wayfinder labels are the only labels, real cross-reference ids) carry their upstream changes.

Typography adopted: 19 procedures and 17 supporting reference files now use the upstream punctuation (em dashes become colons, commas, semicolons or parentheses, and `*italics*` becomes `_italics_`), so `wait-what` is byte-identical to upstream and only content differences remain elsewhere. Supporting references and assets are matched to their upstream counterparts by name because `upstream-selection.json` classifies `SKILL.md` files only, and UPSTREAM.md now records that rule. `pr` carries the `show-me` attribution that upstream keeps in its separate `CREDITS.md`. Local Pi policies stay: the required-recommendation question tool, the written-deliverable rule, and the harness integration lines.

`upstream-selection.json` records the reviewed commit `49dd158d`, the tag `v1.3.1` resolving to `24fe0ef7`, and excludes the new `chief-of-staff` skill as an experimental in-progress skill that needs recurring schedules and background subagent orchestration. `UPSTREAM.md` notes that the newest tag can predate the reviewed tree.

Two semantic guards now assert the local question policy (required recommendation, deadline adoption) and the written-deliverable rule in the delivered bundles, so a later sync cannot drop them silently.