# Domain Glossary

## Assignment Attempt

One authorization for a Teammate to perform direct work or hold a Board Task claim. It is distinct from both Teammate identity and the work item; replacing, reopening, releasing, or reclaiming work creates a new Assignment Attempt.

## Teammate

A reusable actor with an identity, capabilities, liveness, and process incarnation. A Teammate is not defined by any one Assignment Attempt.

## Process Incarnation

One live child-process instance of a Teammate, identified by `spawnId`. It authenticates the source process but does not establish which Assignment Attempt authored an event.

## Coordination Event

An asynchronous report, task intent, verification result, or lifecycle marker that may propose a shared-state transition. It is authoritative for a current transition only when causally bound to the active Assignment Attempt.

## Historical Evidence

A Coordination Event from an Assignment Attempt that is no longer current. It remains part of the team's history but cannot propose a current shared-state transition.

## Team Console

The interactive TUI surface through which a leader views the current team, board, and coordination history. It presents richer coordination detail without adding model-facing tool parameters.
