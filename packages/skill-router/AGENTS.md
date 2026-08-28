# Skill Router Package Guidelines

`packages/skill-router/` publishes `pi-skill-router`, a native Pi package that
routes to externally hosted skill collections. It ships no skill content:
users add GitHub repositories through the `/skill-router` menu, selected
skills are materialized under `~/.pi/agent/skill-router/`, and the extension
exposes them through the `resources_discover` event while adding focused
`before_agent_start` suggestions.

BDD scenarios live in `features/skill-router.feature`; executable tests live
in `tests/test_skill_router.py` with `tests/router_harness.ts` driving the
extension through a tsx harness.

## Commands

Run focused validation with:

```bash
python3 -m pytest packages/skill-router/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/skill-router pack --dry-run
```

## Structure and Invariants

- **Pure router**: `package.json` declares only `pi.extensions`. No `skills/`
  directory, no bundled collections, and routed collections are never npm
  packages.
- **User-level managed directory**: `<agentDir>/skill-router/` holds
  `collections.json` (registry), `cache/` (raw clones), and `exposed/`
  (materialized wrapped skills). Agent dir resolves from
  `PI_CODING_AGENT_DIR` or `~/.pi/agent`, matching sibling packages.
- **Wrapping**: leaves are copied with a `<prefix>-` name rewrite and
  `disable-model-invocation: true`; one visible gateway is generated per
  collection. Prefixes are unique across collections; duplicate upstream
  skill names inside one collection fail the install.
- **Atomicity**: materialization builds a temporary directory and renames it;
  failures leave no partial exposed directory and do not touch the registry.
- **Fail Closed**: invalid registry entries are dropped; prefixes shared by
  multiple collections disable all of them.
- **No Side Effects**: the router never mutates user prompts, injects full
  leaf instructions, or reroutes explicit slash / `<skill>` invocations.
