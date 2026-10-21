# pi-skill-router

`pi-skill-router` routes to **externally hosted skill collections**. It clones skill repositories into a user-level managed directory, wraps the skills you select as hidden leaves behind a visible gateway, exposes them to Pi, and registers every routed skill as a codemode tool the model searches and calls.

**Package version:** see [`package.json`](package.json).

The package ships no skill content itself, and routed collections are never npm packages — they are plain Git repositories you add through the `/skill-router` menu.

## Installation

```bash
pi install npm:pi-skill-router
```

## How It Works

```
~/.pi/agent/skill-router/
├── collections.json      # registry: source, selection, routing terms
├── cache/                # raw git clones (upstream content, unmodified)
└── exposed/              # materialized router output
    └── collections/
        └── <collection>/
            ├── gateway/
            │   └── SKILL.md            # generated gateway (the only skill Pi sees in `/`)
            └── leaves/                 # private sub-skills (suggested by router, hidden from `/`)
                └── <leaf>/SKILL.md
```

1. **Add**: `/skill-router` → *Add collection* → enter `owner/repo[@ref]`, a GitHub URL, or a local path. The repo is shallow-cloned into `cache/`, scanned for `SKILL.md` files, and you choose which skills to route (or all). No prefix is required.
2. **Describe and materialize**: after selecting skills, the active AI model synthesizes the selected skills' descriptions into a whole-collection capability summary and the router saves it directly, without manual editing or confirmation. If no authenticated model is available or generation fails or returns invalid output, Add collection reports an installation error and leaves the collection uninstalled; it never substitutes a skill-name-based summary. The summary becomes the gateway's frontmatter description. Selected skills are saved into `exposed/collections/<collection>/leaves/<name>/`, while the single visible gateway is created in `exposed/collections/<collection>/gateway/SKILL.md`. Keeping the gateway and leaves in one atomic collection tree prevents partial materialization. Its body indexes the selected workflows with descriptions and exact relative leaf paths. Sub-skills remain clean without synthetic name prefixes.
3. **Expose**: on session start and `/reload`, the extension answers Pi's `resources_discover` event with only the gateway directory, so only `/skill:<gateway>` appears in Pi's slash-command menu. Sub-skills do not clutter `/`.
4. **Search and call**: each routed skill is registered as one codemode tool, named `skill_router__<collection>__<skill>` with every character outside `[A-Za-z0-9_]` replaced by `_`, as MCP tool names are. All of a collection's skill tools share one namespace named `skill_router__<collection>`, aliased to the collection id. The model searches codemode's tools and calls the matched one, which returns that skill's instructions together with the directory its references and scripts resolve against. The collection's capability summary is the namespace description and the gateway body is its `instructions`, so one lookup answers what a collection contains. Codemode is inactive by default and the router never activates it.
5. **Fall back without codemode**: while codemode is not active — or while an allowlist has removed the skill tools, or the registered `codemode` declares that it reaches no tool — `before_agent_start` appends a focused suggestion naming the exact sub-skill `SKILL.md` path for the agent to read instead. Your message is never rewritten. The gateway is the sole slash command; sub-skills are never slash commands.

To run the tools channel without an MCP server, declare codemode in your settings with `"defaultTools": ["+codemode"]`. Passing `--tools` names an allowlist that also removes extension tools: `--tools 'read,codemode'` hides every skill tool and leaves only the fallback, while `--tools 'read,codemode,skill_router__*'` keeps them callable from a script. An allowlist match cannot declare a `codemode`-exposure tool, so a direct call needs `tool_search` to load it first. The router decides per skill, so an allowlist that kept one skill's tool and removed another still falls back for the removed one.

## Managing Collections

Registry changes wait asynchronously for competing operations, for up to 10 seconds. Press Escape in the loading overlay to cancel a pending lock acquisition or summary generation; cancellation closes the overlay promptly, leaves the registry and the current owner's lock untouched, and prevents later installation stages. Pending authentication or model responses cannot resume a cancelled flow when they settle. The collection mutation APIs return promises and accept an optional final `AbortSignal` argument. Once a synchronous Git or filesystem mutation begins, it finishes its atomic operation before returning.

Everything runs through the `/skill-router` menu:

- **Add collection** — clone a repo, pick skills, install. Every menu change — add, update, routed skills, capability summary, remove, enable/disable — refreshes the skill tools in place, so the tools channel follows the registry in the same session and a removed or disabled collection has its tools withdrawn. `/reload` is needed only to refresh the gateway command and the prompt's skill list. A collection installed by another process, or a hand-edited registry, stays on the routing suggestion until then.
- **Update collection** — pull upstream and re-materialize the preserved selection. New upstream skills are reported but stay unrouted until you explicitly select them.
- **Change routed skills** — add currently available upstream skills to an installed collection's explicit selection.
- **Edit capability summary** — revise the gateway description for an installed collection, then re-materialize its gateway.
- **Remove collection** — delete the exposed skills and registry entry (the cached clone is kept).
- **Enable/disable collection** — toggle exposure and routing without removing anything.
- **List collections** — show installed collections.

Routing terms are derived from skill names and stored in `~/.pi/agent/skill-router/collections.json`; edit that file to refine terms or collection descriptions. A collection description should be a high-level account of the selected workflows' shared capability, not installation details such as the repository name or gateway mechanics.

## Guarantees

- Gateway names are unique across collections; duplicate upstream skill names inside one collection fail the install instead of colliding.
- Materialization is atomic (temporary directory + rename); a failed install leaves no partial exposed directory.
- Invalid registry entries fail closed: they are ignored for exposure, routing, and tool registration.
- Only skills you selected are ever exposed, and a disabled collection registers no tools.
- A skill tool re-resolves its collection on every call and reads only a regular file inside `exposed/collections`. A removed collection, a tampered leaf, or a symlinked instruction file is refused instead of served.
- A call returns at most 20000 characters of instructions, followed by a note naming the file that holds the rest.
- A registered skill tool can be filtered out of the session entirely by a `--tools` or `--exclude-tools` allowlist. The router detects that for the matched skill, and the routing suggestion takes over for it.
- Removing or disabling a collection while the session is live withdraws its skill tools: Pi cannot unregister a tool, so they are re-registered hidden and stay unreachable.

## Security

Skills are instructions the model follows and may bundle scripts. Review a repository's skills before adding it — installing a collection means trusting its content at user level across all projects.

## License

MIT
