# Repository Guidelines

> Renamed from `@fradser/pi-memory` to `pi-continual-learning`: the package now owns
> the harness surface of continual learning (declarative tool-call guardrails) in
> addition to the prompt surface (memory retrieval, injection, consolidation).

## Project Structure

`packages/pi-continual-learning/` publishes `pi-continual-learning`, a native extension with no
skill surface. Package-root `index.ts` loads `extensions/inject-memory.ts`,
which owns `/memory`, `/consolidate`, memory injection, and lifecycle cleanup.
Supporting extension modules cover configuration, secure memory loading,
canonical project paths, and parent-owned consolidation. The read-only child
procedure is `procedures/consolidate.md`; `scripts/validate-consolidate.py` is
the dependency-free artifact/privacy validator. BDD contracts are in
`features/`, with Python tests and the TypeScript evidence harness in `tests/`.

## Commands

Run focused checks with:

```bash
python3 -m pytest packages/pi-continual-learning/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/pi-continual-learning pack --dry-run
```

There is no separate build step; Pi loads the shipped TypeScript entry point.

## Style and Architecture

Use ESM TypeScript, strict bounded memory filename/loading rules, atomic writes,
and symlink-safe path checks. Consolidation remains parent-owned: acquire the
project lock, capture an immutable snapshot (or explicit `no-context` mode),
spawn a read-only `--no-extensions` worker, accept one bounded structured plan,
validate before and after mutation, then write receipts and synchronize only
safe files to `.memory`. Never let the child mutate memory or expose private
harness data. Reuse `@fradser/pi-kit`; keep its dependency direction intact.

## Testing and Release

Update the relevant feature before behavior changes, then extend tests for
injection, command registration, model/config handling, locking, snapshots,
bounds, rollback, privacy, receipts, and shutdown cancellation. The manifest
ships `index.ts`, `procedures`, `extensions`, `scripts`, and `README.md`; keep
all runtime helpers inside those paths. Add a Changeset for published changes
and follow the repository's Conventional Commit scopes.
