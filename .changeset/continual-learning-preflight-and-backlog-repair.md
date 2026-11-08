---
"pi-continual-learning": minor
---

Report preflight failures accurately and keep legacy backlog rows from blocking replay.

A sensitive-material guard on existing Memory bodies no longer stages the whole corpus into the history WAL; a no-change run writes no history record. Zero-worker receipts name the `preflight` phase and say `no model calls` only when no worker was started, while failed workers with unknown usage still report unavailable amounts. Old `auto-memory-off` backlog rows are quarantined and malformed-row counting is scoped, so unrelated historical rows no longer disable replay binding. The shared credential guard now distinguishes `Auth:` mode labels and bracketed placeholders from real secrets, refuses `*_WEB_KEY` assignments, and keeps parsed object members strict in both the TypeScript and Python detectors. Started learning rows name the real current-task topic from the last user entry instead of a generic placeholder.
