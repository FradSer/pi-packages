/**
 * magpie's `/v1/models` catalog, translated into Pi chat models.
 *
 * magpie serves one gateway for every provider (and routing group) it knows:
 * OpenAI chat completions, OpenAI Responses and Anthropic Messages, with the
 * translation done upstream. Pi only needs the catalog and the endpoint, so
 * these helpers stay free of Pi runtime state and are testable on their own.
 */

import process from "node:process";
import type { Model } from "@earendil-works/pi-ai";

export const MAGPIE_PROVIDER_ID = "magpie";
export const DEFAULT_MAGPIE_BASE_URL = "http://127.0.0.1:3425/v1";

/** One entry of magpie's `/v1/models` answer. Fields Pi does not use are ignored. */
export interface MagpieModelEntry {
	id?: string;
	display_name?: string;
	magpie_label?: string;
	context_window?: number;
	max_input_tokens?: number;
	max_output_tokens?: number;
	modalities?: { input?: readonly string[] };
	reasoning?: boolean;
	supported_reasoning_levels?: readonly { effort?: string }[];
	reasoning_levels?: readonly string[];
	service_tiers?: readonly unknown[];
	type?: string;
	/** magpie's effective price, USD per million tokens. Absent when magpie has none. */
	magpie_price?: {
		input?: number;
		output?: number;
		cache_read?: number;
		cache_write?: number;
	};
}

export type MagpieChatModel = Model<"openai-completions">;

/** Minimal fetch surface, so tests can inject a transport. */
export type FetchLike = (
	input: string,
	init: { headers: Record<string, string>; signal?: AbortSignal },
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

const THINKING_LEVELS = ["minimal", "low", "medium", "high", "xhigh", "max"] as const;

/**
 * magpie speaks the OpenAI chat protocol and maps reasoning efforts itself.
 * Mirrors the compat flags magpie writes into models.json when it wires Pi.
 */
const MAGPIE_COMPAT = {
	supportsReasoningEffort: true,
	thinkingFormat: "openai",
	maxTokensField: "max_tokens",
} as const;

function positive(value: number | undefined): number | undefined {
	return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : undefined;
}

/** A price field, or zero: Pi needs a number for every cost, and states "free" as 0. */
function costValue(value: number | undefined): number {
	return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0;
}

/**
 * magpie reports an effective price per million tokens, matching Pi's own cost
 * units, once a request asks for prices with `X-Magpie-Prices: 1`. Models it has
 * no price for — including a routing group over differently priced members — stay
 * zero rather than borrowing a member's price.
 */
export function costOf(entry: MagpieModelEntry): MagpieChatModel["cost"] {
	const price = entry.magpie_price;
	return {
		input: costValue(price?.input),
		output: costValue(price?.output),
		cacheRead: costValue(price?.cache_read),
		cacheWrite: costValue(price?.cache_write),
	};
}

function effortsOf(entry: MagpieModelEntry): Set<string> {
	const efforts = new Set<string>();
	for (const level of entry.supported_reasoning_levels ?? []) {
		if (typeof level.effort === "string" && level.effort) efforts.add(level.effort);
	}
	for (const level of entry.reasoning_levels ?? []) {
		if (typeof level === "string" && level) efforts.add(level);
	}
	return efforts;
}

/**
 * Pi's thinking levels mapped to the efforts magpie reports. `off` stays
 * unsupported because magpie exposes no way to disable thinking per request;
 * every unsupported level is nulled so Pi clamps instead of sending it.
 */
export function thinkingLevelMap(
	entry: MagpieModelEntry,
): Partial<Record<"off" | (typeof THINKING_LEVELS)[number], string | null>> {
	const efforts = effortsOf(entry);
	const map: Partial<Record<"off" | (typeof THINKING_LEVELS)[number], string | null>> = {
		off: null,
		minimal: null,
	};
	for (const level of THINKING_LEVELS) {
		map[level] = efforts.has(level) ? level : null;
	}
	return map;
}

/** A 3xx/4xx/5xx gateway answer must not replace a working catalog. */
export function isMagpieEntry(value: unknown): value is MagpieModelEntry {
	return typeof value === "object" && value !== null && typeof (value as MagpieModelEntry).id === "string";
}

export function resolveBaseUrl(configured?: string, env: Record<string, string | undefined> = process.env): string {
	const fromEnv = env.MAGPIE_BASE_URL?.trim();
	const base = fromEnv || configured?.trim() || DEFAULT_MAGPIE_BASE_URL;
	return base.replace(/\/+$/, "");
}

/**
 * A gateway address as `/login` should store it. A bare origin gains magpie's
 * `/v1` prefix — the address magpie documents — while an address that already
 * names a path is kept as typed, so a gateway mounted elsewhere still works.
 */
export function normalizeGatewayUrl(input: string | undefined): string {
	const raw = input?.trim() || DEFAULT_MAGPIE_BASE_URL;
	const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `http://${raw}`;
	let url: URL;
	try {
		url = new URL(withScheme);
	} catch {
		throw new Error(`Not a gateway address: ${raw}`);
	}
	const path = url.pathname.replace(/\/+$/, "");
	if (path === "" || path === "/") {
		url.pathname = "/v1";
	}
	return url.toString().replace(/\/+$/, "");
}

function globRegExp(pattern: string): RegExp {
	const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
	return new RegExp(`^${escaped}$`, "i");
}

/**
 * Which magpie models Pi should offer, from `MAGPIE_PI_MODELS`
 * (comma-separated globs, `group/*` for routing groups alone). Unset means all.
 */
export function modelFilter(spec: string | undefined): (id: string) => boolean {
	const patterns = (spec ?? "")
		.split(",")
		.map((pattern) => pattern.trim())
		.filter(Boolean)
		.map(globRegExp);
	if (patterns.length === 0) return () => true;
	return (id) => patterns.some((pattern) => pattern.test(id));
}

export function toPiModel(entry: MagpieModelEntry, baseUrl: string): MagpieChatModel | undefined {
	if (!entry.id) return undefined;
	const contextWindow = positive(entry.context_window) ?? positive(entry.max_input_tokens) ?? 128_000;
	const reasoning = entry.reasoning === true;
	const input: ("text" | "image")[] = entry.modalities?.input?.includes("image") ? ["text", "image"] : ["text"];
	return {
		id: entry.id,
		name: entry.display_name || entry.magpie_label || entry.id,
		api: "openai-completions",
		provider: MAGPIE_PROVIDER_ID,
		baseUrl,
		reasoning,
		...(reasoning ? { thinkingLevelMap: thinkingLevelMap(entry) } : {}),
		input,
		cost: costOf(entry),
		contextWindow,
		maxTokens: positive(entry.max_output_tokens) ?? Math.min(contextWindow, 32_768),
		compat: MAGPIE_COMPAT,
	};
}

/** Every entry magpie serves, in magpie's order, one model per id. */
export function toPiModels(
	entries: readonly MagpieModelEntry[],
	baseUrl: string,
	filterSpec?: string,
): MagpieChatModel[] {
	const include = modelFilter(filterSpec);
	const seen = new Set<string>();
	const models: MagpieChatModel[] = [];
	for (const entry of entries) {
		if (!entry.id || seen.has(entry.id) || !include(entry.id)) continue;
		seen.add(entry.id);
		const model = toPiModel(entry, baseUrl);
		if (model) models.push(model);
	}
	return models;
}

export async function fetchMagpieCatalog(
	baseUrl: string,
	apiKey: string,
	signal: AbortSignal,
	fetchImpl?: FetchLike,
): Promise<MagpieModelEntry[]> {
	const transport = fetchImpl ?? (fetch as unknown as FetchLike);
	// The caller resolved `baseUrl` already; re-reading MAGPIE_BASE_URL here would
	// let an environment variable override the gateway the credential names.
	const response = await transport(`${baseUrl.replace(/\/+$/, "")}/models`, {
		headers: { Authorization: `Bearer ${apiKey}`, "X-Magpie-Prices": "1" },
		signal,
	});
	if (!response.ok) throw new Error(`magpie /v1/models answered HTTP ${response.status}`);
	const payload = (await response.json()) as { data?: unknown };
	if (!Array.isArray(payload.data)) throw new Error("magpie /v1/models returned no data array");
	return payload.data.filter(isMagpieEntry);
}
