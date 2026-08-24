# Repository Guidelines

## Structure

`index.ts` is the package entry point and re-exports `src/index.ts`. There are no built-in roles; `references/agent-roles.md` is the abstract role reference (definition anatomy, archetype axes, invariants) consulted when generating a new definition on demand. The implementation is split under `src/`: `tools.ts` registers leader-only tools and the `/agent-teams` command; `worker.ts` registers worker-only tools plus the one shared `task_list` definition; `team-machine.ts` coordinates resident teammates (mail routing, task intents, verify gates, wake-ups); `state.ts` owns the roster/in-memory board/leader inbox; `spawner.ts` manages resident RPC child processes; and `ui.ts` provides the passive widget and the `/agent-teams` management console (session teammates + persistent agent roles + board). Supporting modules cover agent discovery, state-file/mail/board IO, worktrees, activity rendering, console viewport math, and follow-up delivery. BDD contracts are in `features/`; executable package checks are in `tests/`.

## Commands

From the repository root, run `python3 -m pytest packages/agent-teams/tests/ -q` for focused tests, `pnpm test` for the monorepo suite, and `npx tsc --noEmit -p tsconfig.extensions.json` for strict extension typechecking. Use `pnpm --dir packages/agent-teams pack --dry-run` to verify published contents.

## Style and architecture

Use ESM TypeScript with explicit `.ts` extensions on relative imports (the root tsconfig enables `allowImportingTsExtensions`, and Node runs these modules natively), strict TypeBox schemas, and the existing module boundaries. Agent definitions are Markdown frontmatter plus a role-prompt body; scopes resolve per name as project-local `<name>.local.md` > project `<name>.md` inside `.pi/agents` (the project layer is git-managed) > user `~/.pi/agent/agents` > bundled; `.local.md` pairs with its plain counterpart deduplicate into one definition. `model`, `verify`, and `worktree` are role frontmatter attributes, not spawn-time overrides. The 7-name tool surface is intentional: `send_message(to, message, status?)` is the single message primitive; workers use `to: "leader"` for outbox reports, peers write direct inboxes, and leaders route addressed messages through control streams or idle wake queues. Only the leader process writes state and board snapshots; workers create exclusive-create claim/submission markers. Keep interactive UI in `ctx.ui.custom` or the established passive-widget pattern; never intercept terminal input globally.

## Tool lifecycle rows follow the pi-kit started/event pattern

Every lifecycle tool renders its transcript rows exactly like `packages/monitor` does with pi-kit helpers — this is the settled house style:

- `renderShell: "self"`; `renderCall` returns an EMPTY element (`new Text("", 0, 0)`). Pi renders tool-call and tool-result slots separately, so a row drawn in both slots duplicates on screen. ONE owner per visual row.
- The startup moment owns exactly one row in `renderResult`: `[agent] started · @<name> · <task-name>`, built with `formatToolEventLabel("started", …)` (toolTitle + bold), teammate/task names accent-colored, wrapped with `truncateToWidth`.
- Terminal outcomes of lifecycle tools own one event row: `[agent] event · @<name> shut down`, built with `formatToolEventLabel("event", …)` in the same style.
- Asynchronous teammate reports are NOT tool rows: they arrive once as custom messages rendered by `registerMessageRenderer`/`registerEntryRenderer` in the approved `[message] from @<teammate>` / `<agent-message from="…">` form (collapsed header + expand hint, full body on expand, separate completion entry line). This message design is confirmed-good; do not re-model it as started/event rows.
- Pure data reads (`task_list`) return their content text normally; do not force event styling onto them.
- Tool surface is intentionally small (seven names; three is a guideline for lifecycle verbs, not a hard cap). `task_create` keeps four flat parameters because each carries a distinct coordination axis; nesting would hide them. Do not add a polling or broadcast tool to save a name at the cost of a conditional parameter.
- Known TypeBox limit: `send_message.status` is only meaningful for `to: "leader"` and is enforced at runtime. Do not copy this pattern in new tools.
- Failure handling belongs with the state machine, not the param guideline: a lost claim race returns a descriptive error guiding the claimant to another task. See `src/state.ts` / `src/worker.ts` for the exclusive-create contract; do not add blocking.

Reference implementation: `packages/monitor/src/index.ts` (`monitor_start` + `monitor-result` renderer); agent-teams application: `src/tools.ts` (`teammate_spawn`, `teammate_shutdown`).

## Testing and release

Update `features/agent-teams.feature` before behavior changes, then update `tests/`. Keep `package.json` `pi.extensions`, peer dependencies, `files` entries, bundled `agents/`, README, and changelog/release metadata aligned. This extension depends on `@fradser/pi-kit` via `workspace:*`; pi-kit must publish before this package.
