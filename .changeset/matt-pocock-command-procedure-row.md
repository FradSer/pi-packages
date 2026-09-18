---
"pi-matt-pocock": minor
---

Deliver `/matt-pocock` route starts, menu starts and transitions, standalone capability starts, freeform routing requests, and the menu's "Start a task" through the displayed `matt-pocock-procedure` message, so the transcript shows one `[matt pocock] started` block instead of posting the whole procedure text or routing prompt as a user message.

Align that block with `/impeccable`: the head row carries only the label, a blank band row separates it from the body, and the body is the user's own task verbatim, or the readable phase/capability name when no task was given, on pi's native user-message band. Long lines wrap and the block never advertises expansion. Agent-invoked tool rows stay inline and compact.

Extend the command input to `<route|capability> [task]`, mirroring `/impeccable <capability> [request]`: the task now reaches the procedure prompt as `User target/request:` and the transcript row, while persisted workflow state keeps route, phase, and work-item identity only. `transition <target>` and `cancel <reason>` are accepted directly, and a first word matching no route, capability, or action is forwarded verbatim instead of partially matched.