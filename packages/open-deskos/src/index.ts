import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { open } from "node:fs/promises";
import { readDeskLinkConfig } from "./config.ts";
import { registerConsoleExtension } from "./console-extension.ts";
import { createControlTcpTransport } from "./control-transport.ts";
import { eventsFromMessage, promptFromMessage } from "./events.ts";
import { scanDirectorySessions, SessionDiscovery } from "./discovery.ts";
import { DeskReporter } from "./reporter.ts";
import { CurrentSessionReplay } from "./session-replay.ts";
import { createTcpTransport } from "./transport.ts";

const CONFIG_HINT = "set ODK_DESK_LINK_ADDRESS and ODK_DESK_LINK_TOKEN to report this machine";
/** Read only a bounded tail before it enters the reporter's own 300-event/1MiB retention pipeline. */
const MAX_DURABLE_SESSION_BYTES = 4 * 1024 * 1024;

function workspaceName(cwd: string): string {
  const parts = cwd.split(/[/\\]/).filter((part) => part.length > 0);
  return parts.length > 0 ? (parts[parts.length - 1] ?? cwd) : cwd;
}

/**
 * The current session manager points at its own trusted durable log. Read its
 * bounded tail in chronological order; other sessions never enter this path.
 */
async function durableSessionEvents(sessionFile: string | undefined): Promise<ReturnType<typeof eventsFromMessage>> {
  if (!sessionFile) return [];
  try {
    const handle = await open(sessionFile, "r");
    try {
      const stat = await handle.stat();
      if (!stat.isFile() || stat.size <= 0) return [];
      const bytes = Math.min(stat.size, MAX_DURABLE_SESSION_BYTES);
      const tail = Buffer.alloc(bytes);
      await handle.read(tail, 0, bytes, stat.size - bytes);
      const text = tail.toString("utf8");
      const lines = text.split("\n");
      // A writer can have produced valid JSON before its terminating newline.
      // It is still an incomplete append and must wait for message_end instead
      // of being replayed now and then sent a second time live.
      if (!text.endsWith("\n")) lines.pop();
      // A bounded tail can begin mid-record; that first fragment is never an entry.
      if (stat.size > bytes) lines.shift();
      return lines.flatMap((line) => {
        if (!line.trim()) return [];
        try {
          const entry = JSON.parse(line) as { type?: unknown; message?: unknown };
          return entry.type === "message" && entry.message !== undefined ? eventsFromMessage(entry.message) : [];
        } catch {
          return [];
        }
      });
    } finally {
      await handle.close();
    }
  } catch {
    return [];
  }
}

/**
 * Report this machine's Pi sessions and, with an independent credential, drive
 * Hosted Pi sessions over a separate Desk Link v2 control connection.
 */
export default function (pi: ExtensionAPI): void {
  const config = readDeskLinkConfig();
  const reporter = config === null ? null : new DeskReporter({ config, createTransport: createTcpTransport });
  const discovery = reporter === null ? null : new SessionDiscovery({
    discover: () => scanDirectorySessions(),
    onSnapshot: (sessions) => reporter.replaceDiscoveredSessions(sessions),
  });
  const replay = reporter === null ? null : new CurrentSessionReplay(durableSessionEvents);
  let currentSessionId = "";

  if (reporter && discovery) {
    function beginSession(ctx: Parameters<Parameters<ExtensionAPI["on"]>[1]>[1]): string {
      if (currentSessionId.length > 0 && currentSessionId !== ctx.sessionManager.getSessionId()) {
        reporter?.markStatus(currentSessionId, "exited");
      }
      currentSessionId = ctx.sessionManager.getSessionId();
      const name = ctx.sessionManager.getSessionName();
      const timestamp = ctx.sessionManager.getHeader()?.timestamp;
      const startedAt = timestamp ? Date.parse(timestamp) : Number.NaN;
      reporter?.recordSession({
        sessionId: currentSessionId,
        ...(name === undefined ? {} : { name }),
        cwd: ctx.cwd,
        workspaceName: workspaceName(ctx.cwd),
        status: ctx.isIdle() ? "settled" : "running",
        startedAt: Number.isFinite(startedAt) ? startedAt : Date.now(),
      });
      return currentSessionId;
    }

    pi.on("session_start", async (event, ctx) => {
      const sessionId = beginSession(ctx);
      reporter.start();
      discovery.start();
      // A resumed/reloaded Pi can have a durable JSONL history that is longer
      // than its in-memory branch. Start the gate for every session; only the
      // resumed/reloaded/forked cases provide a durable tail. New sessions still
      // queue their first message_end event behind this empty replay boundary.
      const replayFile = ["resume", "reload", "fork"].includes((event as { reason?: string }).reason ?? "")
        ? ctx.sessionManager.getSessionFile?.()
        : undefined;
      await replay?.start(sessionId, replayFile, (id, events) => reporter?.recordEvents(id, events));
    });
    pi.on("session_info_changed", (event) => {
      if (currentSessionId.length > 0) reporter.renameSession(currentSessionId, event.name);
    });
    pi.on("agent_start", () => reporter.markStatus(currentSessionId, "running"));
    pi.on("agent_settled", () => reporter.markStatus(currentSessionId, "settled"));
    pi.on("message_end", (event) => {
      if (currentSessionId.length === 0) return;
      const prompt = promptFromMessage(event.message);
      if (prompt.length > 0) reporter.recordSession({ sessionId: currentSessionId, latestGoal: prompt });
      const events = eventsFromMessage(event.message);
      replay?.append(currentSessionId, events, (id, fresh) => reporter?.recordEvents(id, fresh));
    });
    pi.on("session_shutdown", () => {
      replay?.invalidate();
      discovery.stop();
      reporter.markStatus(currentSessionId, "exited");
      reporter.disconnect();
    });
  }

  registerConsoleExtension({
    pi,
    config,
    createControlTransport: createControlTcpTransport,
    reporterSnapshot: () => reporter?.snapshot() ?? null,
    configHint: CONFIG_HINT,
  });
}
