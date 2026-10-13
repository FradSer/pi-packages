/**
 * pi-utils-fradser — private live-session control.
 *
 * Every session exposes its live instance over a private Unix socket: another
 * session (or a human running `/live-sessions` here) can discover instances and
 * deliver text to one without touching terminal input or session files. This
 * module owns the socket lifecycle and the `/live-sessions` command, which is
 * the capability's only entry point — the package deliberately ships no
 * separate executable.
 *
 * A delivery receipt is `handed-over` or `queued`; neither means the target
 * session accepted the text, and neither means it did the work. The extension API
 * pi.sendUserMessage returns void and the host reports a rejection on its own
 * channel, so the sender has no delivery disposition to report.
 */

import { randomUUID } from "node:crypto";
import type { AutocompleteItem } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { notifyPi, safeDisplayText } from "@fradser/pi-kit";
import { startServer } from "./live-sessions/server.ts";
import { execute } from "./live-sessions/client.ts";
import { controlDirectory } from "./live-sessions/transport.ts";
import type { Session } from "./live-sessions/protocol.ts";

/** Rows shown before the list is truncated. */
const MAX_LISTED_SESSIONS = 10;
/** Delivered text bound; the protocol rejects more, this keeps prompts sane. */
const MAX_DELIVERY_CHARS = 4_000;
/** Longest accepted instance id, matching the protocol's own bound. */
const MAX_ID_CHARS = 128;

/**
 * Live instances, or why discovery failed.
 *
 * An unusable control directory and an empty one look identical to the user, so
 * the reason is carried to the command instead of being collapsed into "no
 * sessions".
 */
type LiveSessionListing =
	| { ok: true; sessions: Session[] }
	| { ok: false; error: string };

async function listLiveSessions(): Promise<LiveSessionListing> {
	const response = await execute({
		version: 1,
		requestId: randomUUID(),
		command: "list",
	});
	if (!response.ok) return { ok: false, error: response.error?.message ?? "live-session discovery failed" };
	return { ok: true, sessions: response.sessions ?? [] };
}

/** One bounded line per live instance; every field is another process's text. */
function formatLiveSessionLine(session: Session): string {
	const name = session.name ? `${safeDisplayText(session.name)} · ` : "";
	return `${name}${session.state} · pid ${session.pid} · ${safeDisplayText(session.cwd)}`;
}

function formatLiveSessionList(sessions: Session[]): string {
	if (sessions.length === 0) return "No live Pi sessions found.";
	const lines = sessions
		.slice(0, MAX_LISTED_SESSIONS)
		.map((session, index) => `${index + 1}. ${formatLiveSessionLine(session)}`);
	if (sessions.length > MAX_LISTED_SESSIONS) {
		lines.push(`${sessions.length - MAX_LISTED_SESSIONS} more live session(s) not shown.`);
	}
	return lines.join("\n");
}

interface ParsedDelivery {
	deliverAs: "steer" | "followUp";
	sessionId: string;
	text: string;
}

/**
 * Parse `/live-sessions [steer] <sessionId> <text>`. An id longer than the
 * protocol bound or text beyond the delivery bound is rejected before any
 * socket call, so a malformed request never reaches the transport.
 */
export function parseDelivery(args: string): ParsedDelivery | { error: string } {
	const trimmed = args.trim();
	if (!trimmed) return { error: "usage: /live-sessions [steer] <sessionId> <text>" };

	let deliverAs: "steer" | "followUp" = "followUp";
	let rest = trimmed;
	if (rest === "steer" || rest.startsWith("steer ")) {
		deliverAs = "steer";
		rest = rest.slice("steer".length).trim();
	}

	const separator = rest.search(/\s/);
	const sessionId = separator === -1 ? rest : rest.slice(0, separator);
	const text = separator === -1 ? "" : rest.slice(separator + 1).trim();

	if (!sessionId) return { error: "a live session id is required" };
	if (sessionId.length > MAX_ID_CHARS) return { error: `session id is longer than ${MAX_ID_CHARS} characters` };
	if (!text) return { error: "delivery text is required" };
	if (text.length > MAX_DELIVERY_CHARS) return { error: `delivery text is longer than ${MAX_DELIVERY_CHARS} characters` };

	return { deliverAs, sessionId, text };
}

/**
 * Wait briefly for the target to observe the delivered text as its own prompt.
 *
 * The sender's runtime reports no delivery disposition, so the target is the only
 * witness: an idle target starts the turn and confirms inside the window, and a
 * busy one usually does not. An unconfirmed answer is reported as such, never as a
 * failure.
 */
const DELIVERY_CONFIRM_WINDOW_MS = 2_000;
const DELIVERY_CONFIRM_INTERVAL_MS = 200;

async function confirmDelivery(sessionId: string, requestId: string): Promise<boolean> {
	const deadline = Date.now() + DELIVERY_CONFIRM_WINDOW_MS;
	for (;;) {
		const response = await execute({
			version: 1,
			requestId: randomUUID(),
			command: "status",
			sessionId,
			confirmRequestId: requestId,
		});
		if (response.ok && response.confirmed) return true;
		if (Date.now() >= deadline) return false;
		await new Promise((resolve) => setTimeout(resolve, DELIVERY_CONFIRM_INTERVAL_MS));
	}
}

export default function registerLiveSessions(pi: ExtensionAPI): void {
	let server: Awaited<ReturnType<typeof startServer>> | undefined;
	/**
	 * Why this session has no live control, or null when it has one.
	 *
	 * A startup failure is remembered: the control directory can look empty
	 * afterwards, and an empty listing would hide that this session itself cannot
	 * be reached.
	 */
	let controlError: string | null = null;

	pi.on("session_start", async (_event, ctx) => {
		await server?.close();
		const sessionId = randomUUID();
		const piSessionId = ctx.sessionManager.getSessionId();
		try {
			server = await startServer(
				controlDirectory(),
				sessionId,
				() => ({
					sessionId,
					piSessionId,
					cwd: ctx.cwd,
					pid: process.pid,
					name: pi.getSessionName()?.slice(0, 256),
					state: ctx.isIdle() ? "idle" : "running",
				}),
				(text, deliverAs) => {
					if (ctx.sessionManager.getSessionId() !== piSessionId) {
						throw new Error("Session changed");
					}
					pi.sendUserMessage(text, { deliverAs });
				},
			);
			controlError = null;
		} catch (error) {
			// Live control is optional, but a session that silently serves nothing
			// makes every /live-sessions call look like an empty directory.
			server = undefined;
			controlError = error instanceof Error ? error.message : String(error);
			notifyPi(
				ctx.ui,
				`Live session control is unavailable: ${controlError}`,
				"warning",
			);
		}
	});

	pi.on("before_agent_start", (event) => {
		// The delivered text arrives as this turn's prompt, so this is where the
		// target confirms that it really received it.
		server?.observe(event.prompt);
	});

	pi.on("session_shutdown", async () => {
		const previous = server;
		server = undefined;
		await previous?.close();
	});

	pi.registerCommand("live-sessions", {
		description: "List live Pi sessions, or send text to one: /live-sessions [steer] <sessionId> <text>",
		// Completions arrive without a command context, so live ids are fetched
		// here; only the id position is completed.
		getArgumentCompletions: async (prefix: string): Promise<AutocompleteItem[] | null> => {
			if (/\s/.test(prefix)) return null;
			try {
				const typed = prefix.toLowerCase();
				const listing = await listLiveSessions();
				if (!listing.ok) return null;
				return listing.sessions
					.filter((session) => session.sessionId.toLowerCase().startsWith(typed))
					.map((session) => ({ value: session.sessionId, label: session.sessionId }));
			} catch {
				return null;
			}
		},
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			if (!args.trim()) {
				const listing = await listLiveSessions();
				if (!listing.ok) {
					notifyPi(ctx.ui, `Live session discovery failed: ${listing.error}`, "error");
					return;
				}
				if (controlError) {
					notifyPi(ctx.ui, `Live session control is unavailable in this session: ${controlError}`, "warning");
				}
				const sessions = listing.sessions;
				if (sessions.length === 0) {
					// The warning above already explains an empty directory that this
					// session caused.
					if (!controlError) notifyPi(ctx.ui, "No live Pi sessions found.", "info");
					return;
				}
				const text = formatLiveSessionList(sessions);
				if (ctx.hasUI) {
					await ctx.ui.select(`Live Pi sessions\n\n${text}`, ["Close"]);
					return;
				}
				notifyPi(ctx.ui, text, "info");
				return;
			}

			const parsed = parseDelivery(args);
			if ("error" in parsed) {
				notifyPi(ctx.ui, parsed.error, "error");
				return;
			}

			const request = {
				version: 1 as const,
				requestId: randomUUID(),
				command: "send" as const,
				sessionId: parsed.sessionId,
				text: parsed.text,
				deliverAs: parsed.deliverAs,
			};
			const response = await execute(request);

			if (!response.ok) {
				notifyPi(ctx.ui, `Live delivery failed: ${response.error?.message ?? "unknown error"}`, "error");
				return;
			}
			// Never claim completion. A delivery claim needs the target's own witness;
			// otherwise the receipt only proves this session handed the text over.
			if (response.confirmed === true || (await confirmDelivery(parsed.sessionId, request.requestId))) {
				notifyPi(
					ctx.ui,
					`Live session ${parsed.sessionId} confirmed the delivery to its own prompt — completion is still not claimed.`,
					"info",
				);
				return;
			}
			const outcome = response.status === "handed-over"
				? "handed over to its runtime"
				: "queued as a follow-up";
			notifyPi(
				ctx.ui,
				`Live session ${parsed.sessionId} ${outcome} — delivery is not confirmed and completion is not claimed.`,
				"info",
			);
		},
	});
}