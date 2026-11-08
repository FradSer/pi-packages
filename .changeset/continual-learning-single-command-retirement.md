---
"pi-continual-learning": minor
---

Converge the user-facing learning surface on a single `/learning` command and
one zero-argument `learn` tool. The `/learning` Harness menu option now opens
the guarded authoring procedure directly through the same parent-owned bridge
as the tool, instead of looking up another command. Model guidance, six
runtime diagnostics (write guards, headless menu, status and error notices)
and both READMEs no longer offer or name `/memory`, `/consolidate`, or
`/harness` as user input.

Retire the planner worker loadout: `WORKER_LOADOUTS`, `workerCliArgs`,
`workerToolNames`, `createWorkerToolSurface` and the planner case tool. The
parent active-tool transitions and the dynamic current-source collector's
scoped one-read budget survive in `createParentToolSurface` and
`createCollectorToolSurface`; the `learning_read` name remains the collector
tool and the frozen-evidence marker.

Three internal slash-command bindings (`/memory`, `/consolidate`, `/harness`)
remain registered solely for frozen provenance proofs and offline end-to-end
runners. They are not documented, offered in menus, or named in guidance.
Frozen research evidence and completion gates are unchanged.
