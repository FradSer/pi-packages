---
"@fradser/pi-tasks": patch
"@fradser/pi-agent-teams": patch
---

Classify automatically generated direct-input records as execution history. Keep failures and results readable without treating them as actionable task reminders or autonomous claim candidates. Explicit tasks retain their dependency and recovery checks.

Restore earlier generated UUID work records as execution history when no explicit record classification exists. This read-side classification preserves status, evidence, and recovery holds. It does not mark failed attempts completed or alter user files directly.
