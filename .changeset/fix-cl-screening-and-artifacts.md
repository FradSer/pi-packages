---
"pi-continual-learning": patch
---

Stop spending learning calls on evidence that is not evidence, and make the results inspectable.

Harness activity is now decided by Harness-owned transcript evidence (guardrail event entries, Harness guidance delivery, and the notes Harness attaches to tool results) instead of matching words such as `policy`, `harness`, or `blocked` in repository text, so reading a harness file no longer starts a harness planner. A manual consolidation honors the selector's reviewed verdict unless user-stated evidence or real Harness activity floors it: a verified tool recovery alone no longer starts a Memory planner the selector declined after reading the same slice. Completed Memory runs keep their run directory (task, plan, receipts, manifest, snapshot) for inspection, and a sensitive snapshot refusal now names the learned surface to clean without echoing the matched bytes. Planner dossiers record Harness events from that same Harness-owned evidence instead of transcript fragments that merely mention the harness.
