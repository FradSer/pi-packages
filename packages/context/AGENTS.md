# Context package guidelines

`@fradser/pi-context` exposes exactly one native tool: `context_get`. It launches a separate Pi process for read-only context research. The child receives only `read` and `bash`; on macOS it runs inside `sandbox-exec`, where writes are limited to a unique temporary directory under `/tmp`. It may make depth-1 public-repository clones only in that directory, which is removed on completion.

Before changing behavior, update the matching BDD scenario in `features/`, then add executable coverage under `tests/`. Run:

```bash
python3 -m pytest packages/context/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/context pack --dry-run
```

Keep the tool surface to one tool, output bounded, and the lifecycle transcript compact and expandable.
