---
"@fradser/pi-kit": minor
"@fradser/pi-agent-teams": patch
"@fradser/pi-utils": patch
"@fradser/pi-context": patch
"@fradser/pi-monitor": patch
"@fradser/pi-impeccable": patch
"pi-matt-pocock": patch
"pi-continual-learning": patch
---

Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
