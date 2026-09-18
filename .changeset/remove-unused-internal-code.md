---
"@fradser/pi-agent-teams": patch
"pi-continual-learning": patch
"@fradser/pi-impeccable": patch
"pi-keyboard": patch
---

Remove unreachable legacy Agent control, unused internal helpers and constants,
and the unused keyboard HID encoder (hardware commands already use via-rgb).
Retain active entry points, shared public APIs, configuration compatibility,
and behavioral regression coverage. Remove superseded planning documents and
checks that only assert documentation wording or recreate implementation in tests.
