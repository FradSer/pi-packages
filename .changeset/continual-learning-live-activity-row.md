---
"pi-continual-learning": patch
---

Show one live activity row above the editor while a learning run is active,
using the same shared pi-kit spinner widget language as subagents. The row
names the run without receipt metadata and is cleared on completion, failure,
cancellation and session reload. Headless (`--print`/RPC) runs stay silent.
Transcript rows (started and final result) are unchanged.
