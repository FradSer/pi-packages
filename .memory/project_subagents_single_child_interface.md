---
name: subagents-single-child-interface
description: pi-subagents exposes one child tool family (five intent tools) and one collapsed row per result; the `agent` tool and its six-action API are retired
type: project
---

`@fradser/pi-subagents` has one model-facing child tool family: `agent_start`, `agent_input`, `agent_stop`, `agent_inspect`, `agent_list`, plus the `subagents_enable` loader. The shared executor behind them is `executeChildIntent` in `src/child-execution.ts`, with operations `start | input | steer | inspect | list | stop`. The `agent` tool, its `AGENT_TOOL_PARAMS`, `AGENT_CAPABILITY_TOOLS`, `--subagents-interface legacy`, its uppercase receipts and its own row spec are retired. Authority: @docs/adr/0008-retire-the-legacy-agent-tool.md.

Every result paints one collapsed row: `[tool] label · @name · status` for one child, `[agent] listed · @children · N of M` for a roster.

**Why:**
Two families meant two vocabularies for one operation, and the legacy row printed the child's name twice, once in the title and once in a body line. The user directive was one line per result, identity and state on it, everything else on expansion. A branch that recorded `agent` moves to the intent family silently: the removed tool cannot be restored, and an empty selection would take delegation away instead of moving it.

**How to apply:**
1. Fold the state word into the subject only for one named child, and only when the label does not already carry that word: `[agent] stopped · @x`, not `stopped · @x · stopped`.
2. A roster subject never carries one child's state. It keeps the page count instead, because a page showing a subset must say so without opening the row.
3. Keep the authored prompt or steer headline on the collapsed row: it is the work itself. Everything else is expansion detail.
4. Never print one fact twice in a row. The expanded row drops any detail line the subject or the common block already carries (`session ·`, `state ·`, `status ·`).
5. Render every intent operation through pi-kit's lifecycle row geometry, as `packages/subagents/src/intent-tools.ts` does. Do not hand-build a second row shape.
6. Retirement is a deletion, not a shim: no hidden adapter, no flag, no in-transcript notice. Announce the removal in the changeset, the README and the tool descriptions.

**Related:** [[project_monitor_display_pattern]] [[project_pi_package_conventions]] [[pi-kit-internal-dependency]] [[reference_pi_custom_component_rendering]]
