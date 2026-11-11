---
name: subagents-single-child-interface
description: pi-subagents has one child tool family (agent_start, agent_input, agent_stop, agent_list); every result paints one row, and its @name is `agentDisplayName`'s lowercase ASCII-hyphenated projection of the authored label, falling back to the identity or generated name when the label has no ASCII letter or digit
type: project
---

`@fradser/pi-subagents` has one model-facing child tool family, declared by `INTENT_TOOL_NAMES` in `src/intent-tools.ts`: `agent_start`, `agent_input`, `agent_stop`, `agent_list`, plus the `subagents_enable` loader; `agent_inspect` is not one of them. The shared executor behind them is `executeChildIntent` in `src/child-execution.ts`, with operations `start | input | steer | inspect | list | stop`. The `agent` tool, its `AGENT_TOOL_PARAMS`, `AGENT_CAPABILITY_TOOLS`, `--subagents-interface legacy`, its uppercase receipts and its own row spec are retired. Authority: @docs/adr/0008-retire-the-legacy-agent-tool.md.

Every result paints one collapsed row: `[tool] label · @name · status` for one child; a roster reads `[agent] listed`, gaining ` · N of M` only when the page omits entries.

**Display names.** The `@name` is one identifier-shaped token, produced once at the `agent_start` boundary by `agentDisplayName` in `src/intent-tools.ts`:

```ts
export function agentDisplayName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/, "");
}
```

The start path calls it as `const label = (authored ? agentDisplayName(authored) : "") || identity || name;` and hands that value to the executor as `startup.label`, which the roster entry, the start receipt, a Session Result notice, a parent message, the `<agent-result from=…>` envelope, the working row above the editor and the stop row all read as the child's name. Because the projection keeps only `[a-z0-9]`, a label with no ASCII letter or digit (`任务 🛠`) projects to nothing and the child keeps its identity name or the generated `subagent-<8 hex>` name; nothing prints the raw phrase in its place. `label` changes display only and never selects an identity. The authored text is not discarded: a temporary child's description is `authored ?? label`, so the role keeps the phrase while every row keeps one token.

**Why:**
Two families meant two vocabularies for one operation, and the legacy row printed the child's name twice, once in the title and once in a body line. The user directive was one line per result, identity and state on it, everything else on expansion. A later report showed the same row carrying a sentence where a name belongs — `[agent] reported · @Task SQL measured optimization` — and required `xxx-xxx` instead, so the authored label became an input projected once rather than a string copied into every surface. A branch that recorded `agent` moves to the intent family silently: the removed tool cannot be restored, and an empty selection would take delegation away instead of moving it.

**How to apply:**
1. Fold the state word into the subject only for one named child, and only when the label does not already carry that word: `[agent] stopped · @x`, not `stopped · @x · stopped`.
2. A roster subject never carries one child's state. It keeps the page count instead, and only when the page omits entries, because a page showing a subset must say so without opening the row.
3. Keep the authored prompt or steer headline on the collapsed row: it is the work itself. Everything else is expansion detail.
4. Never print one fact twice in a row. The expanded row drops any detail line the subject or the common block already carries (`session ·`, `state ·`, `status ·`).
5. Render every intent operation through pi-kit's lifecycle row geometry, as `packages/subagents/src/intent-tools.ts` does. Do not hand-build a second row shape.
6. Project a display name once, where the child is created, with `agentDisplayName`; never slug at an individual paint site, and never let a spaced or capitalised phrase reach a row. Keep the authored label on the role description so the purpose survives the projection.
7. Retirement is a deletion, not a shim: no hidden adapter, no flag, no in-transcript notice. Announce the removal in the changeset, the README and the tool descriptions.

**Related:** [[project_monitor_display_pattern]] [[project_pi_package_conventions]] [[pi-kit-internal-dependency]] [[reference_pi_custom_component_rendering]]
