# Matt Pocock for Pi

`pi-matt-pocock` is a Pi extension that provides `/matt-pocock`: a persisted
workflow harness for BDD-first engineering and productivity procedures adapted
from `mattpocock/skills`.

## Installation

This package has not yet been released to npm. Install it from a local checkout:

```bash
pi install /path/to/pi-packages/packages/matt-pocock
```

It will be published as `pi-matt-pocock` after its first-release bootstrap.

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
The user manually transitions phases; the harness does not infer completion
from model or tool activity.

Procedures are internal Markdown resources rather than Pi skills, so generic
workflow names such as `tdd`, `code-review`, and `research` never collide with
an installed skill collection.

See [TODO.md](TODO.md) for deliberately deferred automation.
