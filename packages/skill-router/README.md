# pi-skill-router

`pi-skill-router` routes to **externally hosted skill collections**. It clones skill repositories into a user-level managed directory, wraps the skills you select as hidden leaves behind a visible gateway, exposes them to Pi, and provides focused routing suggestions.

**Package version:** 0.2.0

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
2. **Describe and materialize**: after selecting skills, confirm a short capability summary for the whole collection. The suggested text is derived from the selected skill names; edit it to describe the collection's domain and tasks rather than its Git source. The summary becomes the gateway's frontmatter description. Selected skills are saved into `exposed/collections/<collection>/leaves/<name>/`, while the single visible gateway is created in `exposed/collections/<collection>/gateway/SKILL.md`. Keeping the gateway and leaves in one atomic collection tree prevents partial materialization. Its body indexes the selected workflows with descriptions and exact relative leaf paths. Sub-skills remain clean without synthetic name prefixes.
3. **Expose**: on session start and `/reload`, the extension answers Pi's `resources_discover` event with only the gateway directory, so only `/skill:<gateway>` appears in Pi's slash-command menu. Sub-skills do not clutter `/`.
4. **Route**: when a prompt matches a route, `before_agent_start` appends a focused suggestion naming the exact sub-skill `SKILL.md` path for the agent to read. Your message is never rewritten. The gateway is the sole slash command; sub-skills are never slash commands.

## Managing Collections

Everything runs through the `/skill-router` menu:

- **Add collection** — clone a repo, pick skills, install.
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
- Invalid registry entries fail closed: they are ignored for both exposure and routing.
- Only skills you selected are ever exposed.

## Security

Skills are instructions the model follows and may bundle scripts. Review a repository's skills before adding it — installing a collection means trusting its content at user level across all projects.
