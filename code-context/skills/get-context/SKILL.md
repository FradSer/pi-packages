---
name: get-context
description: Execute this when the user requests code context for a repository, library, or any natural-language code/technology question using DeepWiki, Context7, Exa, git clone, and/or web search+fetch.
---

# get-context

Run the full code-context workflow using Pi tools. Prefer keeping heavy lookups out of a single giant turn when possible — summarize intermediate results.

## Pi tools and runtime

| Capability | How |
|------------|-----|
| Clone / local files | `bash` (`git clone`), `read`, `bash` (find/grep) |
| Web fetch | `bash` with `curl -fsSL` (or available HTTP client) |
| DeepWiki / Context7 / Exa | Optional MCP servers from package `.mcp.json` — only if configured in the host |

See package README **Runtime requirements**. Without MCP, fall back to clone + web fetch methods from `/skill:code-context`.

## Invocation args

When invoked as `/skill:get-context <args>`, the text after the skill block is the user-provided arguments. Pi does not expand `$ARGUMENTS` placeholders inside skill bodies; use the trailing invocation text.

1. Split into positional targets and optional `--method=` flag.
   - `--method=` accepts a comma-separated list from `deepwiki,context7,exa,clone,web,all`. Default: `all`.
   - Quoted strings are one target.
   - Multiple positional tokens are multiple targets.
2. Classify each target:
   - GitHub slug (`owner/repo`) or git URL → repo (DeepWiki if MCP available, else clone).
   - Bare package name or `name@version` → library (Context7 if MCP available, else web + clone of docs repo when known).
   - Anything else → natural-language (Exa if MCP available, else web search via `curl` to searchable sources / known docs URLs).
3. Empty input: read dependency manifests in cwd (`package.json`, `go.mod`, `pyproject.toml`, `Cargo.toml`) and use detected dependencies as targets.

## Execute

1. Load and follow `/skill:code-context` (or `read` that skill file) for method selection and process detail.
2. Run methods with Pi tools as above; do not invent Claude-only tools (`Task`, `WebSearch`, `WebFetch`).
3. Return a synthesized summary only — drop raw bulk payloads.
