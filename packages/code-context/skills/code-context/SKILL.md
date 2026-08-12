---
name: code-context
description: This skill should be used when the user asks to "understand a codebase", "get code context", "research a library", "explore a repository", "find code examples", "look up documentation", asks a natural-language code/technology question (e.g. "how does X work", "X vs Y", "best practice for Z"), or wants to understand how a specific project, library, or concept works before making changes.
disable-model-invocation: true
---

# Code Context Retrieval

This skill provides 5 methods for retrieving code context. Select methods based on the target: public GitHub repos, library docs, code search, direct inspection, or post-clone web enrichment.

## Pi tools and runtime

Use Pi built-ins: `bash`, `read`, `edit` (rarely), `write` (rarely), plus this package's native tools from `extensions/context-tools.ts`.

| Method | Runtime |
|--------|---------|
| DeepWiki | `context_deepwiki` tool (always available; no key) |
| Context7 | `context_context7` tool (always available; optional `CONTEXT7_API_KEY` for higher quota) |
| Exa | `context_exa` tool (requires `EXA_API_KEY` env) |
| Git clone | `bash` + `read` (always available) |
| Web search+fetch | `bash` + `curl` (or host HTTP) |

If a tool reports an error (e.g. `EXA_API_KEY` unset), skip it and use clone/web fallbacks. Report which methods ran.

## Token Isolation (Critical)

Prefer small intermediate summaries over dumping entire API payloads into the long-lived conversation:

- **DeepWiki**: structure → relevant pages → short architecture summary
- **Context7**: resolve id → query → minimum viable API surface + examples
- **Exa**: query → dedupe near-identical snippets → short explanation
- **Git clone**: clone to `/tmp/`, read entry points, cleanup, return structure + patterns
- **Web**: targeted queries, fetch high-signal URLs only, validate against code when possible

## Method 1: DeepWiki (AI-powered repo documentation)

Best for: public GitHub repos needing architecture overview quickly.

**Tool**: `context_deepwiki` (native, always available)

**Process**:
1. `context_deepwiki` with `owner`/`repo` and `mode: "structure"` (e.g. `facebook` / `react`)
2. `context_deepwiki` `mode: "contents"` for the full wiki text, or `mode: "ask"` with a `question` for targeted Q&A
3. Extract architecture summary and key relationships

**Fallback on error**: Method 4 (clone) + Method 5 (web) on GitHub docs/README.

## Method 2: Context7 (library documentation)

Best for: up-to-date API docs and version-specific examples for packages/frameworks.

**Tool**: `context_context7` (native, always available)

**Process**:
1. `context_context7` with the library name as `query` (e.g. `fastapi`, `react`)
2. Pass a `topic` (e.g. `auth`, `ssr`) for focused snippets; include the version in the query when given (`react@18`)
3. Extract the minimum viable API surface + examples

**Fallback on error**: official docs URLs via `curl`, or clone of the library repo docs.

## Method 3: Exa Code Search

Best for: real-world usage patterns and cross-web code examples.

**Tool**: `context_exa` (native; requires `EXA_API_KEY`)

**Process**:
1. Call with a precise query (language/framework/version/identifiers)
2. Prefer recent sources; dedupe mirrors

**Fallback when key missing / error**: GitHub code search URLs / known docs via `curl`, or clone representative examples.

## Method 4: Git Clone (direct code inspection)

Best for: private repos, deep implementation review, when other methods lack depth.

**Process**:
1. `git clone <repo-url> /tmp/<repo-name> --depth=1`
2. `read` key files: entry points, config, core modules
3. Map structure with `bash` find/ls; search with `bash` grep or Pi search tools if available
4. Cleanup: `rm -rf /tmp/<repo-name>`

## Method 5: Web Search + Fetch

Best for: rationale, changelogs, issues, migration guides.

**Tools**: `bash` + `curl` (or host HTTP client). There are no Pi built-ins named web search via `curl`/HTTP / HTTP fetch via `curl`.

**Process**:
1. Derive version-anchored queries from the question or clone findings
2. Fetch high-signal URLs (official docs, GitHub issues/PRs, changelogs)
3. Extract only relevant sections; cross-check against cloned code when available
4. Discard results older than ~2 years unless foundational

**Query patterns**:
- Changelogs: `"<repo> CHANGELOG v<version>"`
- Rationale: `"<repo> <concept> why OR rationale site:github.com"`
- Known issues: `"<repo> <symbol> issue OR bug site:github.com"`
- Migration: `"<repo> migrate from <old> to <new>"`

## Target Classification

- **Repo target** — `owner/repo` or git URL → DeepWiki (`context_deepwiki`) or Git Clone
- **Library target** — package name / `name@version` → Context7 (`context_context7`) else web/docs clone
- **Natural-language target** — question/comparison → Exa (`context_exa`) and/or Web; Context7 if a library is named

When caller passes `--method=`, use the intersection of allowed and applicable methods. Empty intersection → skip and report.

## Method Selection Guide

| Scenario | Primary | Fallback |
|----------|---------|----------|
| "How does X library work?" | Context7 | Web / clone |
| "Architecture of Y repo" | DeepWiki | Git Clone |
| "Examples of Z pattern" | Exa | Context7 / web |
| "Private/internal repo" | Git Clone | — |
| "What changed in v3?" | Context7 | Web |
| "Why this design?" | Git Clone → Web | DeepWiki |
| "Compare X vs Y" | Exa + Context7 | Web |
| "Best practice for Z" | Web | Exa |

## Combining Methods

1. DeepWiki / clone for architecture
2. Context7 for API surface
3. Exa / web for community patterns
4. Always prefer read-only operations; clean up `/tmp` clones
