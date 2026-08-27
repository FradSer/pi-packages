# Repository Guidelines

## Project Structure

`packages/utils/` publishes `@fradser/pi-utils`, a native Pi extension. `index.ts`
only wires the focused modules in `extensions/`: `/continue`, `/effort`, `/init`,
`/sessions`/`/recap`, git worktree path redirect, worktree-aware `@`
completions, and EnterWorktree/ExitWorktree session switching. BDD contracts live in
`features/`; executable Python tests and runtime harnesses live in `tests/`.
The published package is limited by `package.json`'s `files` list (`index.ts`,
`extensions/`, and `README.md`).

## Commands

Run from the repository root:

```bash
python3 -m pytest packages/utils/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/utils pack --dry-run
```

`pnpm test` runs the complete workspace test suite.

## Style and Architecture

Use ESM TypeScript targeting Node 20+, with explicit, stable Pi command and tool
names. Keep command behavior in its corresponding extension and keep
`index.ts` as composition-only wiring. Preserve Pi session/context semantics;
interactive choices should use Pi UI APIs rather than global terminal-input
listeners. Reuse `@fradser/pi-kit` helpers when applicable; it is a workspace
runtime dependency, not a peer dependency.

## Testing and Releases

For behavior changes, update the matching `.feature` scenario before changing
implementation, then add or update tests under `tests/`. Cover command parsing,
continuation edge cases, supported thinking levels, safe worktree rewriting,
worktree session replacement, and session registry behavior. Add a Changeset for published changes; any package update should receive a version bump through the GitHub Actions Changesets release flow. Use
the repository's Conventional Commit scopes (for example `feat(packages):`).
