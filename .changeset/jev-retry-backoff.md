---
"pi-continual-learning": patch
---

Wait a bounded 500 ms backoff before the existing single connection-only Jev
retry, and yield immediately to an abort during that wait. The retry count,
request bounds and per-request deadline are unchanged. A failed request group
already stops later request groups of the same review; a regression test now pins
that spending rule.
