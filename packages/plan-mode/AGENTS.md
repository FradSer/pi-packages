# Plan Mode Package Guidelines

Applies to `packages/plan-mode/` (`@fradser/pi-plan-mode`) in addition to
@AGENTS.md at the repository root. All references below are repository-relative.

## Read by Task

- Commands, state, tool guards, plan paths, or model switching:
  @packages/plan-mode/src/index.ts. The package-root `index.ts` re-exports it.
- Model configuration and agent-directory resolution:
  @packages/plan-mode/src/config.ts.
- Explore/writer processes, cancellation, or diagnostics:
  @packages/plan-mode/src/plan-worker.ts.
- Native TUI review, cancellation, and session replacement:
  @packages/plan-mode/src/index.ts. Use `ctx.ui.select` with the owning job signal.
- User-facing behavior: @packages/plan-mode/README.md. Before behavior changes,
  update @packages/plan-mode/features/plan-mode.feature and add a failing
  regression in @packages/plan-mode/tests/test_plan_mode.py. Its
  @packages/plan-mode/tests/plan_lifecycle.mts harness exercises real Pi session
  lifecycle with a faux provider and temporary agent directory.

## Behavior Boundaries

- `/plan <prompt>` directly awaits one pi-kit `runPiWorker` with `minimal: true`
  and only `read`, `grep`, `find`, `ls`. The child explores and returns the plan;
  do not send a planning turn to the parent or require a research marker.
  Keep `/plan start` as the existing interactive main-session planning entry.
- Allocate a plan path once from the first planning prompt. Reserve names
  without overwriting existing files; an empty reservation is not a ready plan.
  Persist the exact path in `plan-mode-path` session entries and restore it on
  session/branch changes. Review, research, and fresh implementation share that
  reference. Honor `PI_CODING_AGENT_DIR`; preserve legacy hash-named files.
- The main session may write/edit only its assigned plan file while planning.
  Validate every bash stage in chains and pipelines; one unsafe stage rejects
  the request. Preserve restricted options and read-only Git operations. This
  guard assumes trusted executables and Git configuration; it is not an OS sandbox.
- Both explore and writer children receive only `read`, `grep`, `find`, and
  `ls`, with `--no-extensions`. Pass the working directory through the worker
  API, not a `--cwd` CLI flag. The writer returns content; only the host writes
  that result, after successful, non-empty completion and an abort check.
  Failed/empty results must retain actionable diagnostics.
- Workers have no wall-clock timeout. Native review waits for explicit selection;
  dismissal and elapsed time never authorize implementation.
- The child uses the configured planning model without switching the parent.
  `/plan start` still switches/restores its main-session model. Keep configuration
  precedence in `src/config.ts`.

## Review and Cancellation

- Await subagent planning and native review from the command handler so headless
  commands own the child lifetime. Only the legacy `/plan start` flow reviews
  from `agent_settled`; detach that review because session replacement waits for
  lifecycle handlers to return. Catch failures and release the owning guard.
- Exit, session replacement, and replacement requests cancel obsolete work.
  Late worker results must not write a plan or open review; stale cleanup must
  not clear a newer job. Manual and automatic selectors share cancellation
  ownership and must ignore late input.
- Send fresh-session implementation through the replacement session context.
  Preserve the plan reference without re-entering plan mode. Unavailable or
  cancelled session replacement must never implement in the current session.
- Use pi-kit renderers and notifications. Keep the mode indicator below the
  editor and passive worker status above it. Use the native selector for
  implementation choices; keep headless planning usable without a selector.

## Verification

For code changes, run from the repository root:

```bash
uv run --with pytest python -m pytest packages/plan-mode/tests/ -q
pnpm exec tsc --noEmit --allowImportingTsExtensions -p packages/plan-mode/tsconfig.json
pnpm typecheck
pnpm --dir packages/plan-mode pack --dry-run
```

The pytest suite invokes the Node/tsx lifecycle harness. Keep behavior coverage
for shell bypasses, stable plan paths, cancellation, and session-replacement
deadlocks; source assertions alone do not verify these contracts. Packed files
must include `index.ts`, `src`, and `README.md`.

For runtime changes, also follow the root installation/live-verification rules;
exercise TUI changes interactively. Shared pi-kit or lifecycle-contract changes
require `pnpm check`. Documentation-only edits need content and reference checks.
