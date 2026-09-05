# Repository Guidelines

## Project Structure & Module Organization

`packages/skill-router/` publishes `pi-skill-router`, a native Pi package that
routes to externally hosted skill collections. It ships no skill content:
users add GitHub repositories through the `/skill-router` menu, selected
skills are materialized under `~/.pi/agent/skill-router/`, and the extension
exposes them through the `resources_discover` event while adding focused
`before_agent_start` suggestions.

## Commands

Run focused validation with:

```bash
python3 -m pytest packages/skill-router/tests/ -q
pnpm --dir packages/skill-router pack --dry-run
```

## Structure and Invariants

- **Pure router**: the `pi` manifest declares only `extensions`. No `skills/`
  directory, no bundled collections, and routed collections are never npm
  packages.
- **User-level managed directory**: `<agentDir>/skill-router/` holds
  `collections.json` (registry), `cache/` (raw clones), and `exposed/`
  (materialized gateway and sub-skills). Agent dir resolves from
  `PI_CODING_AGENT_DIR` or `~/.pi/agent`.
- **Exposure & Routing**: only the collection gateway skill is exposed to Pi's
  `resources_discover` hook, so sub-skills never clutter the `/` command menu.
  Sub-skills retain natural upstream names without prefixes; the router suggests
  the exact file path in `before_agent_start`. Explicit `/skill:<name>` and
  expanded `<skill name="...">` invocations are never rerouted.
- **Atomicity**: materialization builds a temporary directory and renames it;
  failures leave no partial exposed directory and do not touch the registry.
- **Fail Closed**: invalid registry entries are dropped; duplicate collection
  ids, gateways, caches, or sources disable the conflicting entries.
- **Prompt Preservation**: the router never mutates user prompts or injects
  full leaf instructions. Other slash commands remain routable; only explicit
  skill invocations are skipped.
- **Capability Summaries**: `src/menu.ts` and `src/sync.ts` install only after
  the authenticated active model produces a valid collection summary. Failed
  generation must leave the collection uninstalled, not substitute skill names.

## Testing Guidelines

Exercise `features/skill-router.feature` through `tests/test_skill_router.py`
and `tests/router_harness.ts`. Cover registry conflicts, unsafe refs and
symlinks, atomic rollback, selected-only exposure, and summary-generation
failures using temporary local Git repositories and isolated agent directories.
Upstream skills can carry executable resources; inspect them as untrusted
content before materializing them.
