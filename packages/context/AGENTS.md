# Repository Guidelines

## Project Structure & Module Organization

`@fradser/pi-context` exposes exactly one native tool, `context_get`, and no
`/context` command. `index.ts` wires `extensions/context-tools.ts`;
`references/workflow.md` and `agents/context-researcher.md` describe the research
protocol. Keep these resources consistent with the single-tool surface.

## Build/Test/Development Commands

Run from the repository root:

```bash
python3 -m pytest packages/context/tests/ -q
pnpm --dir packages/context pack --dry-run
```

## Architecture & Security

The research child runs through pi-kit's shared `runPiWorker` in the caller's
working directory with no sandbox, no temporary directory, no wall-clock
timeout, and no result truncation. It receives `read` and `bash`, excluding
`edit` and `write` via `--exclude-tools`. Public-repository clones stay
prompt-level guidance only (`git clone --depth=1` under `/tmp`, removed after
inspection). Preserve abort handling; failed or cancelled children must not
return partial answers.

## Testing Guidelines

Use `features/native-tool-runtime.feature` and `tests/test_context_package.py`
for tool-count, no-command, and shared-worker contracts.
`tests/context_tools_harness.mts` provides runtime coverage. Keep the transcript
on the single `[agent] @context-<adjective>-<noun> started · agents/context-researcher.md`
row with a stable, pronounceable run name; the completed result must not add a
separate `[context] researched` event row.
