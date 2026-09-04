# Repository Guidelines

## Project Structure

`packages/matt-pocock/` publishes `pi-matt-pocock`, a catalog-backed Pi capability gateway. The package-root `index.ts` loads `src/index.ts`; `src/catalog.json` is the single source for resource classification and graph relationships, `src/catalog.ts` provides typed queries and validation, `src/resolver.ts` resolves bounded procedure bundles, and `src/workflow.ts` owns persisted workflow state and legal transitions. `procedures/` contains internal Markdown resources and assets. They are not Pi skills, and no child `SKILL.md` may be shipped. BDD scenarios live in `features/`, executable checks in `tests/`, upstream selection metadata in `upstream-selection.json`, and synchronization policy in `UPSTREAM.md`.

## Contributor Commands

Run from the repository root:

```bash
node packages/matt-pocock/scripts/check-upstream-sync.mjs
python3 -m pytest packages/matt-pocock/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/matt-pocock pack --dry-run
```

When validating against an already-cloned upstream checkout, also run:

```bash
node packages/matt-pocock/scripts/check-upstream-sync.mjs --upstream /path/to/mattpocock-skills
```

The sync checker does not clone or fetch upstream.

## Catalog and Resolver Contracts

- Treat the `procedureCatalog` manifest as the only source of procedure ids, aliases, files, kinds, invocation modes, standalone exposure, workflow route metadata, placement, dependencies, disclosures, and transitions. Do not recreate route/procedure enums or route descriptions elsewhere.
- Preserve the four externally meaningful classifications: workflow procedures, standalone capabilities, references, and assets. A standalone capability is a catalog workflow or utility marked `standalone`; references and assets are never public top-level capabilities.
- `requires` is an eager dependency edge. The resolver loads the root and its complete required closure, rejects cycles, and emits every body with stable `source:procedure/<id>` identification.
- `discloses` is an optional reachability edge. Return disclosed ids without eagerly loading their bodies, and reject reference loads outside the active disclosure graph.
- Keep the resolved UTF-8 bundle limit at 64 KiB unless the feature, tests, public architecture documentation, and operational rationale change together. Do not truncate an oversized bundle.
- Every catalog file must exist and be classified exactly once. Every dependency, disclosure, alias, workflow placement, and `allowedNext` target must resolve. Internal references require an inbound catalog edge.

## Gateway and Workflow Contracts

- `/matt-pocock` is the single command menu for workflows, standalone capabilities, status, transitions, completion, and cancellation. Do not add one command per workflow or a second public skill surface.
- `matt_pocock_workflow` is the baseline gateway. It starts a catalog workflow, runs a model-reachable standalone capability, or loads a reference disclosed by a standalone capability.
- `matt_pocock_active` and `matt_pocock_ask` are active-state tools. Enable them only after workflow start or valid restore; remove them after completion, cancellation, failed restore validation, or inactive session start.
- Persist each work item with a stable `workItemId`. Active records use `status: active`; terminal records preserve the identity and use `completed` or `cancelled`, with a cancellation reason when available.
- Enforce the current catalog placement's `allowedNext` list for every transition. Invalid targets fail with allowed alternatives; never fall back to a route entry procedure. A valid transition resets loaded references.
- The model can complete or cancel active work through `matt_pocock_active`; the command menu remains the user control surface. Standalone capabilities do not create persistent workflow state.
- Inject the resolved bundle at start, transition, restore, or explicit reference load. Subsequent turns receive concise state guidance rather than every procedure body.
- Preserve the existing compact lifecycle rows and `@fradser/pi-kit` notification, status, sanitization, and ask-rendering adapters.

## Upstream Sync and Release

`upstream-selection.json` must classify every upstream skill at the recorded latest checked commit as selected or excluded. Selected entries map the upstream path and invocation mode to a local catalog id and plain resource; exclusions carry a concrete reason. Follow `UPSTREAM.md`, strip host-specific frontmatter and invocation syntax, and never copy a nested `SKILL.md` into the package.

For behavior changes, update `features/matt-pocock.feature` first, add or update tests, then implement. Every published-package change requires a Changeset. Do not hand-edit package versions or dependency manifests.
