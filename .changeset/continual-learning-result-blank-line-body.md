---
"pi-continual-learning": patch
---

Fixed the expandable `[learning]` result dropping applied Memory bodies that
contain blank lines. A real applied record keeps a blank line after its
frontmatter and blank lines between the body, **Why** and **How to apply**
sections; the expansion parser split entries on blank lines, so such a record
collapsed into a frontmatter-only fragment (no body, dropped) plus filename-less
section fragments (also dropped). The result row then read `1 memory applied`
with nothing to expand, even though the message content on disk carried the full
body. Entries are now delimited by their parent-owned Memory filename line
instead of blank lines, so multi-section and multi-record bodies render
completely. Reported from debug log `batch_910b9f8d` (2026-11-12,
`project_pi_package_npm_publishing.md`): the receipt, the message `content`, and
the private-root file were all correct; only the terminal projection was wrong.

Fixed memory over-splitting and fragmentation:
1. Prevented `state.newMemoryCapHeld` leaking across pipelines on shared session
   state: `newMemoryCapHeld` was reset neither in `startConsolidationPipeline`
   nor in `spawnAsyncConsolidation`, causing subsequent applied pipelines in the
   same session to falsely inherit the `new-memory-cap-hold` routing marker and
   report held outcomes (reproduced in `batch_3049f80e`, where 3 files applied
   yet were tagged as cap-held).
2. Guided consolidator planners against splitting related findings across
   separate micro-files: when multiple observations belong to the same package,
   module, or workflow, planners consolidate them into a single cohesive entry
   or update an existing selected file instead of emitting multiple split files.
3. Updated selector guidance to select all relevant topic entries rather than
   excluding adjacent entries, allowing the planner to update and extend
   existing topic files instead of being forced into creating new files.
4. Added anti-accumulation rewrite guidance to stop rewrites expanding into
   session-narration logs with one-time error transcripts or run IDs.
