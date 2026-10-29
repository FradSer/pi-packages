/**
 * The catalog magpie already serves, fetched before Pi resolves a session's model.
 *
 * Pi starts a provider's refresh with network access disabled, so a fresh agent
 * directory has no models until a session is running. Seeding at extension load
 * closes that gap: `pi --list-models` and the first session see magpie's models,
 * and the provider persists the seeded catalog so later offline starts keep them.
 */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import {
	fetchMagpieCatalog,
	resolveBaseUrl,
	toPiModels,
	type FetchLike,
	type MagpieChatModel,
} from "./catalog.ts";

export interface MagpieSeedOptions {
	/** Environment override for tests; defaults to the Pi process environment. */
	env?: Record<string, string | undefined>;
	/** Transport override for tests. */
	fetch?: FetchLike;
	/** Agent directory override for tests; defaults to Pi's own config directory. */
	agentDir?: string;
	timeoutMs?: number;
}

interface ConfiguredMagpie {
	baseUrl?: string;
	apiKey?: string;
}

/**
 * `models.json` apiKey values are a literal, `$NAME`/`${NAME}` environment
 * interpolation, `$$` for a literal `$`, or a leading `!command`. A command
 * cannot run at load time, so it stays unresolved here; Pi resolves it at
 * request time instead.
 */
export function resolveConfiguredValue(
	raw: string | undefined,
	env: Record<string, string | undefined>,
): string | undefined {
	const value = raw?.trim();
	if (!value || value.startsWith("!")) return undefined;
	const reference = /^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$/.exec(value);
	if (reference) return env[reference[1] ?? ""]?.trim() || undefined;
	return value.replace(/\$\$/g, "$");
}

/** The magpie provider's own settings, as magpie and the user write them. */
export function magpieConfigFromModelsJson(
	agentDir: string,
	env: Record<string, string | undefined>,
): ConfiguredMagpie {
	try {
		const raw = JSON.parse(fs.readFileSync(path.join(agentDir, "models.json"), "utf8")) as {
			providers?: Record<string, { baseUrl?: string; apiKey?: string } | undefined>;
		};
		const provider = raw.providers?.magpie;
		if (!provider) return {};
		const apiKey = resolveConfiguredValue(provider.apiKey, env);
		return {
			...(provider.baseUrl ? { baseUrl: provider.baseUrl.trim() } : {}),
			...(apiKey ? { apiKey } : {}),
		};
	} catch {
		return {};
	}
}

/**
 * The credential `/login magpie` saved. A login is a complete setup on its own:
 * the gateway it proved reachable is stored beside the key, so neither an
 * environment variable nor a `models.json` entry is required to seed.
 */
export function magpieConfigFromAuthJson(agentDir: string): ConfiguredMagpie {
	try {
		const raw = JSON.parse(fs.readFileSync(path.join(agentDir, "auth.json"), "utf8")) as {
			magpie?: { type?: string; key?: string; env?: Record<string, string> };
		};
		const credential = raw.magpie;
		if (credential?.type !== "api_key") return {};
		const key = credential.key?.trim();
		const baseUrl = credential.env?.MAGPIE_BASE_URL?.trim();
		return {
			...(baseUrl ? { baseUrl } : {}),
			...(key ? { apiKey: key } : {}),
		};
	} catch {
		return {};
	}
}

/**
 * magpie's catalog for the model Pi starts on. Empty when magpie is not
 * configured, the process runs offline, or the gateway cannot answer in time.
 */
export async function loadMagpieSeed(options: MagpieSeedOptions = {}): Promise<MagpieChatModel[]> {
	const env = options.env ?? (process.env as Record<string, string | undefined>);
	if (env.PI_OFFLINE) return [];
	const agentDir = options.agentDir ?? getAgentDir();
	const configured = magpieConfigFromModelsJson(agentDir, env);
	// A stored login complements `models.json`: either may supply the key, the
	// gateway, or both.
	const stored = magpieConfigFromAuthJson(agentDir);
	const key = configured.apiKey ?? stored.apiKey ?? env.MAGPIE_API_KEY?.trim();
	if (!key) return [];
	const configuredBase = env.MAGPIE_BASE_URL?.trim() || configured.baseUrl || stored.baseUrl;
	if (!configuredBase) return [];
	const baseUrl = resolveBaseUrl(configuredBase, env);
	try {
		const entries = await fetchMagpieCatalog(
			baseUrl,
			key,
			AbortSignal.timeout(options.timeoutMs ?? 3_000),
			options.fetch,
		);
		return toPiModels(entries, baseUrl, env.MAGPIE_PI_MODELS);
	} catch {
		return [];
	}
}
