# Code Context Pi Package

**Version:** 0.4.1

Retrieve code context for any repo, library, or natural-language query via 5 methods: DeepWiki, Context7, Exa, git clone, and web search+fetch.

## Installation

```bash
pi install /path/to/pi-packages/packages/code-context
```

Run `/skill:get-context <query…>` for the executable Pi workflow.

## Runtime requirements

| Method | Availability | Notes |
|--------|--------------|-------|
| DeepWiki | Always (native tool `context_deepwiki`) | No API key required |
| Context7 | Always (native tool `context_context7`) | Optional `CONTEXT7_API_KEY` (Bearer) for per-key quota |
| Exa | Native tool `context_exa` | Requires `EXA_API_KEY` env var |
| Git clone | Always | Pi `bash` + `read` |
| Web fetch | Always | `curl`/HTTP via `bash` |

All three retrieval tools are registered by this package's extension (`extensions/context-tools.ts`) and call the public REST APIs directly — no MCP servers needed.

## Overview

Code Context accepts **arbitrary input** — a natural-language question, a repo slug, a library name, or several of these at once — and routes each target to the right method(s). It prefers intermediate summaries so the main conversation stays clean, returning only synthesized summaries.

## Methods

### 1. DeepWiki (AI-powered repo documentation)

Best for: Public GitHub repositories requiring architecture overview, component explanations, or high-level understanding.

**Tool:** `context_deepwiki` — `owner`/`repo` + `mode: structure | contents | ask`

**Process:**
1. `context_deepwiki` with `mode: "structure"` (e.g. owner=`facebook`, repo=`react`)
2. `context_deepwiki` with `mode: "contents"` for full wiki text, or `mode: "ask"` + `question` for targeted Q&A

**Strengths:** Zero setup, instant AI-summarized documentation.

**Limitations:** Only works for public GitHub repos; coverage varies by popularity.

---

### 2. Context7 (library documentation)

Best for: Getting up-to-date API docs, usage examples, and version-specific documentation for npm/pip packages.

**Tool:** `context_context7` — `query` + optional `topic`

**Process:**
1. `context_context7` with the library name (e.g. `"react"`, `"fastapi"`)
2. Pass a `topic` (e.g. `"auth"`, `"ssr"`) for focused snippets; include the version in the query when given (`react@18`)

**Strengths:** Always current docs, supports version pinning, covers thousands of libraries.

**Limitations:** Requires the library to be indexed; less useful for internal packages.

---

### 3. Exa Code Search (web-wide code examples)

Best for: Finding real-world usage patterns, StackOverflow answers, GitHub Gist examples.

**Tool:** `context_exa` — `query` + optional `numResults` (requires `EXA_API_KEY`)

**Query tips:**
- Include language: `"TypeScript React"`
- Include version: `"Next.js 14 app router"`
- Use exact identifiers: `"useServerAction"`
- Add pattern type: `"example"`, `"error handling"`

**Strengths:** Finds diverse real-world examples beyond official docs.

**Limitations:** Results may be outdated; verify publication dates.

---

### 4. Git Clone (direct code inspection)

Best for: Private repositories, detailed implementation review, or when other methods lack depth.

**Process:**
1. `git clone <repo-url> /tmp/<repo-name> --depth=1`
2. Read key files: entry points, configuration, core modules
3. Use bash find/grep and Pi `read` to analyze structure and patterns
4. Clean up: `rm -rf /tmp/<repo-name>`

**Strengths:** Full code access, works with private repos.

**Limitations:** Requires network/disk space; slow for large repos.

---

### 5. Web Search + Fetch (post-clone enrichment)

Best for: Enriching clone findings with changelogs, issue discussions, migration guides.

**Tools:** web search via `curl`/HTTP, HTTP fetch via `curl`

**When to use:** After completing Method 4. Gives you the *why* and *what changed*.

**Query patterns:**
- Changelogs: `"<repo> CHANGELOG v<version>"`
- Design rationale: `"<repo> <concept> why OR rationale site:github.com"`
- Migration: `"<repo> migrate from <old> to <new>"`

**Strengths:** Surfaces context never in source code.

**Limitations:** Results may be stale; always validate against actual code.

---

## Usage

### Pi skill: get-context

Run `/skill:get-context` followed by a natural-language question, repository slug, library name, or several targets. For example:

```text
/skill:get-context React 19 server actions error handling
/skill:get-context facebook/react
/skill:get-context facebook/react zustand --method=deepwiki,context7
```

`--method=` accepts `deepwiki,context7,exa,clone,web,all` (comma-separated). With no target, the skill reads dependency manifests in the current directory. It classifies each target and routes it through the allowed methods, noting gaps when a permitted method cannot cover it.

### Optional manual brief

`agents/context-researcher.md` is an optional manual prompt brief for an isolated research pass. Pi does not load it as an invocable agent; use the `get-context` skill for the executable workflow.

The package's internal method-selection guidance is loaded by the `get-context` workflow.

## Method Selection Guide

| Scenario | Primary | Fallback |
|----------|---------|----------|
| "How does X library work?" | Context7 | DeepWiki |
| "Understand Y repo architecture" | DeepWiki | Git Clone |
| "Find examples of Z pattern" | Exa | Context7 |
| "Inspect private/internal repo" | Git Clone | - |
| "What changed in v3?" | Context7 | Exa |
| "How are modules connected?" | DeepWiki | Git Clone |
| "Why was this design decision?" | Git Clone → Web Search | DeepWiki |
| "Compare X vs Y" (natural-language) | Exa + Context7 | Web Search |
| "Best practice for Z" (natural-language) | Web Search | Exa |

## Structure

```
code-context/
├── extensions/
│   └── context-tools.ts         # Native pi tools: context_deepwiki / context_context7 / context_exa
├── agents/
│   └── context-researcher.md    # Isolated research agent brief
├── skills/
│   ├── code-context/            # Knowledge skill (internal)
│   │   └── SKILL.md            # Method selection guide
│   └── get-context/             # User-invocable command
│       └── SKILL.md            # Command workflow
└── README.md
```

## Prerequisites

- Pi 0.84+ (extensions + custom tools)
- Network access for external lookups
- `EXA_API_KEY` for the Exa method (optional for the other four)

## Best Practices

- **Local first**: Always check local context (package.json, imports) before external lookups
- **Isolated execution**: External lookups run in agent context to keep main conversation clean
- **Combine methods**: For comprehensive context, use DeepWiki → Context7 → Exa → Clone
- **Verify sources**: Cross-reference fetched content against actual code

## License

MIT

## Author

Frad LEE (fradser@gmail.com)
