---
name: Agent leader priority and assignment completion
description: Leader direction must enter active worker execution through native steering, with idle wake-up and assignment-scoped completion.
type: project
---

Leader direction takes precedence over worker plans and peer requests, subject to system instructions and user constraints. Use native delivery that steers running execution and starts idle execution; a writable control stream is not proof that the worker consumed a message. Completion belongs to the current assignment, not the resident agent or its previous PASS.

**Why**
The voice-audit investigation exposed hardcoded idle inspection and a reopened SSH assignment without a terminal report. The user explicitly requires leader messages to enter the worker's running execution rather than wait for the original task to finish.

**How to apply**
Test terminal-then-reopen, active steering, idle wake-up, delayed reports from old assignments, and truthful presence. Preserve in-flight tool safety; priority does not mean forcibly killing external commands. Distinguish yielding a leader turn from declaring the user's task complete.

**Related**
[[project_monitor_display_pattern]]
