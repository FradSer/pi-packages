---
"@fradser/pi-subagents": patch
---

A working child's status row follows Pi's `Hide thinking` setting instead of streaming reasoning the reader asked for.

The above-editor activity row read `liveThinking` directly, so a reader who hid thinking blocks in the transcript still had the reasoning streamed at them in the status line. That is the same reader's surface and the same fact, so it now obeys the same setting: with thinking hidden, the row reads `Thinking...` in the muted activity color — Pi's own label for a hidden thinking block — and the reasoning text never reaches the area.

The label describes thinking, so it yields to newer evidence. Tool activity and answer text take the row as soon as they exist, which is what keeps `Thinking...` from lingering while the child is writing its answer. With thinking visible nothing changes: reasoning still streams through the shared markdown activity.

Read per refresh rather than cached at session start, because the setting is toggled mid-session and a cached copy would keep the old answer until the next session.

Contract: `packages/subagents/features/agent-row-tui.feature`.

**Verification**

- `packages/subagents/tests/test_agent_activity_widget.py` drives the real extension entry with a mocked child: hidden thinking renders `quiet · Thinking...` through the muted color token and never the reasoning text, a tool replaces it, answer text replaces it, and switching the setting back restores the streamed reasoning. A host without `getSettings` keeps the visible behavior.
- `packages/subagents` widget, row, roster, activation, and intent suites pass, and the extension project typechecks.
- Not verified live: no PTY session with a real child was run; the row text and its color token are asserted through the native harness that loads the real entry.