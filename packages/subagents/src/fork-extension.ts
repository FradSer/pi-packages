/**
 * Explicit child-only RPC contribution for --no-session forks. Pi 1.0.0 exposes
 * no RPC entry import; its ExtensionContext sessionManager is intentionally
 * read-only. Keep the detached seed in this extension instance and prepend it
 * through native context transformation, never a prompt, entry or history file.
 */
import type { ExtensionAPI, SessionContext } from "@earendil-works/pi-coding-agent";
import {
  decodeForkContext,
  FORK_CONTEXT_ACK_STATUS,
  FORK_CONTEXT_COMMAND,
  MAX_FORK_CONTEXT_COMMAND_BYTES,
  type ForkContextAck,
} from "./work-context.ts";

export default function forkExtension(pi: ExtensionAPI): void {
  let seed: SessionContext["messages"] | undefined;
  let inputSeen = false;
  let closed = false;

  pi.registerCommand(FORK_CONTEXT_COMMAND, {
    description: "Initialize a temporary child's in-memory fork context (RPC control only)",
    handler: async (args, ctx) => {
      const separator = args.indexOf(" ");
      const requestId = separator < 0 ? args : args.slice(0, separator);
      // Invalid IDs cannot be acknowledged/correlated and are never echoed.
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(requestId)) throw new Error("Fork context request id is invalid.");
      let ack: ForkContextAck;
      try {
        if (ctx.mode !== "rpc" || ctx.sessionManager.getSessionFile() !== undefined) {
          throw new Error("Fork context setup requires an RPC child with --no-session.");
        }
        if (closed || seed !== undefined || inputSeen || !ctx.isIdle() || ctx.hasPendingMessages()
          || ctx.sessionManager.getEntries().some(entry => entry.type === "custom_message"
            || entry.type === "branch_summary" || entry.type === "compaction"
            || (entry.type === "message" && entry.message.role !== "system"))) {
          throw new Error("Fork context setup requires a fresh idle child and may only run once.");
        }
        if (separator < 0 || Buffer.byteLength(args, "utf8") > MAX_FORK_CONTEXT_COMMAND_BYTES) {
          throw new Error("Fork context command is invalid or exceeds the transport limit.");
        }
        const snapshot = decodeForkContext(args.slice(separator + 1));
        seed = snapshot;
        ack = { version: 1, requestId, success: true, messageCount: snapshot.length };
      } catch (error) {
        ack = { version: 1, requestId, success: false,
          error: error instanceof Error ? error.message.slice(0, 512) : "Fork context setup failed." };
      }
      // setStatus is a native RPC notification, not session/LLM state. Pi catches
      // command errors and STILL replies handled, so the parent needs this ack.
      ctx.ui.setStatus(FORK_CONTEXT_ACK_STATUS, JSON.stringify(ack));
    },
  });

  pi.on("input", () => { inputSeen = true; });
  pi.on("context", event => {
    if (seed === undefined || closed) return;
    // Request-local only: native child history accumulates each accepted input
    // and answer. Neither event.messages nor the stored seed is ever mutated.
    return { messages: [...structuredClone(seed), ...event.messages] };
  });
  pi.on("session_shutdown", () => { seed = undefined; closed = true; });
}
