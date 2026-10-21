---
"pi-skill-router": minor
---

Routed leaf skills become codemode tools, searched and called instead of handed a path.

A routed skill was reachable only through a `before_agent_start` suggestion that named its `SKILL.md`, so the router chose, the model read, and nothing made a skill searchable. Every routed leaf skill of an enabled collection is now registered as one codemode tool, so the model searches codemode's tools and calls the matched one. Decision record: `docs/adr/0010-skill-router-codemode-skill-tools.md`.

**What changed**

- One tool per routed skill, named `skill_router__<collection>__<skill>` with every character outside `[A-Za-z0-9_]` replaced by `_`, as MCP tool names are. All of a collection's skill tools share one namespace named `skill_router__<collection>`, aliased to the collection id, whose description is the capability summary and whose `instructions` is the gateway body — so `describeNamespace()` answers what a collection contains.
- Searchable text is the workflow summary followed by the skill author's own description, without repeating one inside the other. The summary says what the skill does; the upstream description carries the words a request uses. Per-skill text is the only discriminating text, because namespace text repeats across a collection, and the tool takes no parameters so skill names never enter every document of that collection.
- A call returns `{ ok, collection, skill, tool, directory, skillFile, body, truncated }` through `outputSchema`/`structuredContent`. The directory is the point: a skill's references, scripts, and assets resolve relative to it. A body over 20000 characters is cut and the result names the file that holds all of it.
- A call re-resolves its collection from the registry and reads the materialized leaf only when it resolves inside the real router root and the real `exposed` directory, as a regular file opened with `O_NOFOLLOW` whose descriptor must be the device and inode that were validated. A removed collection, a missing leaf, or a symlinked instruction file is refused with `isError` and structured content instead of serving content.
- The gateway body keeps its summaries and relative leaf paths and now names each workflow's tool, so a hand-invoked `/skill:<gateway>` works in either codemode state.
- Registration happens once, when the extension loads, and never for a disabled collection.

**Channel selection**

`before_agent_start` resolves the route first and adds a routing suggestion unless that one skill's own tool is reachable: codemode is active, answers a discovery script by naming the tool, and `skill_router__<collection>__<skill>` is in `pi.getAllTools()`. The router never activates codemode: a session that does not declare it keeps the fallback.

The registry check is load-bearing, and a live run is why. `--tools` and `--exclude-tools` name an allowlist that filters extension tools out of the session's registry before codemode can see them. With `--tools read,codemode`, `ALL_TOOLS` inside the sandbox held only `read`, every skill-tool call failed, and the model fell back to reading exposed files by guessing paths. The gate detects that and the routing suggestion takes over. `--tools 'read,codemode,skill_router__*'` keeps the tools callable from a script — an allowlist match cannot declare a `codemode`-exposure tool, so a direct call requires `tool_search` to load one; `"defaultTools": ["+codemode"]` keeps codemode active without an allowlist at all.

The check stays per skill for three reasons an independent review found. An allowlist can keep one routed skill's tool and remove another's, and a surviving sibling must not stand in for the removed one. A collection installed by another process has no tools at all. And a replacement `codemode` may declare `reachesTools` while naming nothing, so the gate asks instead of reading the declaration. Each case carries a scenario and a test.

**Refreshed in place**

Registration is no longer load-only. Every `/skill-router` mutation — add, update, routed skills, capability summary, remove, enable/disable — re-reads the registry and re-registers the tools with fresh descriptions and namespace instructions, because Pi cannot unregister a tool, a name the change removed is re-registered with `hidden` exposure. Only the gateway command and the prompt's skill list still wait for `/reload`. The menu's notification now says so.

**Unchanged**

Routing terms, `routePrompt`, the registry schema, the atomic materialization, the symlink refusals, the capability-summary contract, and the `/skill-router` menu. Registry entries written by an older version stay valid.

**Packaging**

`packages/skill-router/package.json` gains `"type": "module"` — the source has always been ESM, and the routing harness could not load a value import without it — and `typebox` as a peer dependency, matching the other Pi packages in this repository.

**Verification**

- New `features/codemode-skill-tools.feature` with 25 scenarios, exercised by `tests/test_codemode_skill_tools.py` (26 tests) through the existing `tests/router_harness.ts` entry point. The harness now captures `registerTool`, models the session's tool set, can hide tools the way an allowlist does, adds a collection after the extension loaded, drives the registered `/skill-router` command so the extension's own wiring runs, and can refresh the tools directly.
- `python3 -m pytest packages/skill-router/tests/ -q`: 101 passed. `pnpm typecheck`, `pnpm --dir packages/skill-router pack --dry-run`, and `pnpm pack:check` pass.
- Live Pi 1.3.0 run with a real model, a disposable agent directory and cwd, `-e packages/skill-router/index.ts`, `--no-mcp`, `--no-context-files`, `--no-session`, `--exclude-tools bash,edit,write`, and `codemode.inlineBudget: 0` so only `searchTools()` could find a tool. The model ran `searchTools("seo audit")`, which returned `skill_router__upstream__seo_audit`; then `tools.skill_router__upstream__seo_audit({})`, whose payload carried the body and directory; and answered with the token only the body contains. The skill tool was never declared — its call was a nested call of the codemode script. The run was repeated on the repaired candidate.
- An independent review of the first candidate returned two blocking findings, both repaired with a scenario and a test each, and four bounded rechecks returned Standards pass, Spec pass, blocking 0. Findings those rounds left non-blocking were closed too: the answer-checked gate, in-place refresh with withdrawal, the validated-descriptor read, the guarded `reachesTools` call, and coverage of a refresh that updates an existing tool. The review brief, every candidate fingerprint, and each disposition are in `packages/skill-router/tests/review-codemode-skill-tools.md`. Each new test group was shown able to fail by removing or weakening the code it covers.
- The tool result row was checked in a real interactive TUI under a PTY, including its `ctrl+o` detail and a live resize to 60x24: `packages/skill-router/tests/terminal-row-evidence.md`.
- The whole acceptance also runs in an isolated container from packed tarballs — the package gate, a real collection install, and both scripted end-to-end assemblies: `packages/skill-router/tests/skill_router_docker.sh`, evidence in `packages/skill-router/tests/docker-acceptance-evidence.md`. That layer found two environment requirements of the existing suite rather than product defects: Bun 1.4.1 and a warmed corepack, both now satisfied by the setup.