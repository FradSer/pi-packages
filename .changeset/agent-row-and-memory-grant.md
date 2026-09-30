---
"@fradser/pi-subagents": patch
"@fradser/pi-agent-teams": patch
---

The `agent` tool paints a lifecycle row, and only a fixed Agent's spawn carries `agent_memory`.

**The row**

Starting a child printed its raw receipt into the transcript:

```
AGENT · calc1 · started · session:calc1:00e8aac4-494c-4dec-af76-74385ab7f077
WORKING · 回答:1+1 等于几?
GRANT · agent_memory, message, task
```

`registerAgentTool` already accepted a `renderResult` and the entry never supplied one, so every `agent` result fell through to Pi's default text rendering. `src/rows.ts` now binds the shared pi-kit band with real terminal geometry, and `src/extension.ts` passes it in, so a spawn reads like any other lifecycle event:

```
 [agent] started · @calc1 · ctrl+o to expand
 回答:1+1 等于几?只回复结果本身,不要额外说明。
```

Expansion adds `role ·`, `model ·`, `tools ·`, the coordination-only warning, and the remaining prompt lines. A session handle never appears in a row; the model keeps the exact handle in the result text.

The reason the entry could not do this earlier is worth recording, because the stated reason was wrong. Both `src/extension.ts` and the `@fradser/pi-tasks` entry claimed that importing pi-tui executes theme code that throws outside a rendered session. It does not: `truncateToWidth`, `visibleWidth`, and `wrapTextWithAnsi` are pure string functions. What throws is `keyHint()` before `initTheme()`, and `bindLifecycleRenderers` already resolves the expand hint through a guarded thunk. The entry is the right layer for the binding, so it now owns it, and the test loads the entry and renders before any theme exists to keep that property true.

`src/agent-tool.ts` also drops a duplicated `publishRosterAsBoardStore()` call, and an idle resident's row now states it is waiting instead of filtering the receipt line that said so.

**The grant**

Every spawned child was granted `agent_memory`, and `@fradser/pi-subagents`' worker extension was loaded into every child, whatever the Agent's memory opt-in. The child registered nothing when memory was off, so the grant line promised a capability the child did not have: `agent_memory` in `--tools`, no such tool in the child.

`spawnTeammate` now contributes the subagents capability set and its worker extension only when the resolved definition has Agent Memory, which `agents.ts` grants solely to a persisted definition with `memory: true`. A Temporary Agent is spawned as a bare `pi --no-extensions` process holding its own grant plus this package's `message` and `task`, and nothing else. A role naming `agent_memory` without the opt-in is refused by name instead of being silently dropped by the child's allowlist.

```
memory: true      →  --extension <subagents worker>   --tools read, bash, agent_memory, message, task
no memory field   →  --extension <teams worker>      --tools read, bash, message, task
inline role       →  --extension <teams worker>      --tools read, message, task
```

`references/agent-roles.md` documents `memory: true`, since that file is where a leader generating a role looks and the field was previously undiscoverable.

Contract: `packages/subagents/features/agent-row-tui.feature`, and a new rule in `packages/subagents/features/agent-memory.feature`.

**Verification**

- `packages/subagents/tests/test_agent_row_tui.py` drives the real `executeAgentAction` and paints through the entry-registered renderer: the entry registers one, a render before `initTheme()` produces rows rather than throwing, the collapsed row is one band naming the child and its prompt, expansion carries the grant and the prompt tail, no handle leaks, and a clipped row advertises the configured expand key.
- `test_agent_memory_reaches_only_a_fixed_agents_spawn` asserts the grants behaviourally, from the real spawn path with a mocked child: a fixed Agent, a persisted Agent without the opt-in, and a Temporary Agent each produce a recorded grant equal to the child's `--tools` argv, only the fixed one carries the memory extension, and the refused spawn starts no child at all.
- Against the real `pi` binary: a bare child with `--tools read` reports `read`; the same child with the worker extension and `PI_SUBAGENT_MEMORY=enabled` executes `agent_memory`; with `PI_SUBAGENT_MEMORY=none` it does not. A fresh `pi --print` process loading the edited extension starts a temporary agent and reports `GRANT · coordination only`.
- `packages/subagents` (64), `packages/agent-teams` (242), `packages/tasks`, and the root suites pass; `pnpm typecheck`, `pnpm pack:check`, and `pnpm check:install` are clean.
