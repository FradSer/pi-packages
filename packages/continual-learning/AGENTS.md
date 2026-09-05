# Repository Guidelines

## Project Structure

`packages/continual-learning/` publishes `pi-continual-learning`, a native extension with no
skill surface. Package-root `index.ts` composes `extensions/inject-memory.ts`
(`/memory`, `/consolidate`, injection, cleanup) and `extensions/guardrails.ts`
(`/harness`, tool-call policies, skill-prompt guidance).
Supporting extension modules cover configuration, secure memory loading,
canonical project paths, parent-owned consolidation, harness guardrail mining,
and AGENTS.md consolidation (`extensions/agents-md-consolidation.ts`: plan
validation, verbatim quote verification against the snapshot, document
simulation, byte-budget zero-sum gating, and autonomous application). The
read-only child procedures are
`procedures/consolidate.md`, `procedures/consolidate-harness.md`, and
`procedures/consolidate-agents.md`; `scripts/validate-consolidate.py` is
the dependency-free artifact/privacy validator for the memory phase. BDD contracts are in
`features/`, with Python tests and the TypeScript evidence harness in `tests/`.

## Commands

Run focused checks with:

```bash
python3 -m pytest packages/continual-learning/tests/ -q
pnpm --dir packages/continual-learning pack --dry-run
```

## Style and Architecture

Use strict bounded memory filename/loading rules, atomic writes,
and symlink-safe path checks. Consolidation remains parent-owned: acquire the
project lock, capture an immutable snapshot (or explicit `no-context` mode),
spawn a read-only `--no-extensions` worker, accept one bounded structured plan,
validate before and after mutation, then write receipts. Harness resolves its three configuration layers independently. Memory instead has exactly two synchronized roots: the complete private `~/.pi/agent/memory/<escaped-canonical-project-path>/` root and the safe project `.memory/` mirror. Automatic consolidation transactionally applies safe changes to both and private changes only to the private root; Harness consolidation still writes only `.pi/harness.local.json`. Never let the child
mutate memory or configuration. The AGENTS.md phase additionally requires code-verified snapshot
quotes, batched evidence for new units, budget zero-sum at cap, autonomous
application only after mechanical validation, and never targets user-level
instruction files.

## Testing Guidelines

Cover injection, command registration, model/config handling, locking,
snapshots, bounds, rollback, layer precedence and immutability, receipts, and
shutdown cancellation. `features/` separates memory, harness, and instruction
consolidation contracts. The manifest ships `index.ts`, `procedures`,
`extensions`, `scripts`, `examples`, and `README.md`; place runtime helpers and
sanitized policy examples inside those published paths.
