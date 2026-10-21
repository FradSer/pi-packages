# 0010: Skill Router delivers leaf skills as codemode tools

## Status

Accepted 2026-10-21. Scope: routing and delivery in `packages/skill-router`.
The registry schema, the materialized exposed tree, and the `/skill-router`
menu keep their behavior.

## Context

A Pi skill is prose: Pi advertises each skill by name and description, and the
model reads the instruction file when the task calls for it. `pi-skill-router`
keeps leaf skills out of Pi's skill list entirely and instead injects a
`before_agent_start` suggestion that names the matched leaf's instruction file.
The model then reads that path.

Pi's codemode exposes another route to the same content. A registered tool with
`exposure: "codemode"` is callable from a codemode script, is listed in the
codemode tool description grouped by namespace, and is ranked by
`searchTools()`. The Scheme is not MCP-specific: `ToolDefinition` carries
`exposure`, `namespace`, `reachesTools`, `outputSchema`, and `promptGuidelines`
for any extension. The MCP extension uses exactly these fields.

The requirement here is that the model reach a leaf skill by searching the tools
and calling the matched one, rather than by being handed a path.

Two facts shape the trade-off. Codemode is inactive by default: Pi activates it
only for an MCP server whose exposure asks for it, or when the user names it in
`defaultTools`. And `searchTools()` ranks tools over names, descriptions,
parameter schemas, and namespace text, so a searchable skill must exist as a
tool.

## Decision

- **One skill tool per routed leaf skill**, named
  `skill_router__<collection>__<skill>`, with every character outside
  `[A-Za-z0-9_]` replaced by `_`. This mirrors `mcp__<server>__<tool>`.
- **One namespace per collection**, named `skill_router__<collection>` with the
  collection id as an alias. Its `description` is the capability summary and its
  `instructions` is the gateway body, so `describeNamespace` answers "what is in
  this collection" in one call.
- **Searchable text** is the workflow summary followed by the upstream
  description. The summary states what the skill does; the upstream description
  carries the words a request actually uses. A per-skill description is the only
  discriminating text, because namespace text repeats across a collection.
- **Exposure is `codemode`.** The tool takes no parameters, so skill names never
  enter every document of the collection through a parameter schema.
- **A call returns the skill's wrapped instructions and its directory** through
  `outputSchema`/`structuredContent`. Success carries `{ ok: true, collection,
  skill, tool, directory, skillFile, body, truncated }`; a refusal carries
  `{ ok: false, collection, skill, tool, error }` with `isError`, so a script
  reads one shape whatever went wrong. The directory matters because a skill's
  references, scripts, and assets resolve relative to it. An oversized body is
  truncated and points at the real file on disk.
- **The router never activates codemode.** `before_agent_start` resolves the route
  first, and the tools channel applies only when that skill's own tool is
  reachable: codemode is active, declares `reachesTools`, and
  `skill_router__<collection>__<skill>` is in the session's registry. Otherwise
  the entry injects the routing suggestion for that skill.
- **The gateway stays** as the human entry point, and its body now carries each
  workflow's summary, its skill tool name, and its leaf path. A `/skill:` prompt
  is an explicit invocation that the router never reroutes, so the gateway body
  is the only clue available to a hand-invoked gateway.
- Routing terms and `routePrompt` stay: the fallback channel still needs them.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| A few generic tools (`load`, `list`) instead of one per skill | `searchTools()` ranks tools. A single loader would give search nothing to rank, so the required search-then-call flow would have no search step. |
| Activate codemode from the router, as the MCP extension does | The user keeps explicit control of which tools a session declares. The fallback channel already keeps skills reachable without codemode. |
| Replace the skill channel entirely: no gateway, no routing, no terms | Skills would be unreachable in any session without codemode, and `/skill:<gateway>` manual entry would disappear with them. |
| `exposure: "deferred"` with `tool_search` discovery | The requirement names codemode's search. (`tool_search` can still find these tools, since it searches `codemode` and `deferred` exposure alike; that remains available and is not forbidden.) |
| Put the workflow summary only in the searchable text | Recall drops: the generated summary deliberately drops the upstream trigger wording a request is likely to use. |

## Consequences

- Leaf skill delivery now depends on codemode being active. The fallback channel
  is a second live code path, and both must keep working.
- The tool allowlist (`--tools`, `--exclude-tools`) filters an extension tool out
  of the session's registry before codemode can see it. Naming or matching the
  skill tools activates and declares them, so the model may call them directly as
  well as from a script; leaving them out of the allowlist removes them entirely,
  which is why the gate re-checks the registry and falls back. An allowlist match
  cannot declare a `codemode` tool (`_isDeclarable` accepts only `direct` and
  `model-only`), so a direct call requires `tool_search` to load it. A session that
  wants the tools channel and nothing else declares codemode through
  `defaultTools` rather than `--tools`.
- A tool's searchable text and its namespace `instructions` are captured when the
  extension loads, while its call body is read fresh. `/reload` is therefore
  required after any collection change, not only after adding one.
- The gate asks the registered `codemode` what it reaches for a script that
  searches instead of reading the declaration alone. A replacement `codemode`
  that declares `reachesTools` and names nothing keeps the fallback, and the
  routing suggestion remains the only working path. The cost is a coupling to
  codemode's script input, which Pi defines as a `code` string.
- The codemode tool description grows with the number of routed skills, so
  `codemode.inlineBudget` decides how many skill tools are listed inline and how
  many are only reachable through `searchTools()`.
- A tool count that grows with installed skills is visible in
  `pi.getAllTools()`, `/mcp`-style listings, and every codemode loadout refresh.
  Registration happens at extension load and after each `/skill-router` mutation,
  so a collection installed by another process still needs `/reload`.
- A tool's searchable text and its namespace `instructions` are recomputed on
  every `/skill-router` mutation, so only a registry changed by another process —
  or a hand edit — stays stale until `/reload`.
- `before_agent_start` now decides per turn, because the active tool set can
  change during a session.

## Required evidence

- Package features and tests in the Given/When/Then loop: tool and namespace
  shape, searchable text, call payload and truncation, disabled collections
  registering nothing, the tools-channel gate suppressing the suggestion, the
  fallback suggestion while codemode is unavailable or the allowlist has removed
  the tools, and refusal to read outside the exposed tree.
- `python3 -m pytest packages/skill-router/tests/ -q`, `pnpm typecheck`, and
  `pnpm --dir packages/skill-router pack --dry-run`.
- A live Pi run that actually searches and calls a skill tool through codemode.
  Unit tests do not establish that codemode reaches a registered extension tool.

## Acceptance record

Observed on 2026-10-21 against Pi 1.3.0 and a local Git collection of two
skills, with `PI_CODING_AGENT_DIR` pointing at a disposable agent directory, a
disposable cwd, `-e packages/skill-router/index.ts`, `--no-mcp`,
`--no-context-files`, `--no-session`, `--exclude-tools bash,edit,write`, and a
settings file holding `codemode.inlineBudget: 0` so only `searchTools()` could
find a tool. The model wrote
`const found = await searchTools("seo", { limit: 20 })`, which returned
`skill_router__upstream__seo_audit` with the composed description; then
`const res = await tools.skill_router__upstream__seo_audit({})`, whose payload
carried the skill body and directory; and answered with the token that only the
skill body contains. The skill tool was not declared: its call appeared as a
nested call of the codemode script.

The first live attempt failed and produced this ADR's gate condition. With
`--tools read,codemode`, Pi's allowlist removed the skill tools from the
registry, so `ALL_TOOLS` held only `read`, every call failed, and the model fell
back to reading exposed files by guessing paths. That run is the evidence that
"codemode is active" alone does not mean a skill tool is reachable.

An independent review of that first candidate found two blocking defects, both
repaired before delivery. The gate was global (`some` over every registered skill
tool), so an allowlist that kept one skill's tool and removed another suppressed
the fallback for the removed skill, and a collection added after load had no
reachable channel either; it is now decided per matched skill. Leaf containment
was compared against the resolved `exposed` directory, so replacing
`root/exposed` with a symlink moved the base with it and served the linked
tree; containment is now anchored on the real router root, requires the real
`exposed` directory, and the read opens with `O_NOFOLLOW` and re-verifies the
file on its descriptor. Each repair carries a scenario and a test, and the
recheck ran against the repaired candidate.

Three findings the recheck left as non-blocking or as a residual were then closed
as well, because each one had a real failure behind it rather than only a wording
gap.

- The gate read the `reachesTools` declaration instead of asking it, so a
  replacement `codemode` that declares it and names nothing suppressed the
  fallback for every skill; the gate now asks with a discovery script and
  requires the answer to name the tool.
- Registration happened only at load, so a collection installed through the menu
  had no skill tools — and, once the gate was per skill, no fallback either —
  until `/reload`. Every menu mutation now refreshes the tools in place: the
  registry is re-read, definitions are re-registered with fresh descriptions and
  namespace instructions, and a name the change removed is re-registered with
  `hidden` exposure, because Pi cannot unregister a tool.
- The leaf read compared device and inode only against the file it opened; a
  directory swapped between the containment check and the open could still
  redirect it. The descriptor is now required to be the very file that was
  validated.

Both new test groups were shown capable of failing: removing the menu's refresh
left the installed collection's tool absent, and removing the withdrawal loop
left a removed collection's tool exposed.

A residual stays open and is recorded rather than claimed closed: a symlinked
router root is resolved rather than refused, exactly as `loadCollections` and
`managedFile` already did, and the sync layer refuses to create one.