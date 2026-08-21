# Repository Guidelines

## Structure

`index.ts` is the package entry point and re-exports `src/index.ts`. Bundled declarative agent definitions live in `agents/` (`worker`, `reviewer`, `specialist`, and `observer`). The implementation is split under `src/`: `tools.ts` registers leader tools and `/teammate`, `run-machine.ts` schedules runs, `state.ts` owns run state, `spawner.ts` manages child Pi processes, `worker.ts` binds worker capabilities, and `ui.ts` provides the passive widget and full-screen console. Supporting modules cover agent discovery, state-file/outbox I/O, worktrees, activity, terminal results, and follow-up delivery. BDD contracts are in `features/`; executable package checks are in `tests/`.

## Commands

From the repository root, run `python3 -m pytest packages/agent-teams/tests/ -q` for focused tests, `pnpm test` for the monorepo suite, and `npx tsc --noEmit -p tsconfig.extensions.json` for strict extension typechecking. Use `pnpm --dir packages/agent-teams pack --dry-run` to verify published contents.

## Style and architecture

Use ESM TypeScript, strict TypeBox schemas, and the existing module boundaries. Agent definitions are Markdown frontmatter plus a role-prompt body; project, user, and bundled scopes resolve in that precedence order. Runs are dependency-aware DAGs of bounded child Pi processes. Worker messaging is one-way to the leader through validated outboxes; `paths` and `access` are advisory scheduling/prompt metadata, while `worktree` is opt-in Git isolation. Keep interactive UI in `ctx.ui.custom` or the established passive-widget pattern; never intercept terminal input globally.

## Testing and release

Update `features/agent-teams.feature` before behavior changes, then update `tests/`. Keep `package.json` `pi.extensions`, peer dependencies, `files` entries, bundled `agents/`, README, and changelog/release metadata aligned. This extension depends on `@fradser/pi-kit` via `workspace:*`; pi-kit must publish before this package.