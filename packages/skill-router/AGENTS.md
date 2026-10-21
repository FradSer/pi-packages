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

`features/codemode-skill-tools.feature` is exercised by
`tests/test_codemode_skill_tools.py` through the same `tests/router_harness.ts`
entry point as the routing scenarios.

Isolated acceptance in a container, which needs Docker and the network:

```bash
sh packages/skill-router/tests/skill_router_docker.sh
```

It packs this package and pi-kit, installs them into an isolated tree inside
`node:24-bookworm-slim`, asserts that only this package is loaded, runs the package
gate, installs a collection through the router, and runs both scripted end-to-end
assemblies (`tests/skill_router_e2e.py` with `tests/skill_router_e2e_fixture.ts`).
The image must provide the runtimes the suite declares: Bun 1.4.1 (one registry test
uses `bun -e`) and a warmed corepack (one lock test shells out to `pnpm exec tsx`
under a 20-second budget). `tests/docker-acceptance-evidence.md` records the run and
what those requirements cost when they are missing.

Records kept beside the tests:

- `tests/review-codemode-skill-tools.md` — the review brief, every candidate
  fingerprint, each finding's disposition, and the mutations that showed the new
  tests can fail.
- `tests/terminal-row-evidence.md` — the interactive-terminal check of the tool
  result row and its scope.
- `tests/docker-acceptance-evidence.md` — the container acceptance and the runtime
  requirements it exposed.

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
  Sub-skills retain natural upstream names without prefixes. Explicit
  `/skill:<name>` and expanded `<skill name="...">` invocations are never
  rerouted.
- **Tools Channel**: every routed leaf skill of an enabled collection is
  registered as one codemode tool, named `skill_router__<collection>__<skill>`
  with every character outside `[A-Za-z0-9_]` replaced by `_`, grouped in one
  namespace per collection aliased to the collection id. Its searchable text is
  the workflow summary followed by the upstream description without repeating
  one inside the other; the namespace description is the capability summary and
  its `instructions` is the gateway body. Registration happens when the extension
  loads and again after every `/skill-router` mutation, and never for a disabled
  collection. Pi cannot unregister a tool, so a refresh withdraws the names a
  registry change removed by re-registering them with `hidden` exposure.
- **Channel Selection**: `before_agent_start` resolves the route first and then
  adds the routing suggestion unless that one skill's tool is reachable: codemode
  is active, answers a discovery script by naming that tool, and the tool named
  `skill_router__<collection>__<skill>` is in `pi.getAllTools()`. The registry
  check is load-bearing: `--tools` and `--exclude-tools` filter an extension tool
  out of the registry before codemode can see it, so "codemode is active" alone
  does not make a skill tool reachable. The check stays per skill, because a
  surviving sibling tool must not stand in for a removed one, and a collection
  installed by another process has no tool until `/reload`. The router never
  calls `setActiveTools`.
- **Call Safety**: a call re-resolves its collection from the registry and reads
  the materialized leaf only when it resolves inside the real router root and the
  real `exposed` directory, as a regular file opened with `O_NOFOLLOW` and
  re-checked on its descriptor against the device and inode that were validated;
  a removed collection, a missing leaf, or a symlinked instruction file refuses
  with `isError` and structured content instead of serving content. One call
  returns at most `MAX_SKILL_BODY_CHARS` characters of instructions, followed by a
  note naming the file that holds the rest.
- **Gateway Body**: each workflow line carries the summary, the skill tool name,
  and the relative leaf path, so a hand-invoked gateway works in either codemode
  state.
- **Atomicity**: materialization builds a temporary directory and renames it;
  failures leave no partial exposed directory and do not touch the registry.
- Lock acquisition must remain asynchronous and cancellable. Await all mutation
  APIs and forward the loading overlay's signal; cancellation must not remove
  another process's lock or apply a pending change.
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
