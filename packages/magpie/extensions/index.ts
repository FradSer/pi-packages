/**
 * Pi provider for the magpie gateway.
 *
 * magpie already wires Pi's `models.json` when a model is picked there, but it
 * writes only that model. This extension registers the whole magpie catalog
 * instead: every provider model and routing group magpie serves becomes a Pi
 * model, and a refresh at session start picks up models added or removed in
 * magpie. Pin a subset with `MAGPIE_PI_MODELS` (comma-separated globs).
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { MAGPIE_PROVIDER_ID } from "./catalog.ts";
import { createMagpieProvider } from "./provider.ts";
import { loadMagpieSeed } from "./seed.ts";

const REFRESH_INTERVAL_MS = 5 * 60_000;
const REFRESH_TIMEOUT_MS = 5_000;

let lastRefresh = 0;

export default async function magpieExtension(pi: ExtensionAPI): Promise<void> {
	// Pi waits for an asynchronous factory before startup model selection, so the
	// first session already sees magpie's models; an offline or unreachable
	// gateway leaves the seed empty and the persisted catalog is used instead.
	const seed = await loadMagpieSeed();
	pi.registerProvider(createMagpieProvider({ seed }));

	pi.on("session_start", (_event, ctx) => {
		// Startup restores the persisted catalog without network access. Refresh once
		// per session so magpie's new models appear without waiting for a restart or
		// `pi update --models`. A failure keeps the last catalog.
		if (Date.now() - lastRefresh < REFRESH_INTERVAL_MS) return;
		lastRefresh = Date.now();
		void ctx.modelRegistry
			.refresh({
				providers: [MAGPIE_PROVIDER_ID],
				allowNetwork: true,
				force: true,
				signal: AbortSignal.timeout(REFRESH_TIMEOUT_MS),
			})
			.catch(() => {});
	});
}
