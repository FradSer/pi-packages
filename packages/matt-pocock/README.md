# pi-matt-pocock

`pi-matt-pocock` is a Pi extension that provides `/matt-pocock`: a persisted
workflow harness for BDD-first engineering and productivity procedures adapted
from `mattpocock/skills`.

## Installation

```bash
pi install npm:pi-matt-pocock
```

## Workflow harness

`/matt-pocock` opens one routing menu:

- Start an idea-to-ship flow
- Diagnose a hard bug
- Triage incoming work
- Map a large ambiguous initiative
- Improve codebase architecture
- View, transition, or end the current workflow

The harness injects only the chosen procedure, persists its current route and
phase in the Pi session, restores that state on restart, and adds concise
phase guidance to agent turns. Its structured interview tool is available only
while a workflow is active, so ordinary questions remain in the conversation.
When a procedure's done condition makes its next procedure clear, the agent transitions with `matt_pocock_workflow` and continues without waiting for permission. It pauses only for a user-owned decision, unavailable fact, or required external action. The menu's transition option remains available for an explicit user override.

Procedures are internal Markdown resources rather than Pi skills, so generic
workflow names such as `tdd`, `code-review`, and `research` never collide with
an installed skill collection.

For the design rationale, lifecycle, context trade-offs, and a comparison with
upstream `mattpocock/skills`, see the [中文架构说明](ARCHITECTURE.zh-CN.md).

See [TODO.md](TODO.md) for lifecycle automation that remains deliberately deferred.
