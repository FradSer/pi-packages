# Repository Guidelines
## Project Structure
`packages/context/` publishes `@fradser/pi-context`, a native Pi extension with no shipped skill or MCP sidecar. `index.ts` wires `extensions/context-tools.ts` (`context_deepwiki`, `context_context7`, and `context_exa`) and `extensions/context-command.ts` (the `/context` command and concise prompt guidance). The full workflow is in `references/workflow.md`; the manual brief is in `agents/`. BDD scenarios and executable tests are in `features/` and `tests/`.
## Commands
Run from the repository root:
```bash
python3 -m pytest packages/context/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/context pack --dry-run
```
`pnpm test` runs the complete workspace suite.
## Style and Architecture
Use ESM TypeScript, TypeBox schemas, stable native tool names, and direct REST calls rather than MCP servers. Forward Pi abort signals and retain the 30-second request timeout. Keep `/context` workflow loading separate from HTTP tool implementation. Optional API keys belong in environment variables; Exa uses its public keyless endpoint when `EXA_API_KEY` is absent, while operational HTTP failures are tool errors. Use the shared `@fradser/pi-kit` lifecycle renderer for the `/context` transcript message; keep its collapsed summary compact and place the full workflow only in expandable detail.
## Testing and Research
Before editing, inspect the local manifest, workflow, and extension behavior. For external contracts, use `context_context7`; use `context_deepwiki` for public repository architecture and `context_exa` for current usage patterns (keyless by default, full-text with `EXA_API_KEY`), falling back to clone or web fetch. Update a BDD scenario before behavior changes, then extend `tests/` and the HTTP harness for registration, fallback, timeout, abort, and configuration cases. Add a Changeset for published changes and use Conventional Commit scopes such as `feat(packages):`; keep README, workflow, and package `files` aligned.
