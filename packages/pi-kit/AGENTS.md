# Repository Guidelines

## Structure

`index.ts` re-exports the shared runtime from `src/index.ts`; the implementation intentionally remains a single module. `src/index.ts` contains spinner constants, theme/style and layout helpers, compact labels, Pi child-process spawning/progress/termination, message text extraction, and model-reference/menu helpers. BDD scenarios are in `features/pi-kit.feature`, and executable Python checks are in `tests/`.

## Commands

From the repository root, run `python3 -m pytest packages/pi-kit/tests/ -q` for focused tests, `pnpm test` for the monorepo suite, and `npx tsc --noEmit -p packages/pi-kit/tsconfig.json` for strict typechecking. Use `pnpm --dir packages/pi-kit pack --dry-run` to verify package contents and exports.

## Style and architecture

Use ESM TypeScript with explicit public types and small pure helpers. Keep pi-kit a one-way shared runtime: it may use Node built-ins, must not import Pi core or consumer packages, and must not duplicate utilities already exported by `@earendil-works/pi-tui`. Preserve the native spinner sequence/cadence, shared `PiThemeStyle` callbacks, bounded child-process close/termination semantics, and the existing `provider/model` validation behavior. Consumers should import these helpers from `@fradser/pi-kit` rather than reimplementing them.

## Testing and release

Update `features/pi-kit.feature` before behavior changes, then update `tests/` and run focused and typecheck commands. This is an internal workspace runtime, not a Pi extension package: keep the manifest free of `pi`, `pi-package`, dependencies, and peer dependencies, while retaining its `exports`, `files`, and root entry point. Consumers declare `@fradser/pi-kit` under `dependencies` with `workspace:*`; keep the release allowlist publishing pi-kit before its consumers.