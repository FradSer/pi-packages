# Context Pi Package

**Version:** 0.5.0

Retrieve code context for any repo, library, or natural-language query via 5 methods: DeepWiki, Context7, Exa, git clone, and web search+fetch.

The package does **not** ship a skill. Native tool guidance is injected into the system prompt, and the `/context` command loads the full workflow into the current turn.

## Installation

```bash
pi install npm:@fradser/pi-context
# or from this repository:
pi install /path/to/pi-packages/packages/context
```

## Usage

Run `/context` followed by a natural-language question, repository slug, library name, or several targets. For example:

```text
/context React 19 server actions error handling
/context facebook/react
/context facebook/react zustand --method=deepwiki,context7
```

`--method=` accepts `deepwiki,context7,exa,clone,web,all` (comma-separated). With no target, the command reads dependency manifests in the current directory (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`) and uses detected dependencies as targets.

The full workflow (target classification, per-method process, fallbacks, selection guide) lives in `references/workflow.md` and is injected into the turn when `/context` runs. Lightweight tool-selection guidance is always present in the system prompt.

## Runtime requirements

| Method | Availability | Notes |
|--------|--------------|-------|
| DeepWiki | Always (native tool `context_deepwiki`) | No API key required |
| Context7 | Always (native tool `context_context7`) | Optional `CONTEXT7_API_KEY` (Bearer) for per-key quota |
| Exa | Native tool `context_exa` | Requires `EXA_API_KEY` env var |
| Git clone | Always | Pi `bash` + `read` |
| Web fetch | Always | `curl`/HTTP via `bash` |

All three retrieval tools are registered by this package's root extension entry (`index.ts`) and call the public REST APIs directly — no MCP servers needed.

## Methods (summary)

1. **DeepWiki** — AI-generated repo docs via `context_deepwiki` (`mode: structure | contents | ask`).
2. **Context7** — up-to-date library docs via `context_context7` (`query` + optional `topic`).
3. **Exa** — web/code search via `context_exa` (`query` + optional `numResults`, requires `EXA_API_KEY`).
4. **Git clone** — `git clone --depth=1` to `/tmp`, `read` key files, clean up.
5. **Web search+fetch** — `bash` + `curl` against official docs, GitHub issues, changelogs.

If a native tool is unavailable or errors, fall back to clone/web. The `/context` workflow reference contains the full selection matrix and per-method process.

## Optional manual brief

`agents/context-researcher.md` is an optional manual prompt brief for an isolated research pass. Pi does not load it as an invocable agent; use the `/context` command for the executable workflow.

## Structure

```
context/
├── index.ts                     # Package-root extension entry point
├── extensions/
│   ├── context-tools.ts         # Native pi tools: context_deepwiki / context_context7 / context_exa
│   └── context-command.ts       # /context command + system-prompt guidance
├── references/
│   └── workflow.md              # Full workflow injected by /context
├── agents/
│   └── context-researcher.md    # Isolated research brief (manual)
└── README.md
```

## Prerequisites

- Pi with extensions + custom tools
- Network access for external lookups
- `EXA_API_KEY` for the Exa method (optional for the other four)

## Best Practices

- **Local first**: check local context (package.json, imports) before external lookups.
- **Combine methods**: DeepWiki / clone for architecture, Context7 for API surface, Exa / web for community patterns.
- **Verify sources**: cross-reference fetched content against actual code.
- **Clean up**: remove `/tmp` clones when finished.

## License

MIT

## Author

Frad LEE (fradser@gmail.com)
