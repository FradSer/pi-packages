# Repository Guidelines

## Project Structure & Module Organization

`@fradser/pi-context` exposes exactly one native tool, `context_get`, and no
`/context` command. `index.ts` wires `extensions/context-tools.ts`;
`references/workflow.md` and `prompts/context-research.md` describe the research
protocol. Keep these resources consistent with the single-tool surface.

## Build/Test/Development Commands

Run from the repository root:

```bash
python3 -m pytest packages/context/tests/ -q
pnpm --dir packages/context pack --dry-run
```

## Architecture & Security

The one-shot research worker runs through pi-kit's shared `runPiWorker` in the caller's
working directory with no sandbox, no temporary directory, no wall-clock
timeout, and no result truncation. It receives only `read` and `bash` through
an explicit `--tools` allowlist, so `edit` and `write` are unavailable. Public-repository clones stay
prompt-level guidance only (`git clone --depth=1` under `/tmp`, removed after
inspection). Preserve abort handling; failed or cancelled children must not
return partial answers.

## Testing Guidelines

Use `features/native-tool-runtime.feature` and `tests/test_context_package.py`
for tool-count, no-command, and shared-worker contracts.
`tests/context_tools_harness.mts` provides runtime coverage. Startup renders the
`[context] research started · <research query>` row, using the normalized concrete
request that produced the prompt; completion renders the compact, expandable
`[context] researched · <research query>` lifecycle row. The typed builder treats
Markdown as a reference protocol, constructs the task-specific review prompt, and
fails closed on missing, unknown, or unresolved placeholders.
