/**
 * Native pi tools for DeepWiki / Context7 / Exa retrieval.
 *
 * Replaces the package's `.mcp.json` (MCP servers). pi has no built-in MCP
 * support (docs/usage.md), so these tools call the public REST APIs directly:
 *   - context_deepwiki  → https://mcp.deepwiki.com/mcp (DeepWiki's public JSON-RPC/SSE API)
 *   - context_context7  → https://context7.com/api/v1/{search,docs}
 *   - context_exa       → https://api.exa.ai/search  (needs EXA_API_KEY)
 *
 * Pure HTTP tools — available in interactive and non-interactive runs alike.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateHead, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

const MAX_CHARS = 60_000;
const TIMEOUT_MS = 30_000;
const DEEPWIKI_MCP = "https://mcp.deepwiki.com/mcp";

interface ToolTextResult {
	content: [{ type: "text"; text: string }];
	details: Record<string, unknown>;
}

function textResult(text: string, details: Record<string, unknown> = {}): ToolTextResult {
	return { content: [{ type: "text", text }], details };
}

function truncate(text: string): string {
	if (text.length <= MAX_CHARS) return text;
	const result = truncateHead(text, { maxLines: DEFAULT_MAX_LINES, maxBytes: MAX_CHARS });
	return `${result.content}\n\n…[truncated ${text.length - MAX_CHARS} chars]`;
}

async function httpJson(url: string, init: RequestInit = {}): Promise<{ ok: boolean; status: number; body: string }> {
	const res = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
	const body = await res.text();
	return { ok: res.ok, status: res.status, body };
}

/**
 * DeepWiki's public API is a JSON-RPC-over-HTTP/SSE endpoint (mcp.deepwiki.com).
 * Call a tool directly — no MCP client or sidecar process needed.
 */
async function deepwikiCall(tool: string, args: Record<string, unknown>): Promise<string> {
	const res = await fetch(DEEPWIKI_MCP, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json, text/event-stream",
		},
		body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: tool, arguments: args } }),
		signal: AbortSignal.timeout(TIMEOUT_MS),
	});
	const body = await res.text();
	if (!res.ok) throw new Error(`DeepWiki HTTP ${res.status}: ${body.slice(0, 200)}`);

	// SSE frames: `event: message` + one or more `data:` lines, blank-line terminated.
	// Join multiline payloads, keep the last frame with data.
	let payload: string | null = null;
	let currentData: string[] = [];
	for (const raw of body.split("\n")) {
		const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
		if (line === "") {
			if (currentData.length > 0) payload = currentData.join("\n");
			currentData = [];
			continue;
		}
		if (line.startsWith(":")) continue; // SSE comment
		if (line.startsWith("data:")) {
			currentData.push(line.slice(5).replace(/^ /, ""));
		}
	}
	if (currentData.length > 0) payload = currentData.join("\n");
	if (payload === null) throw new Error("DeepWiki: no data frame in response");

	const data = JSON.parse(payload);
	if (data.error) throw new Error(`DeepWiki: ${data.error.message ?? JSON.stringify(data.error)}`);
	const content = data.result?.content;
	if (Array.isArray(content)) {
		return content.map((c) => (typeof c?.text === "string" ? c.text : JSON.stringify(c))).join("\n");
	}
	return JSON.stringify(data.result ?? data);
}

const DeepWikiParams = Type.Object({
	owner: Type.String({ description: "GitHub owner, e.g. 'facebook'" }),
	repo: Type.String({ description: "GitHub repository name, e.g. 'react'" }),
	mode: StringEnum(["structure", "contents", "ask"], {
		description: "structure = table of contents; contents = full wiki text; ask = targeted Q&A",
	}),
	question: Type.Optional(
		Type.String({ description: "Required when mode is 'ask'; the question about the repository" }),
	),
});
const Context7Params = Type.Object({
	query: Type.String({ description: "Library name to find docs for, e.g. 'fastapi' or 'react'" }),
	topic: Type.Optional(
		Type.String({ description: "Optional topic focus, e.g. 'auth' or 'ssr' (best results with a topic)" }),
	),
});

const ExaParams = Type.Object({
	query: Type.String({ description: "Precise natural-language or code query" }),
	numResults: Type.Optional(
		Type.Number({ description: "Number of results (default 5)", default: 5 }),
	),
});

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "context_deepwiki",
		label: "DeepWiki repo docs",
		description:
			"Fetch AI-generated documentation for a public GitHub repository from DeepWiki. " +
			"mode=structure returns the table of contents; mode=contents returns the full wiki text; " +
			"mode=ask answers a specific question with sources. No API key required.",
		promptSnippet: "Look up AI-generated documentation for a public GitHub repo from DeepWiki",
		promptGuidelines: [
			"Use context_deepwiki to fetch structured repo documentation via DeepWiki instead of cloning when you only need a high-level understanding.",
		],
		parameters: DeepWikiParams,
		executionMode: "sequential",

		async execute(_toolCallId, params) {
			const repo = `${params.owner}/${params.repo}`;
			try {
				if (params.mode === "ask") {
					if (!params.question) {
						return textResult("context_deepwiki: mode 'ask' requires a question");
					}
					const answer = await deepwikiCall("ask_question", { repoName: repo, question: params.question });
					return textResult(truncate(answer));
				}
				const tool = params.mode === "structure" ? "read_wiki_structure" : "read_wiki_contents";
				const out = await deepwikiCall(tool, { repoName: repo });
				return textResult(truncate(out));
			} catch (err) {
				return textResult(`context_deepwiki: ${err instanceof Error ? err.message : String(err)}`);
			}
		},
	});

	pi.registerTool({
		name: "context_context7",
		label: "Context7 library docs",
		description:
			"Fetch up-to-date, version-aware documentation snippets for a library from Context7. " +
			"Searches the library, then retrieves markdown docs (optionally focused on a topic). " +
			"Anonymous usage is rate-limited; set CONTEXT7_API_KEY (Authorization: Bearer) for per-key quota.",
		promptSnippet: "Look up version-aware library documentation from Context7",
		promptGuidelines: [
			"Use context_context7 to look up library docs instead of guessing APIs from memory. Anonymous usage is rate-limited; set CONTEXT7_API_KEY for higher quota.",
		],
		parameters: Context7Params,
		executionMode: "sequential",

		async execute(_toolCallId, params) {
			try {
				const headers: Record<string, string> = {};
				if (process.env.CONTEXT7_API_KEY) {
					headers.Authorization = `Bearer ${process.env.CONTEXT7_API_KEY}`;
				}

			const { ok, status, body } = await httpJson(
				`https://context7.com/api/v1/search?query=${encodeURIComponent(params.query)}`,
				{ headers },
			);
			if (!ok) {
				if (status === 401 || status === 403) {
					return textResult(
						`Context7 search needs an API key (HTTP ${status}). Set CONTEXT7_API_KEY ` +
							`(Authorization: Bearer) or fall back to web/clone methods.`,
					);
				}
				return textResult(`Context7 search failed (HTTP ${status}): ${body.slice(0, 400)}`);
			}

			let libraryId = "";
			try {
				const data = JSON.parse(body);
				const results = Array.isArray(data.results) ? data.results : [];
				if (results.length === 0) {
					return textResult(`Context7: no library found for "${params.query}"`);
				}
				libraryId = typeof results[0]?.id === "string" ? results[0].id : "";
			} catch {
				return textResult(`Context7 search: unexpected response: ${body.slice(0, 400)}`);
			}

			if (!libraryId) {
				return textResult(`Context7: search returned no usable library id for "${params.query}"`);
			}

			// v1 doc ids look like "/owner/repo" — strip the leading slash for the path.
			const path = libraryId.startsWith("/") ? libraryId.slice(1) : libraryId;
			const topic = params.topic ? `&topic=${encodeURIComponent(params.topic)}` : "";
			const docUrl = `https://context7.com/api/v1/${path}?type=txt${topic}`;
			const doc = await httpJson(docUrl, { headers });
			if (!doc.ok) {
				return textResult(`Context7 docs failed (HTTP ${doc.status}): ${doc.body.slice(0, 400)}`);
			}
			return textResult(
				`Context7 docs for "${params.query}" (${libraryId})${params.topic ? `, topic ${params.topic}` : ""}:\n\n${truncate(doc.body)}`,
			);
			} catch (err) {
				return textResult(`context_context7: ${err instanceof Error ? err.message : String(err)}`);
			}
		},
	});

	pi.registerTool({
		name: "context_exa",
		label: "Exa web/code search",
		description:
			"Search the web for real-world code patterns, comparisons, and up-to-date information via Exa. " +
			"Requires the EXA_API_KEY environment variable. Returns titles, URLs, and text snippets.",
		promptSnippet: "Search the web for real-world code patterns, comparisons, and up-to-date information via Exa",
		promptGuidelines: [
			"Use context_exa to search the web when you need current information, code patterns, or comparisons. Requires EXA_API_KEY to be set.",
		],
		parameters: ExaParams,
		executionMode: "sequential",

		async execute(_toolCallId, params) {
			try {
				const apiKey = process.env.EXA_API_KEY;
				if (!apiKey) {
					return textResult(
						"context_exa: EXA_API_KEY is not set. Set EXA_API_KEY to enable Exa search, " +
							"or fall back to web search via curl / GitHub search.",
					);
				}

			const numResults = Math.max(1, Math.min(10, Math.floor(params.numResults ?? 5)));
			const { ok, status, body } = await httpJson("https://api.exa.ai/search", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"x-api-key": apiKey,
				},
				body: JSON.stringify({ query: params.query, numResults, contents: { text: true } }),
			});
			if (!ok) return textResult(`Exa search failed (HTTP ${status}): ${body.slice(0, 400)}`);

			try {
				const data = JSON.parse(body);
				const results = Array.isArray(data.results) ? data.results : [];
				if (results.length === 0) {
					return textResult(`Exa: no results for "${params.query}"`);
				}
				const lines = results.map((r: { title?: string; url?: string; text?: string }, i: number) => {
					const title = r.title || r.url || "(untitled)";
					const url = r.url || "";
					const text = typeof r.text === "string" ? r.text.slice(0, 1200) : "";
					return `${i + 1}. ${title}\n   ${url}\n${text ? `   ${text}` : ""}`;
				});
				return textResult(truncate(lines.join("\n\n")));
			} catch {
				return textResult(`Exa search: unexpected response: ${body.slice(0, 400)}`);
			}
			} catch (err) {
				return textResult(`context_exa: ${err instanceof Error ? err.message : String(err)}`);
			}
		},
	});
}
