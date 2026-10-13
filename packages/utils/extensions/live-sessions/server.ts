import { createServer, type Socket } from "node:net";
import { chmod, unlink } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { checkDirectory, readFrame } from "./transport.ts";
import { failure, parseRequest, type Response, type Session } from "./protocol.ts";

export async function startServer(
	directory: string,
	sessionId: string,
	snapshot: () => Session,
	send: (text: string, deliverAs: "steer" | "followUp") => void,
) {
	await checkDirectory(directory, true);
	const path = join(directory, `${sessionId}.sock`);
	if (Buffer.byteLength(path) > 100) throw new Error("Socket path too long; use a shorter PI_UTILS_LIVE_SESSIONS_DIR");
	let active = true;
	const receipts = new Map<string, { fingerprint: string; response: Response; text: string; confirmedAt?: number }>();
	const sockets = new Set<Socket>();
	/**
	 * Record that this session observed `text` as a prompt.
	 *
	 * The sender's runtime reports no disposition for the text it was handed, so the
	 * target's own prompt is the only proof of delivery that exists; it upgrades the
	 * receipt for that requestId instead of guessing.
	 */
	const observe = (text: string): void => {
		for (const receipt of receipts.values()) {
			if (receipt.confirmedAt !== undefined || receipt.text !== text) continue;
			receipt.confirmedAt = Date.now();
			receipt.response = { ...receipt.response, confirmed: true };
		}
	};
	const handle = (value: unknown): Response => {
		const r = parseRequest(value);
		if (!active || r.sessionId !== sessionId) return failure(r.requestId, "stale_session", "Target is no longer active");
		const base = { version: 1 as const, requestId: r.requestId, ok: true };
		if (r.command === "status") {
			if (!r.confirmRequestId) return { ...base, session: snapshot() };
			return { ...base, session: snapshot(), confirmed: receipts.get(r.confirmRequestId)?.confirmedAt !== undefined };
		}
		if (r.command !== "send") return failure(r.requestId, "invalid_request", "Use the CLI for discovery");
		const fingerprint = createHash("sha256").update(JSON.stringify([r.text, r.deliverAs ?? "followUp"])).digest("hex");
		const previous = receipts.get(r.requestId);
		if (previous) {
			return previous.fingerprint === fingerprint
				? previous.response
				: failure(r.requestId, "request_conflict", "requestId already used for different input");
		}
		if (receipts.size >= 10000) return failure(r.requestId, "capacity", "Receipt capacity reached; start a new live session");
		// The receipt records what this session did with the text. The runtime exposes
		// no delivery disposition, so an idle target is not reported as having
		// accepted anything.
		const status = snapshot().state === "idle" ? "handed-over" : "queued";
		const response: Response = { ...base, sessionId, status };
		receipts.set(r.requestId, { fingerprint, response, text: r.text! });
		try {
			send(r.text!, r.deliverAs ?? "followUp");
		} catch {
			receipts.set(r.requestId, {
				fingerprint,
				response: failure(r.requestId, "delivery_failed", "Pi rejected delivery"),
				text: r.text!,
			});
		}
		return receipts.get(r.requestId)!.response;
	};
	const serve = async (socket: Socket) => {
		sockets.add(socket);
		socket.on("error", () => {});
		socket.once("close", () => sockets.delete(socket));
		try {
			socket.end(`${JSON.stringify(handle(JSON.parse(await readFrame(socket))))}\n`);
		} catch {
			socket.end(`${JSON.stringify(failure(null, "invalid_request", "Malformed, oversized, or timed-out request"))}\n`);
		}
	};
	const server = createServer((socket) => {
		void serve(socket);
	});
	await new Promise<void>((resolve, reject) => {
		server.once("error", reject);
		server.listen(path, resolve);
	});
	await chmod(path, 0o600);
	return {
		path,
		observe,
		async close() {
			if (!active) return;
			active = false;
			for (const socket of sockets) socket.destroy();
			await new Promise<void>((resolve) => server.close(() => resolve()));
			await unlink(path).catch((error: NodeJS.ErrnoException) => {
				if (error.code !== "ENOENT") throw error;
			});
		},
	};
}