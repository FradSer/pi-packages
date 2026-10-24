/**
 * A Pi provider over magpie's gateway, with magpie's live catalog.
 *
 * The gateway is OpenAI-compatible, so streaming is delegated to Pi's own
 * `openai-completions` implementation; this file only owns the catalog and
 * the key. The catalog comes from `GET /v1/models` on every network refresh
 * and is persisted by Pi, so a model added or removed in magpie shows up
 * without editing `models.json`.
 */

import process from "node:process";
import { isModelType, type Credential, type Provider } from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/compat";
import {
	MAGPIE_PROVIDER_ID,
	fetchMagpieCatalog,
	normalizeGatewayUrl,
	resolveBaseUrl,
	toPiModels,
	type FetchLike,
	type MagpieChatModel,
} from "./catalog.ts";

export interface MagpieProviderOptions {
	/** Transport override for tests. */
	fetch?: FetchLike;
	/** Environment override for tests; defaults to the Pi process environment. */
	env?: Record<string, string | undefined>;
	/** Catalog fetched before Pi resolves a session's model; see `loadMagpieSeed`. */
	seed?: readonly MagpieChatModel[];
}

function isMagpieChatModel(model: { provider: string; api: string }): model is MagpieChatModel {
	return model.provider === MAGPIE_PROVIDER_ID && model.api === "openai-completions";
}

export function createMagpieProvider(options: MagpieProviderOptions = {}): Provider<"openai-completions"> {
	const env = options.env ?? (process.env as Record<string, string | undefined>);
	let models: MagpieChatModel[] = [...(options.seed ?? [])];
	// The gateway a login settled on. Pi stores it beside the key, so later
	// requests and refreshes use that gateway without any environment variable.
	let loginBaseUrl: string | undefined;

	// The gateway key: a stored credential, then the process environment Pi reports,
	// then the environment this provider was created with.
	const keyFrom = async (
		ctx: { env(name: string): Promise<string | undefined> },
		credential: Credential | undefined,
	): Promise<string | undefined> => {
		if (credential?.type === "api_key" && credential.key) return credential.key.trim();
		const ambient = (await ctx.env("MAGPIE_API_KEY"))?.trim() || env.MAGPIE_API_KEY?.trim();
		return ambient || undefined;
	};

	const gatewayKey = (credential: Credential | undefined): string | undefined =>
		credential?.type === "api_key" && credential.key ? credential.key : env.MAGPIE_API_KEY?.trim() || undefined;

	// Delegate streaming to Pi's openai-completions implementation: magpie accepts
	// the same request shape and fills in reasoning and tool calls upstream.
	const streams = openAICompletionsApi();

	/**
	 * Where requests and refreshes go. A gateway saved by `/login` wins, because
	 * that is the one the user proved reachable; otherwise Pi's registered URL
	 * (which already reflects `models.json`) and the environment decide.
	 */
	const baseUrlFor = (credential: Credential | undefined, registered?: string): string =>
		loginBaseUrl ??
		resolveBaseUrl(
			(credential?.type === "api_key" ? credential.env?.MAGPIE_BASE_URL : undefined) ?? registered,
			env,
		);

	return {
		id: MAGPIE_PROVIDER_ID,
		name: "magpie",
		baseUrl: resolveBaseUrl(undefined, env),
		auth: {
			apiKey: {
				name: "magpie gateway key",
				login: async (interaction) => {
					// `/login magpie` asks for the gateway as well as the key: magpie can
					// run on this machine, in Docker, or on another host, and the key alone
					// cannot say which. The entered address is stored with the credential,
					// so no environment variable is needed afterwards.
					const baseUrl = normalizeGatewayUrl(
						await interaction.prompt({
							type: "text",
							message: "magpie gateway URL",
							placeholder: resolveBaseUrl(undefined, env),
						}),
					);
					const key = (
						await interaction.prompt({ type: "secret", message: `gateway key for ${baseUrl}` })
					).trim();
					// Prove both before saving anything: a wrong URL or key is reported here
					// instead of as a request timeout on the first turn.
					interaction.notify({ type: "progress", message: `Checking ${baseUrl}` });
					await fetchMagpieCatalog(baseUrl, key, interaction.signal, options.fetch);
					loginBaseUrl = baseUrl;
					return { type: "api_key", key, env: { MAGPIE_BASE_URL: baseUrl } };
				},
				check: async ({ ctx, credential }) => {
					const key = await keyFrom(ctx, credential);
					return key
						? { type: "api_key", source: credential ? "stored credential" : "MAGPIE_API_KEY" }
						: undefined;
				},
				resolve: async ({ ctx, credential }) => {
					const key = await keyFrom(ctx, credential);
					if (!key) return undefined;
					const baseUrl = baseUrlFor(credential);
					if (credential?.type === "api_key" && credential.env?.MAGPIE_BASE_URL) {
						loginBaseUrl = credential.env.MAGPIE_BASE_URL;
					}
					return {
						auth: { apiKey: key, baseUrl },
						env: credential?.type === "api_key" ? credential.env : undefined,
						source: credential ? "stored credential" : "MAGPIE_API_KEY",
					};
				},
			},
		},
		getModels: () => models,
		refreshModels: async (context) => {
			// Pi calls this with network access first disabled, to restore the last
			// persisted catalog, and then enabled when a live refresh is allowed.
			const stored = (context.stored?.models ?? []).filter(
				(model) => isModelType(model, "chat") && isMagpieChatModel(model),
			);
			const seeded = models;
			if (stored.length > 0 && models.length === 0) {
				const published = await context.publish({
					update: () => {
						models = stored;
					},
				});
				if (!published) return;
			}
			if (!context.allowNetwork || context.signal.aborted) {
				// A seeded catalog is newer than the persisted one and is all an
				// offline start gets, so cache it now.
				if (seeded.length > 0) {
					await context.publish({ persist: { models: seeded, checkedAt: Date.now() } });
				}
				return;
			}

			const baseUrl = baseUrlFor(context.credential, context.baseUrl);
			const key = gatewayKey(context.credential);
			if (!key) return;
			const entries = await fetchMagpieCatalog(baseUrl, key, context.signal, options.fetch);
			if (context.signal.aborted) return;
			const refreshed = toPiModels(entries, baseUrl, env.MAGPIE_PI_MODELS);
			// An empty answer never erases a catalog that already works.
			if (refreshed.length === 0) return;
			await context.publish({
				persist: { models: refreshed, checkedAt: Date.now() },
				update: () => {
					models = refreshed;
				},
			});
		},
		stream: (model, context, streamOptions) => streams.stream(model, context, streamOptions),
		streamSimple: (model, context, streamOptions) => streams.streamSimple(model, context, streamOptions),
	};
}
