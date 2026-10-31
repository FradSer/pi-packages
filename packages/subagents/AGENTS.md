# Subagents Package Guidelines

`packages/subagents/` publishes `@fradser/pi-subagents`, the runtime library and
independent Pi package for child agent execution. Package entry `index.ts`
loads `src/agent-extension.ts`. Implementation lives in `src/`: `intent-tools.ts`
defines the four intent tools, `spawner.ts` manages child process execution,
`agents.ts` manages durable disk identities, `child-execution.ts` and `child-env.ts`
handle child environment isolation, and `rows.ts` formats lifecycle display.

## Commands

Run focused tests from the repository root:

```bash
python3 -m pytest packages/subagents/tests/ -q
pnpm --dir packages/subagents pack --dry-run
```

For real-model Docker studies, see `packages/subagents/tests/docker-study/README.md`.

## Structure and Invariants

- **Tool Surface**: The four intent tools (`agent_start`, `agent_input`,
  `agent_stop`, `agent_list`) are the exclusive child tool family.
  `agent_message` is an optional, child-only capability granted explicitly for
  bounded intermediate progress; it is never included in default grants.
- **Child Lifecycle**: Both temporary and durable children settle to `IDLE`
  after every settled result, remaining available for `delivery: "next"` or
  `delivery: "steer"` until `agent_stop` or parent shutdown. No child process
  survives its parent Pi process.
- **Identity and Boundaries**: Disk `agent.md` alone declares a durable identity;
  `identity` selects an existing definition. `label` changes display only and
  never selects or creates an identity. Missing identities fail before effects.
  Do not combine a saved identity with temporary `instructions`.
- **Workspace & Storage**: Children execute in the project working directory
  with an isolated private agent home. There are no model-facing `persistent`,
  `memory`, `worktree`, or definition-creation parameters.

## Task References

- Read @VISION.md for the core execution contract, acceptance policy, and lifecycle state rules.
- Read @AUTHORITY.md when changing authorization, definition creation, migration, or child controls.
