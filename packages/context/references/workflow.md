# context workflow

Retrieve code context for any repo, library, or natural-language code/technology question. Five methods are available; pick them per target. Prefer small intermediate summaries over dumping raw API payloads into the long-lived conversation.

## Native tools

| Method | Tool | Availability |
|--------|------|--------------|
| DeepWiki | `context_deepwiki` | always, no key |
| Context7 | `context_context7` | always, optional `CONTEXT7_API_KEY` for higher quota |
| Exa | `context_exa` | no key required (public endpoint); optional `EXA_API_KEY` for full-text results |
| Git clone | `bash` + `read` | always |
| Web search+fetch | `bash` + `curl` | always |

If a native tool errors or is unreachable, skip it and use the documented clone/web fallback. Report which methods ran. There are no Pi built-ins named `WebSearch`/`WebFetch`/`Task` — do not invent them.

## Invocation

`/context [targets...] [--method=a,b,...]`

- `--method=` accepts a comma-separated list from `deepwiki,context7,exa,clone,web,all`. Default: `all`.
- Quoted strings are one target. Multiple positional tokens are multiple targets.
- No targets: read dependency manifests in cwd (`package.json`, `go.mod`, `pyproject.toml`, `Cargo.toml`) and use detected dependencies as targets.

Classify each target:

- GitHub slug (`owner/repo`) or git URL → repo — DeepWiki (`context_deepwiki`), else clone.
- Bare package name or `name@version` → library — Context7 (`context_context7`), else web + clone of docs repo when known.
- Anything else → natural-language — Exa (`context_exa`, works without an API key); fall back to web search via `curl` if it errors.

When `--method=` is passed, use the intersection of allowed and applicable methods. Empty intersection → skip and report.

## Method 1: DeepWiki

Best for: public GitHub repos needing an architecture overview quickly.

1. `context_deepwiki` with `owner`/`repo` and `mode: "structure"` (e.g. `facebook` / `react`).
2. `mode: "contents"` for the full wiki text, or `mode: "ask"` with `question` for targeted Q&A.
3. Extract architecture summary and key relationships.

Token isolation: structure → relevant pages → short architecture summary.
Fallback on error: Method 4 (clone) + Method 5 (web) on GitHub docs/README.

## Method 2: Context7

Best for: up-to-date API docs and version-specific examples for packages/frameworks.

1. `context_context7` with the library name as `query` (e.g. `fastapi`, `react`).
2. Pass a `topic` (e.g. `auth`, `ssr`) for focused snippets; include the version in the query when given (`react@18`).
3. Extract the minimum viable API surface + examples.

Token isolation: resolve id → query → minimum viable API surface + examples.
Fallback on error: official docs URLs via `curl`, or clone of the library repo docs.

## Method 3: Exa

Best for: real-world usage patterns and cross-web code examples.

1. Call with a precise query (language/framework/version/identifiers).
2. Prefer recent sources; dedupe near-identical snippets and mirrors.
3. Return a short explanation with sources.

Fallback when key missing / error: GitHub code search URLs / known docs via `curl`, or clone representative examples.

## Method 4: Git clone

Best for: private repos, deep implementation review, when other methods lack depth.

1. `git clone <repo-url> /tmp/<repo-name> --depth=1`
2. `read` key files: entry points, config, core modules.
3. Map structure with `bash` find/ls; search with `bash` grep.
4. Cleanup: `rm -rf /tmp/<repo-name>`.

## Method 5: Web search + fetch

Best for: rationale, changelogs, issues, migration guides.

1. Derive version-anchored queries from the question or clone findings.
2. Fetch high-signal URLs (official docs, GitHub issues/PRs, changelogs).
3. Extract only relevant sections; cross-check against cloned code when available.
4. Discard results older than ~2 years unless foundational.

Query patterns:
- Changelogs: `"<repo> CHANGELOG v<version>"`
- Rationale: `"<repo> <concept> why OR rationale site:github.com"`
- Known issues: `"<repo> <symbol> issue OR bug site:github.com"`
- Migration: `"<repo> migrate from <old> to <new>"`

## Method selection guide

| Scenario | Primary | Fallback |
|----------|---------|----------|
| "How does X library work?" | Context7 | Web / clone |
| "Architecture of Y repo" | DeepWiki | Git clone |
| "Examples of Z pattern" | Exa | Context7 / web |
| "Private/internal repo" | Git clone | — |
| "What changed in v3?" | Context7 | Web |
| "Why this design?" | Git clone → web | DeepWiki |
| "Compare X vs Y" | Exa + Context7 | Web |
| "Best practice for Z" | Web | Exa |

## Combining methods

1. DeepWiki / clone for architecture.
2. Context7 for API surface.
3. Exa / web for community patterns.
4. Always prefer read-only operations; clean up `/tmp` clones.
5. Return a synthesized summary only — drop raw bulk payloads.
