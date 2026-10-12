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
 * A delivery receipt is `accepted` or `queued`; neither means the target
 * session did the work.
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

export default function registerLiveSessions(pi: ExtensionAPI): void {
	let server: Awaited<ReturnType<typeof startServer>> | undefined;

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
		} catch (error) {
			// Live control is optional, but a session that silently serves nothing
			// makes every /live-sessions call look like an empty directory.
			server = undefined;
			notifyPi(
				ctx.ui,
				`Live session control is unavailable: ${error instanceof Error ? error.message : String(error)}`,
				"warning",
			);
		}
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
				const sessions = listing.sessions;
				if (sessions.length === 0) {
					notifyPi(ctx.ui, "No live Pi sessions found.", "info");
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

			const response = await execute({
				version: 1,
				requestId: randomUUID(),
				command: "send",
				sessionId: parsed.sessionId,
				text: parsed.text,
				deliverAs: parsed.deliverAs,
			});

			if (!response.ok) {
				notifyPi(ctx.ui, `Live delivery failed: ${response.error?.message ?? "unknown error"}`, "error");
				return;
			}
			// Never claim completion: the receipt only proves the target
			// accepted or queued the text.
			const outcome = response.status === "accepted" ? "accepted" : "queued as follow-up";
			notifyPi(
				ctx.ui,
				`Live session ${parsed.sessionId} ${outcome} — the text was delivered, not completed.`,
				"info",
			);
		},
	});
}