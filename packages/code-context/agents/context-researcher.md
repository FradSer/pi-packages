---
name: context-researcher
description: Research a library, repository, or code pattern without polluting the main conversation. Uses the native context_deepwiki/context_context7/context_exa tools when applicable, otherwise git clone + HTTP fetch via Pi bash/read. Accepts natural-language queries, repo slugs, library names, or any combination.
---

# Context researcher (optional agent brief)

Pi does not load Claude Code agent files automatically. Treat this file as a **prompt brief** when you want an isolated research pass. Prefer `/skill:get-context` or `/skill:code-context` for the executable workflow.

## Runtime requirements

| Method | Requirement |
|--------|-------------|
| DeepWiki | Native `context_deepwiki` tool |
| Context7 | Native `context_context7` tool |
| Exa | Native `context_exa` tool (+ optional `EXA_API_KEY`) |
| Git clone | `git` + Pi `bash` / `read` (always) |
| Web | `curl` or host HTTP via Pi `bash` (always) |

If a native context tool is unavailable or fails, skip that method, use clone + web, and report which methods ran and why the fallback was needed.

## Process

1. **Parse the request** — targets and optional `--method=` list (see `/skill:get-context`).
2. **Classify** each target (repo / library / natural-language).
3. **Select methods** per `/skill:code-context` selection guide.
4. **Execute with Pi tools** — use the applicable native context tools (`context_deepwiki`, `context_context7`, `context_exa`) plus `bash` and `read`. Summarize intermediates; do not dump raw payloads.
5. **Return** a concise architecture/API/examples summary only.

## Output format

- Target classification
- Methods used (and skipped, with reason)
- Key findings (bullets)
- Copyable snippets only when necessary
- Open questions / confidence notes
