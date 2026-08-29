# Pi Skill Router

`pi-skill-router` routes to **externally hosted skill collections**. It clones skill repositories into a user-level managed directory, wraps the skills you select as hidden leaves behind a visible gateway, exposes them to Pi, and provides focused routing suggestions.

**Package version:** 0.1.0

The package ships no skill content itself, and routed collections are never npm packages — they are plain Git repositories you add through the `/skill-router` menu.

## Installation

This package has not yet been released to npm. Install it from a local checkout:

```bash
pi install /path/to/pi-packages/packages/skill-router
```

## How It Works

```
~/.pi/agent/skill-router/
├── collections.json      # registry: source, selection, routing terms
├── cache/                # raw git clones (upstream content, unmodified)
└── exposed/              # materialized gateway and sub-skills
    └── <collection>/
        ├── <gateway>/SKILL.md    # generated gateway (the only skill Pi sees in `/`)
        └── skills/               # internal sub-skills (suggested by router, hidden from `/`)
            └── <leaf>/SKILL.md
```

1. **Add**: `/skill-router` → *Add collection* → enter `owner/repo[@ref]`, a GitHub URL, or a local path. The repo is shallow-cloned into `cache/`, scanned for `SKILL.md` files, and you choose which skills to route (or all). No prefix is required.
2. **Materialize**: selected skills are saved into `exposed/<collection>/skills/<name>/`, and a single gateway skill is created in `exposed/<collection>/<gateway>/SKILL.md`. Sub-skills remain clean without synthetic name prefixes.
3. **Expose**: on session start and `/reload`, the extension answers Pi's `resources_discover` event with only the gateway directory, so only `/skill:<gateway>` appears in Pi's slash-command menu. Sub-skills do not clutter `/`.
4. **Route**: when a prompt matches a route, `before_agent_start` appends a focused suggestion naming the exact sub-skill `SKILL.md` path for the agent to read. Your message is never rewritten. The gateway is the sole slash command; sub-skills are never slash commands.

## Managing Collections

Everything runs through the `/skill-router` menu:

- **Add collection** — clone a repo, pick skills, install.
- **Update collection** — pull upstream and re-materialize the preserved selection. New upstream skills are reported but stay unrouted until you explicitly select them.
- **Change routed skills** — add currently available upstream skills to an installed collection's explicit selection.
- **Remove collection** — delete the exposed skills and registry entry (the cached clone is kept).
- **Enable/disable collection** — toggle exposure and routing without removing anything.
- **List collections** — show installed collections.

Routing terms are derived from skill names and stored in `~/.pi/agent/skill-router/collections.json`; edit that file to refine terms or descriptions.

## Guarantees

- Prefixes are unique across collections; duplicate upstream skill names inside one collection fail the install instead of colliding.
- Materialization is atomic (temporary directory + rename); a failed install leaves no partial exposed directory.
- Invalid registry entries fail closed: they are ignored for both exposure and routing.
- Only skills you selected are ever exposed.

## Security

Skills are instructions the model follows and may bundle scripts. Review a repository's skills before adding it — installing a collection means trusting its content at user level across all projects.
