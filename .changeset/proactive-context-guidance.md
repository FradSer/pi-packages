---
"@fradser/pi-context": patch
---

Make the injected context-retrieval guidance proactive: natural-language search requests (e.g. "帮我搜索") now route to `context_exa`, library/API questions to `context_context7`, and public-repo questions to `context_deepwiki`, with trigger phrasing in both the system-prompt guidance and the tool-level prompt guidelines.

`context_exa` no longer requires `EXA_API_KEY`: without a key it queries Exa's public keyless endpoint (`mcp.exa.ai`, same JSON-RPC/SSE pattern as DeepWiki); with a key it upgrades to the full-text `api.exa.ai/search` REST API.
