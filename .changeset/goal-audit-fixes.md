---
"@fradser/pi-goal": patch
---

Remove dead code and comments that describe retired behaviour: the duplicate goal reader, the legacy `readPrompt` name, the fabricated `activePath` write, the unread `currentTurnSeq` and `focusedId` accessors, and three verdict fields that are never set or read. De-export helpers with no external reader; they stay in the module. Correct the comments that still described an append-only ledger, a prose file as the objective, and a refusal count.

Add tests for the delivery-failure stop and for the timer delivery route. Replace the stale `goal_native_supersede.py`, which failed while asserting removed archive, ledger and research behaviour, with `goal_native_revision.py`: it drives a real Pi TUI, and asserts that one `/goal <request>` revises the open goal in place, keeps the earlier requirement inside the objective, pursues again, and writes no archive.

Every harness that records observations now verifies each scenario it observed against every `features/*.feature` file: the scenario must exist in some file, with the same predicates in the same order, and a recording harness that wrote nothing fails. A recorded scenario can no longer drift, and a recording harness cannot lose its contract entry, without failing the suite; clause-only scenarios stay outside that check.
