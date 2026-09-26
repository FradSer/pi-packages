---
"@fradser/pi-kit": patch
"@fradser/pi-agent-teams": patch
"pi-open-deskos": patch
"pi-continual-learning": patch
---

A tool call now names its pattern instead of the directory it searched.

Pi's built-in `grep` and `find` take `{ pattern, path? }`, and every package that labeled a tool call from its arguments read `path` first, so a search that named a root rendered as that directory (`file: <directory>`, `grep: <directory>`, or `<tool> <directory>`) while a search without a root fell back to the bare tool name. The pattern is what the call is doing; the path is only where it looked.

**@fradser/pi-kit**

- `classifyToolActivity()` and `inlineToolActivity()` are new exports: one precedence rule — an explicit command, then a search's pattern, then a path, a query, a subject, and a delivery target — shared by every labeling call site instead of restated per package.
- Live worker progress labeled a `grep` or `find` call `file: <directory>` whenever it carried a `path`, and fell back to the bare tool name otherwise. It now reports `search: <pattern>` and keeps `file: <name>` for genuine file reads.

**@fradser/pi-agent-teams**

- A teammate running `grep`/`find` with a `path` showed `file: <directory>` in its live activity row. It now renders `search: <pattern>`, and its labeler consumes the shared classifier rather than keeping its own copy of the ordering.

**pi-open-deskos**

- `summarizeToolCall` ignored `pattern` entirely, so a `grep` call read as `grep: <directory>`. It now renders `search: <pattern>` and still prefers an explicit command, then a path, for every other tool.

**pi-continual-learning**

- The dreaming widget showed a `grep`/`find` call as `<tool> <directory>`, because a consolidation worker holds `grep`, `find`, and `ls` alongside `read`. A search now names its pattern, and the label is the testable `dreamingToolActivity()` rather than inline argument parsing.