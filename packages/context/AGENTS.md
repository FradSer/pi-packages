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

The research child receives `read` and `bash`, excluding `edit` and `write`.
Create its working directory with `mkdtempSync` under `os.tmpdir()` rather than
assuming the platform's temp path is `/tmp`. On macOS, `sandbox-exec` limits
writes to this directory; other platforms rely on tool and prompt restrictions.
Permit depth-1 public-repository clones only in temporary research space.
Preserve the 180-second deadline, abort handling, and cleanup on close or launch
failure; failed or cancelled children must not return partial answers.

## Testing Guidelines

Use `features/native-tool-runtime.feature` and `tests/test_context_package.py`
for tool-count, no-command, sandbox, cleanup, and bounded-result contracts.
`tests/context_tools_harness.mts` provides runtime coverage. Keep the result
label `researched` and its compact, expandable transcript.
