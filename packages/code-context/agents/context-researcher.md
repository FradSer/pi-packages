---
name: context-researcher
description: Research a library, repository, or code pattern without polluting the main conversation. Uses DeepWiki/Context7/Exa when MCP is configured, otherwise git clone + HTTP fetch via Pi bash/read. Accepts natural-language queries, repo slugs, library names, or any combination.
---

# Context researcher (optional agent brief)

Pi does not load Claude Code agent files automatically. Treat this file as a **prompt brief** when you want an isolated research pass. Prefer `/skill:get-context` or `/skill:code-context` for the executable workflow.

## Runtime requirements

| Method | Requirement |
|--------|-------------|
| DeepWiki | MCP server `deepwiki-code-context` from package `.mcp.json` |
| Context7 | MCP server `context7-code-context` |
| Exa | MCP server `exa-code-context` (+ optional `EXA_API_KEY`) |
| Git clone | `git` + Pi `bash` / `read` (always) |
| Web | `curl` or host HTTP via Pi `bash` (always) |

If MCP is unavailable, skip those methods and use clone + web. Report which methods ran.

## Process

1. **Parse the request** — targets and optional `--method=` list (see `/skill:get-context`).
2. **Classify** each target (repo / library / natural-language).
3. **Select methods** per `/skill:code-context` selection guide.
4. **Execute with Pi tools** — `bash`, `read`; MCP tools only when present. Summarize intermediates; do not dump raw payloads.
5. **Return** a concise architecture/API/examples summary only.

## Output format

- Target classification
- Methods used (and skipped, with reason)
- Key findings (bullets)
- Copyable snippets only when necessary
- Open questions / confidence notes
